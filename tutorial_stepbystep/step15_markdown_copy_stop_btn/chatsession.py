import sys
from collections.abc import Iterator
from store import ConversationStore
import httpx
import ollama
from ollama import ResponseError


class ChatSession:

    # Personnalité par défaut. Modifiable à la création de la session.
    DEFAULT_SYSTEM_PROMPT: str = (
        "Tu es un assistant concis et serviable. "
        "Tu réponds en français avec l'accent de Mario depuis Super Mario Bros, avec clarté, et tu admets quand tu ne sais pas."
    )

    def __init__(
        self,
        model: str = "llama3.1:8b",
        max_turns: int = 10,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        store: ConversationStore | None = None,  # type = le Protocol
    ) -> None:
        self._model: str = model

        # Nombre maximal d'échanges conservés (1 échange = question + réponse).
        self._max_turns: int = max_turns

        # Stockage de persistance (None = session purement en mémoire).
        self._store: ConversationStore | None = store

        # L'historique DÉMARRE avec le message system, en position 0.
        # _trim_history ne touche jamais à cet élément.
        self._messages: list[dict[str, str]] = [
            {"role": "system", "content": system_prompt}
        ]

        # Si un stockage est fourni et contient une conversation, on la
        # restaure. La conversation sauvegardée inclut déjà son propre message
        # system en position 0 : on remplace donc l'historique complet.
        if self._store is not None:
            saved: list[dict[str, str]] = self._store.load()
            if saved:
                self._messages = saved

        # Options de génération : elles contrôlent NON pas ce que dit le bot
        # (ça, c'est le system), mais COMMENT il génère son texte.
        self._options: dict[str, object] = {
            # Créativité. 0.0 = déterministe/factuel, 1.0+ = imprévisible.
            "temperature": 0.7,
            # Longueur max d'une réponse, en tokens. -1 = illimité.
            "num_predict": 512,
            # Taille de la fenêtre de contexte du modèle, en tokens.
            # C'est le VRAI plafond : system + historique + réponse doivent
            # tenir dedans. Fixé explicitement pour ne pas dépendre du défaut
            # (variable selon la VRAM) ni de la troncature silencieuse d'Ollama.
            "num_ctx": 8192,
            # Séquences qui interrompent la génération (empêche le modèle
            # de « jouer » le rôle de l'utilisateur).
            "stop": ["Vous :"],
            # Graine aléatoire. Valeur fixe + temperature basse = sorties
            # reproductibles (utile pour les tests). None = aléatoire.
            "seed": None,
        }

    def ask(self, user_input: str) -> Iterator[str]:

        # On enregistre la question avant l'appel : le modèle doit la voir.
        self._messages.append({"role": "user", "content": user_input})

        stream = ollama.chat(
            model=self._model,
            messages=self._messages,
            stream=True,
            options=self._options,
        )

        # On reconstruit la réponse complète : le streaming ne donne que des
        # morceaux, mais l'historique a besoin du texte entier.
        bot_reply: str = ""
        for chunk in stream:
            token: str = chunk["message"]["content"]
            bot_reply += token
            yield token  # on transmet le fragment à l'appelant.

        # ATTENTION : ce code ne s'exécute QU'UNE FOIS le streaming terminé,
        # donc uniquement si l'appelant consomme tout le générateur. Si le
        # générateur est abandonné en cours de route, la réponse ne sera
        # pas enregistrée dans l'historique.
        self._messages.append({"role": "assistant", "content": bot_reply})
        self._trim_history()

        # Persiste l'échange complet : au prochain démarrage, __init__ le
        # rechargera. On sauvegarde APRÈS _trim_history pour stocker exactement
        # la fenêtre conservée en mémoire.
        if self._store is not None:
            self._store.save(self._messages)

    def _trim_history(self) -> None:
        system_message: dict[str, str] = self._messages[0]
        conversation: list[dict[str, str]] = self._messages[1:]

        max_messages: int = self._max_turns * 2
        if len(conversation) > max_messages:
            # On ne garde que les échanges les plus récents.
            conversation = conversation[-max_messages:]

        # On reconstruit : system EN PREMIER, conversation ensuite.
        self._messages = [system_message] + conversation

    def rollback_last_question(self) -> None:
        """Retire la dernière question restée sans réponse (après une erreur).

        Le message system (position 0) n'est jamais retiré : on exige donc qu'il reste au moins un message en plus de lui.
        """
        if len(self._messages) > 1:
            self._messages.pop()


def main() -> None:

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
            for token in session.ask(user_input):
                print(token, end="", flush=True)
            print()
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