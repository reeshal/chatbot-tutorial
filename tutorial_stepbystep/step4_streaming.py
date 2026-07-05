import ollama

messages = []

while True:
    user_input = input("Vous : ")

    if user_input.lower() == "exit":
        break

    messages.append({"role": "user", "content": user_input})

    # stream=True : la réponse arrive en fragments, pas d'un seul bloc.
    stream = ollama.chat(
        model="llama3.1:8b",
        messages=messages,
        stream=True,
    )

    print("Bot : ", end="", flush=True)

    # On doit reconstruire la réponse complète au fur et à mesure,
    # car on en aura besoin pour l'historique (le modèle ne nous
    # renvoie plus un texte fini, mais une suite de morceaux).
    bot_reply = ""

    for chunk in stream:
        # Chaque fragment contient un petit bout de texte.
        token = chunk["message"]["content"]

        # end="" : pas de retour à la ligne entre les fragments.
        # flush=True : on force l'affichage immédiat, sinon Python
        # garde le texte en mémoire tampon et tout sort d'un coup.
        print(token, end="", flush=True)

        # On accumule pour reconstituer la réponse entière.
        bot_reply += token

    print()  # un seul retour à la ligne, une fois la réponse terminée.

    messages.append({"role": "assistant", "content": bot_reply})