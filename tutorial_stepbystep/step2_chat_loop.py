import ollama

# Boucle infinie : on continue de discuter tant que l'utilisateur ne quitte pas.
while True:
    # On lit ce que tape l'utilisateur.
    user_input = input("Vous : ")

    # Une porte de sortie : taper "exit" arrête la boucle.
    if user_input.lower() == "exit":
        break

    # Même appel qu'à l'étape 1, mais avec le texte saisi.
    response = ollama.chat(
        model="llama3.1:8b",
        messages=[
            {"role": "user", "content": user_input},
        ],
    )

    print("Bot :", response["message"]["content"])

#Vous : Je m'appelle Reeshal.
# Vous : Comment je m'appelle ?
# Bot : Je ne sais pas ... tu ne me l'as pas dit.
# It just forgot your name one line after you said it.
# Why? Look closely at the loop: every iteration builds a brand new messages list containing only the current input. The previous turn is thrown away. The model isn't being forgetful — we're literally handing it a blank slate every single time and asking it to respond to one isolated sentence.