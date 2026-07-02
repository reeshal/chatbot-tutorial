# Chatbot Local — Tutoriel Python

Un chatbot local construit pas à pas, du script minimal jusqu'à une petite
application web avec persistance. Le modèle tourne en local via
[Ollama](https://ollama.com/) (`llama3.1:8b`) — aucune clé API requise.

## Progression

Chaque étape est autonome et ajoute une notion :

| Étape | Sujet |
|-------|-------|
| `step1`–`step5` | premier message, boucle, mémoire, streaming, gestion d'erreurs |
| `step6`–`step9` | classe `ChatSession`, fenêtre glissante, system prompt, options |
| `step10`–`step11` | générateurs, backend FastAPI |
| `step12_persistence` | persistance (JSON puis SQLite) |
| `step13_conversations_list` | liste de conversations + interface (SQLite) |
| `step14_postgres` | même app, stockage **PostgreSQL** + pgAdmin (Docker) |

L'architecture repose sur un contrat `ConversationStore` (Protocol) : passer de
SQLite à Postgres ne change pas une ligne de `ChatSession`.

## Lancer la dernière étape (step14, PostgreSQL)

```bash
cd step14_postgres
docker compose up -d                     # PostgreSQL + pgAdmin
export DATABASE_URL=postgresql://chatbot:chatbot@localhost:5432/chatbot
pip install -r requirements.txt
uvicorn server:app --reload
```

- Application : http://127.0.0.1:8000
- pgAdmin : http://localhost:5050 (`admin@local.dev` / `admin`)

> Les identifiants du `docker-compose.yml` sont des valeurs de développement
> local — à remplacer par un fichier `.env` (déjà ignoré par git) en production.

## Pré-requis

- Python 3.11+
- [Ollama](https://ollama.com/) avec le modèle : `ollama pull llama3.1:8b`
- Docker + Docker Compose (pour l'étape 14)
