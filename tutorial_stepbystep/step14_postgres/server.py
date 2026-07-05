"""
Backend web (FastAPI) pour le chatbot local — stockage PostgreSQL.

Identique à l'étape 13 côté logique (endpoints, streaming, titrage) : seule la
COUCHE DE STOCKAGE change. On construit un pool de connexions Postgres au
démarrage et on l'injecte dans le repository et dans chaque store par requête.

Lancement :
    docker compose up -d                       # démarre Postgres + pgAdmin
    export DATABASE_URL=postgresql://chatbot:chatbot@localhost:5432/chatbot
    pip install -r requirements.txt
    uvicorn server:app --reload
"""

import os
from collections.abc import Iterator

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from ollama import ResponseError
from psycopg_pool import ConnectionPool
from pydantic import BaseModel

from chatsession import ChatSession
from store import ConversationRepository, PostgresConversationStore


# Chaîne de connexion lue dans l'environnement (défaut = valeurs du compose).
DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://chatbot:chatbot@localhost:5432/chatbot"
)

app = FastAPI()

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
    (contrainte ON DELETE CASCADE). 404 si inexistante.

    (On choisit 404 sur un id absent — plutôt qu'un succès idempotent — parce
    qu'ici cela force à écrire le contrôle d'existence, ce qui est l'intérêt
    pédagogique.)"""
    if not repo.delete(conversation_id):
        raise HTTPException(status_code=404, detail="Conversation introuvable")
    return {"ok": True}


# ---------------------------------------------------------------------------
# Conversation : streaming d'une réponse
# ---------------------------------------------------------------------------
@app.post("/chat")
def chat(request: ChatRequest) -> StreamingResponse:
    """Reçoit un message pour UNE conversation et diffuse la réponse, token par
    token. La session est reconstruite ici, à partir du store de la conversation."""

    store = PostgresConversationStore(pool, conversation_id=request.conversation_id)
    session = ChatSession(store=store)

    def token_stream() -> Iterator[str]:
        try:
            for token in session.ask(request.message):
                yield token
        except httpx.ConnectError:
            session.rollback_last_question()
            yield "[Erreur] Ollama injoignable. Le serveur tourne-t-il ?"
        except ResponseError as error:
            session.rollback_last_question()
            yield f"[Erreur Ollama] {error}"
        else:
            # Le streaming a réussi → session.ask() a déjà persisté le tour.
            # On peut maintenant titrer : autotitle lit le premier message
            # utilisateur EN BASE (et non request.message, qui n'est le premier
            # que sur une conversation neuve). No-op si déjà titrée.
            repo.autotitle(request.conversation_id)

    return StreamingResponse(token_stream(), media_type="text/plain")


# Fichiers statiques propres à cette étape.
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse("static/index.html")
