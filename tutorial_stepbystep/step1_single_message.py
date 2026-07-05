import ollama

# On envoie une liste de messages au modèle.
# Chaque message a un "role" (qui parle) et un "content" (le texte).
response = ollama.chat(
    model="llama3.1:8b",
    messages=[
        {"role": "user", "content": "Bonjour, qui es-tu ?"},
    ],
)

# La réponse est un dictionnaire. Le texte du modèle se trouve ici :
print(response["message"]["content"])