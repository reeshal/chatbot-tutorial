import ollama

# UNE seule liste, créée AVANT la boucle.
# Elle va accumuler tout l'historique de la conversation.
messages = []

while True:
    user_input = input("Vous : ")

    if user_input.lower() == "exit":
        break

    # On AJOUTE la question à l'historique (au lieu de repartir de zéro).
    messages.append({"role": "user", "content": user_input})

    # On envoie TOUT l'historique, pas seulement le dernier message.
    response = ollama.chat(
        model="llama3.1:8b",
        messages=messages,
    )

    # On récupère le texte de la réponse.
    bot_reply = response["message"]["content"]
    print("Bot :", bot_reply)

    # ÉTAPE CLÉ : on ajoute aussi la réponse du bot à l'historique,
    # avec le rôle "assistant". Sinon, au tour suivant, le modèle
    # ne saurait pas ce qu'il a lui-même répondu.
    messages.append({"role": "assistant", "content": bot_reply})