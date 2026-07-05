"""
Backend web (FastAPI) pour le chatbot local — version « liste de conversations ».

Nouveautés par rapport à l'étape 12 :
  - le serveur est SANS ÉTAT par requête : pour chaque message, il reconstruit
    une ChatSession à partir du store de la conversation visée. SQLite reste
    l'unique source de vérité — aucun cache en mémoire à invalider.
  - une couche CRUD (ConversationRepository) expose les conversations via REST,
    ce qui alimente la barre latérale du front.

Lancement :
    pip install fastapi uvicorn
    uvicorn server:app --reload
    # L'API écoute alors sur http://127.0.0.1:8000
"""

from collections.abc import Iterator

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from ollama import ResponseError
from pydantic import BaseModel

from chatsession import ChatSession
from store import ConversationRepository, SQLiteConversationStore


DB_PATH = "conversations.db"

app = FastAPI()

# Le repository gère la COLLECTION de conversations. Sa construction lance aussi
# la migration de démarrage (backfill des historiques antérieurs).
repo = ConversationRepository(DB_PATH)


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
    messages = SQLiteConversationStore(DB_PATH, conversation_id).load()
    return [m for m in messages if m["role"] != "system"]


@app.patch("/conversations/{conversation_id}")
def rename_conversation(conversation_id: str, request: RenameRequest) -> dict[str, str]:
    """UPDATE : renomme la conversation. 404 si l'id n'existe pas."""
    if not repo.rename(conversation_id, request.title):
        raise HTTPException(status_code=404, detail="Conversation introuvable")
    return {"id": conversation_id, "title": request.title}


@app.delete("/conversations/{conversation_id}")
def delete_conversation(conversation_id: str) -> dict[str, bool]:
    """DELETE : supprime la conversation et ses messages. 404 si inexistante.

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

    store = SQLiteConversationStore(DB_PATH, conversation_id=request.conversation_id)
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


# Fichiers statiques PROPRES à cette étape (la barre latérale change le HTML/JS,
# on ne réutilise donc pas le ../static partagé avec l'étape 12).
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse("static/index.html")
