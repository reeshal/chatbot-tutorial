import sys

import httpx
import ollama
from ollama import ResponseError

messages = []

while True:
    # On protège aussi la saisie : Ctrl+C ou Ctrl+D ne doit pas
    # provoquer une erreur, mais quitter proprement.
    try:
        user_input = input("Vous : ")
    except (EOFError, KeyboardInterrupt):
        print("\nAu revoir.")
        break

    if user_input.lower() == "exit":
        break

    messages.append({"role": "user", "content": user_input})

    # On entoure l'appel réseau d'un try/except : c'est la partie
    # qui peut échouer pour des raisons hors de notre contrôle.
    try:
        stream = ollama.chat(
            model="llama3.1:8b",
            messages=messages,
            stream=True,
        )

        print("Bot : ", end="", flush=True)
        bot_reply = ""

        for chunk in stream:
            token = chunk["message"]["content"]
            print(token, end="", flush=True)
            bot_reply += token

        print()
        messages.append({"role": "assistant", "content": bot_reply})

    except httpx.ConnectError:
        # Le serveur Ollama est arrêté ou injoignable.
        print(
            "\n[Erreur] Impossible de joindre Ollama. "
            "Vérifiez que le serveur tourne.",
            file=sys.stderr,
        )
        # On retire la question de l'historique : elle n'a pas reçu
        # de réponse, autant ne pas la garder pour ne pas fausser la suite.
        messages.pop()

    except ResponseError as error:
        # Ollama a répondu mais avec une erreur (ex. modèle introuvable).
        print(f"\n[Erreur Ollama] {error}", file=sys.stderr)
        messages.pop()