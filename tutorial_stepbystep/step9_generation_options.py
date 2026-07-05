"""
Chatbot en ligne de commande connecté à un modèle local via Ollama.

Architecture :
    - ChatSession : toute la logique de conversation (historique, fenêtre
      glissante, options de génération, streaming). Ne connaît rien du
      terminal, donc réutilisable ailleurs (ex. backend web).
    - main()      : la boucle interactive, seule partie liée au terminal.

Prérequis :
    pip install ollama        # installe aussi httpx (réseau)
    ollama pull llama3.1:8b   # le modèle doit être présent localement
    # Vérifier que le GPU est utilisé : `ollama ps` (colonne PROCESSOR)
"""

import sys

import httpx
import ollama
from ollama import ResponseError


class ChatSession:
    """Gère une conversation persistante avec un modèle local.

    Le message « system » définit le rôle de l'assistant. Il est placé en
    tête de l'historique et protégé : la fenêtre glissante ne le supprime
    jamais, sinon l'assistant oublierait son identité au fil de l'échange.
    """

    # Personnalité par défaut. Modifiable à la création de la session.
    DEFAULT_SYSTEM_PROMPT: str = (
        "Tu es un assistant concis et serviable. "
        "Tu réponds en français, avec clarté, et tu admets quand tu ne sais pas."
    )

    def __init__(
        self,
        model: str = "llama3.1:8b",
        max_turns: int = 10,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
    ) -> None:
        self._model: str = model

        # Nombre maximal d'échanges conservés (1 échange = question + réponse).
        self._max_turns: int = max_turns

        # L'historique DÉMARRE avec le message system, en position 0.
        # _trim_history ne touche jamais à cet élément.
        self._messages: list[dict[str, str]] = [
            {"role": "system", "content": system_prompt}
        ]

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

    def ask(self, user_input: str) -> str:
        """Envoie un message, diffuse la réponse, et la renvoie en entier."""
        # On enregistre la question avant l'appel : le modèle doit la voir.
        self._messages.append({"role": "user", "content": user_input})

        # stream=True : la réponse arrive en fragments, pas d'un seul bloc.
        stream = ollama.chat(
            model=self._model,
            messages=self._messages,
            stream=True,
            options=self._options,
        )

        # On reconstruit la réponse complète : le streaming ne nous donne
        # que des morceaux, mais l'historique a besoin du texte entier.
        bot_reply: str = ""
        for chunk in stream:
            token: str = chunk["message"]["content"]
            # flush=True : affichage immédiat, sinon Python met en tampon.
            print(token, end="", flush=True)
            bot_reply += token
        print()  # un seul retour à la ligne une fois la réponse terminée.

        self._messages.append({"role": "assistant", "content": bot_reply})

        # On borne l'historique après chaque échange complet.
        self._trim_history()
        return bot_reply

    def _trim_history(self) -> None:
        """Borne l'historique en PRÉSERVANT le message system (position 0).

        On isole le message system, on ne rogne QUE la conversation, puis
        on recolle le tout. Ainsi le system survit à n'importe quelle durée
        de conversation.
        """
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

        Le message system (position 0) n'est jamais retiré : on exige donc
        qu'il reste au moins un message en plus de lui.
        """
        if len(self._messages) > 1:
            self._messages.pop()


def main() -> None:
    """Boucle interactive : la seule partie qui connaît le terminal."""
    session = ChatSession()
    print("Chatbot local prêt. Tapez 'exit' pour quitter.\n")

    while True:
        # Ctrl+C / Ctrl+D ne doivent pas crasher, mais quitter proprement.
        try:
            user_input: str = input("Vous : ")
        except (EOFError, KeyboardInterrupt):
            print("\nAu revoir.")
            break

        if user_input.lower() == "exit":
            break

        print("Bot : ", end="", flush=True)

        # On protège l'appel réseau : c'est la partie qui peut échouer
        # pour des raisons hors de notre contrôle.
        try:
            session.ask(user_input)
        except httpx.ConnectError:
            # Le serveur Ollama est arrêté ou injoignable.
            print(
                "\n[Erreur] Impossible de joindre Ollama. "
                "Vérifiez que le serveur tourne.",
                file=sys.stderr,
            )
            session.rollback_last_question()
        except ResponseError as error:
            # Ollama a répondu mais avec une erreur (ex. modèle introuvable).
            print(f"\n[Erreur Ollama] {error}", file=sys.stderr)
            session.rollback_last_question()


if __name__ == "__main__":
    main()