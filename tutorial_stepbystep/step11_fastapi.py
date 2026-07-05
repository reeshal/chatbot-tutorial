"""
Backend web (FastAPI) pour le chatbot local.

Réutilise ChatSession SANS la modifier : l'endpoint consomme le générateur
`ask` et diffuse les fragments au client via une réponse en streaming.

Lancement :
    pip install fastapi uvicorn
    uvicorn server:app --reload
    # L'API écoute alors sur http://127.0.0.1:8000
"""

from collections.abc import Iterator

import httpx
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from ollama import ResponseError
from pydantic import BaseModel

from step10_generator import ChatSession


app = FastAPI()

# Une seule session partagée pour l'instant (chatbot personnel, mono-utilisateur).
# LIMITE connue : tous les clients partagent le même historique, et deux
# requêtes simultanées s'entremêleraient. On introduira des sessions
# distinctes par client plus tard.
session = ChatSession()


class ChatRequest(BaseModel):
    """Corps attendu de la requête : le message de l'utilisateur.

    Pydantic valide automatiquement que `message` est bien une chaîne
    présente dans le JSON reçu, et renvoie une erreur 422 sinon.
    """

    message: str


@app.post("/chat")
def chat(request: ChatRequest) -> StreamingResponse:
    """Reçoit un message et diffuse la réponse du modèle, token par token."""

    def token_stream() -> Iterator[str]:
        # On enveloppe la génération : une erreur réseau ne doit pas couper
        # brutalement la réponse HTTP, mais s'afficher comme un message lisible.
        try:
            for token in session.ask(request.message):
                yield token
        except httpx.ConnectError:
            session.rollback_last_question()
            yield "[Erreur] Ollama injoignable. Le serveur tourne-t-il ?"
        except ResponseError as error:
            session.rollback_last_question()
            yield f"[Erreur Ollama] {error}"

    # media_type text/plain : un simple flux de texte, lu morceau par morceau
    # côté client. StreamingResponse itère le générateur et envoie chaque
    # fragment dès qu'il est produit, sans attendre la fin.
    return StreamingResponse(token_stream(), media_type="text/plain")

# Monte le dossier static/ : toute requête /static/X.Y sert le fichier
# static/X.Y (le CSS et le JS sont donc accessibles automatiquement).
app.mount("/static", StaticFiles(directory="static"), name="static")

# La racine renvoie la page HTML elle-même.
@app.get("/")
def index() -> FileResponse:
    return FileResponse("static/index.html")