"""
Chatbot en ligne de commande connecté à un modèle local via Ollama.

La logique de conversation (classe ChatSession) est séparée de l'interface
terminal (fonction main). Cette séparation permet de réutiliser ChatSession
ailleurs — par exemple dans un backend web — sans rien réécrire.
"""

import sys

import httpx
import ollama
from ollama import ResponseError


class ChatSession:
    """Gère une conversation persistante avec un modèle local.

    Cette classe ne connaît rien du terminal : elle ne fait ni input()
    ni print() décoratif. Elle expose simplement une méthode `ask`.
    C'est ce qui la rend réutilisable dans n'importe quelle interface.
    """

    def __init__(self, model: str = "llama3.1:8b") -> None:
        self._model: str = model
        # L'historique vit dans l'objet, plus dans une variable globale.
        self._messages: list[dict[str, str]] = []

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
        return bot_reply

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