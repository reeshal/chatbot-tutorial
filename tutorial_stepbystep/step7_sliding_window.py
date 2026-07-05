
import sys

import httpx
import ollama
from ollama import ResponseError


class ChatSession:
    """Gère une conversation persistante avec un modèle local.

    L'historique est borné par une fenêtre glissante : on ne conserve
    que les `max_turns` derniers échanges pour éviter de dépasser la
    taille du contexte du modèle.
    """

    def __init__(self, model: str = "llama3.1:8b", max_turns: int = 10) -> None:
        self._model: str = model
        self._messages: list[dict[str, str]] = []
        # Nombre maximal d'échanges (1 échange = 1 question + 1 réponse)
        # que l'on garde en mémoire.
        self._max_turns: int = max_turns

    def ask(self, user_input: str) -> str:
        """Envoie un message, diffuse la réponse, et la renvoie en entier."""
        self._messages.append({"role": "user", "content": user_input})

        stream = ollama.chat(
            model=self._model,
            messages=self._messages,
            stream=True,
        )

        bot_reply: str = ""
        for chunk in stream:
            token: str = chunk["message"]["content"]
            print(token, end="", flush=True)
            bot_reply += token
        print()

        self._messages.append({"role": "assistant", "content": bot_reply})

        # NOUVEAU : on rogne l'historique après chaque échange complet.
        self._trim_history()
        return bot_reply

    def _trim_history(self) -> None:
        """Ne conserve que les `max_turns` derniers échanges.

        Un échange = 2 messages (utilisateur + assistant), donc la
        limite en nombre de messages est `max_turns * 2`. Les messages
        les plus anciens sont supprimés en premier.
        """
        max_messages: int = self._max_turns * 2
        if len(self._messages) > max_messages:
            # On garde uniquement la fin de la liste (les plus récents).
            self._messages = self._messages[-max_messages:]

    def rollback_last_question(self) -> None:
        """Retire la dernière question restée sans réponse (après une erreur)."""
        if self._messages:
            self._messages.pop()

def main() -> None:
    """Boucle interactive : la seule partie qui connaît le terminal."""
    session = ChatSession()
    print("Chatbot local prêt. Tapez 'exit' pour quitter.\n")

    while True:
        try:
            user_input: str = input("Vous : ")
        except (EOFError, KeyboardInterrupt):
            print("\nAu revoir.")
            break

        if user_input.lower() == "exit":
            break

        print("Bot : ", end="", flush=True)
        try:
            session.ask(user_input)
        except httpx.ConnectError:
            print(
                "\n[Erreur] Impossible de joindre Ollama. "
                "Vérifiez que le serveur tourne.",
                file=sys.stderr,
            )
            session.rollback_last_question()
        except ResponseError as error:
            print(f"\n[Erreur Ollama] {error}", file=sys.stderr)
            session.rollback_last_question()


if __name__ == "__main__":
    main()