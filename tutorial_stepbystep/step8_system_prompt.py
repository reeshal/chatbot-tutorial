
import sys

import httpx
import ollama
from ollama import ResponseError


class ChatSession:
    """Gère une conversation persistante avec un modèle local.

    Le message « system » définit le rôle de l'assistant. Il est placé en
    tête de l'historique et protégé : la fenêtre glissante ne le supprime
    jamais, sinon l'assistant oublierait son identité au fil de la
    conversation.
    """

    # Personnalité par défaut. Modifiable à la création de la session.
    DEFAULT_SYSTEM_PROMPT: str = (
        "Tu es un assistant concis et serviable. "
        "Tu réponds en français, avec clarté, et tu admets quand tu ne sais pas. Tu dois repondre dans le meme ton que Mario depuis Super Mario Bros"
    )

    def __init__(
        self,
        model: str = "llama3.1:8b",
        max_turns: int = 10,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
    ) -> None:
        self._model: str = model
        self._max_turns: int = max_turns
        # L'historique DÉMARRE avec le message system, en position 0.
        # Il y restera : _trim_history ne touche jamais à cet élément.
        self._messages: list[dict[str, str]] = [
            {"role": "system", "content": system_prompt}
        ]

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
        self._trim_history()
        return bot_reply

    def _trim_history(self) -> None:
        """Borne l'historique en PRÉSERVANT le message system (position 0).

        On découpe l'historique en deux : le message system d'un côté,
        la conversation de l'autre. On ne rogne QUE la conversation,
        puis on recolle le tout. Ainsi le system survit toujours.
        """
        # Le message system est toujours le premier élément.
        system_message: dict[str, str] = self._messages[0]

        # Tout le reste : les vrais échanges user/assistant.
        conversation: list[dict[str, str]] = self._messages[1:]

        max_messages: int = self._max_turns * 2
        if len(conversation) > max_messages:
            # On ne garde que les échanges les plus récents...
            conversation = conversation[-max_messages:]

        # ...puis on reconstruit : system EN PREMIER, conversation ensuite.
        self._messages = [system_message] + conversation

    def rollback_last_question(self) -> None:
        """Retire la dernière question restée sans réponse (après une erreur)."""
        # On ne retire jamais le message system : il faut au moins
        # qu'il reste un message en plus de lui pour pouvoir en retirer un.
        if len(self._messages) > 1:
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