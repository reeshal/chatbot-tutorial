"""
Backend API (FastAPI) pour le chatbot local

Lancement (depuis backend/python ; le docker-compose vit un cran au-dessus,
partagé par toutes les implémentations du backend) :
    docker compose -f ../docker-compose.yml up -d   # Postgres + pgAdmin
    export DATABASE_URL=postgresql://chatbot:chatbot@localhost:5432/chatbot
    pip install -r requirements.txt
    uvicorn main:app --reload
"""

import json
import os
from collections.abc import Iterator

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from ollama import ResponseError
from psycopg_pool import ConnectionPool
from pydantic import BaseModel

from chatsession import ChatSession
from store import ConversationRepository, PostgresConversationStore


# Chaîne de connexion lue dans l'environnement (défaut = valeurs du compose).
DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://chatbot:chatbot@localhost:5432/chatbot"
)

# Origin du frontend, seul autorisé par CORS (défaut = dev-server Vite).
FRONTEND_ORIGIN = os.environ.get("FRONTEND_ORIGIN", "http://localhost:5173")

app = FastAPI()

# Le navigateur bloque par défaut les requêtes entre origins différents
# (5173 → 8000). Ce middleware ajoute les en-têtes qui les autorisent,
# pour NOTRE frontend uniquement.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_ORIGIN],
    allow_methods=["*"],
    allow_headers=["*"],
)

# UN pool de connexions partagé par toute l'application. Ouvrir une connexion
# Postgres est coûteux ; le pool en garde quelques-unes prêtes à l'emploi.
pool = ConnectionPool(DATABASE_URL, open=True)

# Le repository gère la COLLECTION de conversations. Sa construction lance aussi
# la migration de démarrage (backfill des historiques importés, s'il y en a).
repo = ConversationRepository(pool)


class ChatRequest(BaseModel):
    """Corps de /chat : le message ET la conversation visée."""

    message: str
    conversation_id: str


class RenameRequest(BaseModel):
    """Corps de PATCH /conversations/{id}."""

    title: str


# ---------------------------------------------------------------------------
# CRUD des conversations (alimente la liste / le détail de la barre latérale)
# ---------------------------------------------------------------------------
@app.get("/conversations")
def list_conversations() -> list[dict[str, str]]:
    """LISTE : toutes les conversations, la plus récente en premier."""
    return repo.list()


@app.post("/conversations")
def create_conversation() -> dict[str, str]:
    """CREATE : une conversation vide ; renvoie son identifiant."""
    return {"id": repo.create()}


@app.get("/conversations/{conversation_id}")
def get_conversation(conversation_id: str) -> list[dict[str, str]]:
    """DÉTAIL : les messages de la conversation, SANS le message system
    (interne au modèle, jamais affiché). 404 si l'id n'existe pas."""
    if not repo.exists(conversation_id):
        raise HTTPException(status_code=404, detail="Conversation introuvable")
    messages = PostgresConversationStore(pool, conversation_id).load()
    return [m for m in messages if m["role"] != "system"]


@app.patch("/conversations/{conversation_id}")
def rename_conversation(conversation_id: str, request: RenameRequest) -> dict[str, str]:
    """UPDATE : renomme la conversation. 404 si l'id n'existe pas."""
    if not repo.rename(conversation_id, request.title):
        raise HTTPException(status_code=404, detail="Conversation introuvable")
    return {"id": conversation_id, "title": request.title}


@app.delete("/conversations/{conversation_id}")
def delete_conversation(conversation_id: str) -> dict[str, bool]:
    """DELETE : supprime la conversation ; ses messages partent en cascade
    (contrainte ON DELETE CASCADE). 404 si inexistante."""
    if not repo.delete(conversation_id):
        raise HTTPException(status_code=404, detail="Conversation introuvable")
    return {"ok": True}


# ---------------------------------------------------------------------------
# Conversation : streaming d'une réponse (SSE)
# ---------------------------------------------------------------------------
def _sse(event: str, data: dict[str, object]) -> str:
    """Encode UN évènement au format Server-Sent Events.

    Format texte normalisé : « event: <type> », « data: <payload> », ligne
    vide pour clore. Le payload est du JSON : côté client, chaque évènement
    redevient un objet typé, sans ambiguïté token/erreur.
    """
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.post("/chat")
def chat(request: ChatRequest) -> StreamingResponse:
    """Reçoit un message pour UNE conversation et diffuse la réponse en
    évènements SSE :
      - event: token → {"text": ...}     un fragment de réponse ;
      - event: error → {"message": ...}  une erreur (Ollama absent, etc.) ;
      - event: done  → {}                tour persisté et conversation titrée.

    La session est reconstruite ici, à partir du store de la conversation."""
    if not repo.exists(request.conversation_id):
        raise HTTPException(status_code=404, detail="Conversation introuvable")

    store = PostgresConversationStore(pool, conversation_id=request.conversation_id)
    session = ChatSession(store=store)

    def event_stream() -> Iterator[str]:
        try:
            for token in session.ask(request.message):
                yield _sse("token", {"text": token})
        except httpx.ConnectError:
            session.rollback_last_question()
            yield _sse("error", {"message": "Ollama injoignable. Le serveur tourne-t-il ?"})
        except ResponseError as error:
            session.rollback_last_question()
            yield _sse("error", {"message": f"Erreur Ollama : {error}"})
        else:
            # Le streaming a réussi → session.ask() a déjà persisté le tour.
            # On peut maintenant titrer : autotitle lit le premier message
            # utilisateur EN BASE (et non request.message, qui n'est le premier
            # que sur une conversation neuve). No-op si déjà titrée.
            repo.autotitle(request.conversation_id)
            yield _sse("done", {})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        # Empêche la mise en tampon par les proxys : chaque évènement doit
        # partir immédiatement, sinon le « streaming » arrive d'un bloc.
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
