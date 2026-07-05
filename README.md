# Chatbot Local — Tutoriel Python

Un chatbot local construit pas à pas, du script minimal jusqu'à une petite
application web avec persistance. Le modèle tourne en local via
[Ollama](https://ollama.com/) (`llama3.1:8b`) — aucune clé API requise.

## Progression

Chaque étape est autonome et ajoute une notion. Les étapes 1 à 15 vivent dans
`tutorial_stepbystep/` ; l'étape finale (`final/`) est à la
racine :

| Étape | Sujet |
|-------|-------|
| `step1`–`step5` | premier message, boucle, mémoire, streaming, gestion d'erreurs |
| `step6`–`step9` | classe `ChatSession`, fenêtre glissante, system prompt, options |
| `step10`–`step11` | générateurs, backend FastAPI |
| `step12_persistence` | persistance (JSON puis SQLite) |
| `step13_conversations_list` | liste de conversations + interface (SQLite) |
| `step14_postgres` | même app, stockage **PostgreSQL** + pgAdmin (Docker) |
| `step15_markdown_copy_stop_btn` | rendu **Markdown**, bouton **Arrêter**, bouton **Copier** + horodatage (côté client) |
| `final` | séparation **backend API** (FastAPI, CORS, SSE typé) / **frontend React** (Vite + TypeScript) |

L'architecture repose sur un contrat `ConversationStore` (Protocol) : passer de
SQLite à Postgres ne change pas une ligne de `ChatSession`.

## Lancer la dernière étape (final)

Deux projets séparés : l'API sur le port 8000, le frontend React sur le 5173
(autorisé via CORS ; `/chat` diffuse des évènements SSE `token`/`error`/`done`).

Terminal 1 — backend :

```bash
cd final/backend
docker compose up -d                     # PostgreSQL + pgAdmin
cd python                                # l'implémentation FastAPI
export DATABASE_URL=postgresql://chatbot:chatbot@localhost:5432/chatbot
pip install -r requirements.txt
uvicorn main:app --reload
```

Terminal 2 — frontend :

```bash
cd final/frontend
npm install
npm run dev
```

- Application : http://localhost:5173
- API : http://localhost:8000 (`VITE_API_URL` côté frontend et
  `FRONTEND_ORIGIN` côté backend pour changer les origins)
- pgAdmin : http://localhost:5050 (`admin@local.dev` / `admin`)

> Le `docker-compose.yml` de l'étape finale déclare `name: step14_postgres` : il
> pilote le MÊME projet compose que les étapes 14–15, donc les conteneurs et
> les données existants sont réutilisés tels quels.

> Les identifiants du `docker-compose.yml` sont des valeurs de développement
> local — à remplacer par un fichier `.env` (déjà ignoré par git) en production.

## Pré-requis

- Python 3.11+
- [Ollama](https://ollama.com/) avec le modèle : `ollama pull llama3.1:8b`
- Docker + Docker Compose (pour les étapes 14 à 16)
- Node.js 20+ (pour le frontend de l'étape finale)
