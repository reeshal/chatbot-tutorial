"""
Persistance de l'historique de conversation — implémentation PostgreSQL.

Ce module définit :
  - ConversationStore        : le CONTRAT (Protocol) — l'équivalent Python d'une
                               interface. Tout stockage doit fournir load/save.
  - PostgresConversationStore : messages d'UNE conversation (load/save).
  - ConversationRepository    : CRUD sur la COLLECTION de conversations.

Nouveautés par rapport à la version SQLite :
  - le driver est `psycopg` (v3) et les connexions viennent d'un POOL partagé :
    une connexion Postgres est coûteuse, on ne la rouvre pas à chaque appel ;
  - le placeholder des requêtes est `%s` (et non `?`) ;
  - les clés étrangères sont ACTIVES par défaut sous Postgres : on déclare donc
    une vraie contrainte `ON DELETE CASCADE` et on laisse la base supprimer les
    messages d'une conversation effacée (plus de suppression manuelle).

ChatSession dépend du CONTRAT, pas d'une implémentation précise : passer de
SQLite à Postgres n'a demandé AUCUNE modification de ChatSession.
"""

import uuid
from datetime import datetime, timezone
from typing import Protocol

import psycopg
from psycopg_pool import ConnectionPool


# Titre par défaut d'une conversation tant qu'aucun message ne l'a nommée.
DEFAULT_TITLE: str = "Nouvelle conversation"


def _now() -> datetime:
    """Horodatage courant, en UTC. Stocké tel quel dans une colonne TIMESTAMPTZ
    (psycopg adapte automatiquement l'objet datetime)."""
    return datetime.now(timezone.utc)


# SQL de création des tables, partagé. Comme le store ET le repository touchent
# la même base, chacun garantit l'existence des tables (CREATE IF NOT EXISTS est
# idempotent). ORDRE IMPORTANT : `conversations` d'abord, car `messages` la
# référence par une clé étrangère.
_CREATE_CONVERSATIONS: str = """
    CREATE TABLE IF NOT EXISTS conversations (
        id          TEXT        PRIMARY KEY,
        title       TEXT        NOT NULL,
        updated_at  TIMESTAMPTZ NOT NULL
    )
"""

# `id` en IDENTITY (équivalent Postgres de l'AUTOINCREMENT SQLite).
# La clé étrangère ON DELETE CASCADE : supprimer une conversation efface
# automatiquement ses messages — la base s'en charge, plus de DELETE manuel.
_CREATE_MESSAGES: str = """
    CREATE TABLE IF NOT EXISTS messages (
        id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        conversation_id TEXT    NOT NULL
                        REFERENCES conversations(id) ON DELETE CASCADE,
        position        INTEGER NOT NULL,
        role            TEXT    NOT NULL,
        content         TEXT    NOT NULL
    )
"""


class ConversationStore(Protocol):
    """Contrat commun à tous les stockages de conversation.

    Un Protocol décrit les méthodes attendues SANS imposer d'héritage :
    n'importe quelle classe qui possède ces deux méthodes « est un »
    ConversationStore aux yeux du vérificateur de types. C'est l'équivalent
    structurel d'une interface (IConversationStore en .NET).
    """

    def load(self) -> list[dict[str, str]]:
        """Renvoie la conversation persistée (liste vide si aucune)."""
        ...

    def save(self, conversation: list[dict[str, str]]) -> None:
        """Persiste la conversation fournie."""
        ...


# ---------------------------------------------------------------------------
# Implémentation : base PostgreSQL
# ---------------------------------------------------------------------------
class PostgresConversationStore:
    """Persiste les messages d'UNE conversation dans PostgreSQL.

    Implémente le contrat ConversationStore (load / save) : ChatSession ne
    dépend que du contrat, jamais de cette classe directement.
    """

    def __init__(self, pool: ConnectionPool, conversation_id: str = "default") -> None:
        # Une connexion Postgres est chère : on partage un POOL plutôt que d'en
        # ouvrir une par opération (comme on le faisait avec le fichier SQLite).
        self._pool: ConnectionPool = pool
        # Identifie LA conversation gérée par cette instance de store.
        self._conversation_id: str = conversation_id
        self._initialize_schema()

    def _initialize_schema(self) -> None:
        """Crée les tables si elles n'existent pas (idempotent)."""
        with self._pool.connection() as conn:  # emprunt au pool ; commit en sortie
            conn.execute(_CREATE_CONVERSATIONS)
            conn.execute(_CREATE_MESSAGES)

    def load(self) -> list[dict[str, str]]:
        """Charge, dans l'ordre, les messages de CETTE conversation."""
        with self._pool.connection() as conn:
            rows = conn.execute(
                """
                SELECT role, content
                FROM messages
                WHERE conversation_id = %s
                ORDER BY position
                """,
                # Paramètre LIÉ (%s), jamais une f-string : c'est ce qui protège
                # contre l'injection SQL.
                (self._conversation_id,),
            ).fetchall()

        # Chaque ligne (role, content) redevient le dict attendu par ChatSession.
        return [{"role": role, "content": content} for role, content in rows]

    def save(self, conversation: list[dict[str, str]]) -> None:
        """Remplace les messages stockés de cette conversation.

        L'historique étant borné par la fenêtre glissante de ChatSession,
        « tout remplacer » reste peu coûteux. L'ensemble s'exécute dans UNE
        transaction : soit tout réussit, soit rien n'est modifié.
        """
        rows = [
            (self._conversation_id, position, message["role"], message["content"])
            for position, message in enumerate(conversation)
        ]

        with self._pool.connection() as conn:  # transaction : commit en sortie
            with conn.cursor() as cur:
                # On efface l'ancienne version de CETTE conversation seulement.
                cur.execute(
                    "DELETE FROM messages WHERE conversation_id = %s",
                    (self._conversation_id,),
                )
                # Puis on réinsère la version courante en un seul appel.
                cur.executemany(
                    """
                    INSERT INTO messages (conversation_id, position, role, content)
                    VALUES (%s, %s, %s, %s)
                    """,
                    rows,
                )
                # « Quand les messages ont-ils été écrits pour la dernière
                # fois ? » est un fait du moment de la sauvegarde : on met donc
                # à jour updated_at DANS LA MÊME transaction. La barre latérale
                # trie là-dessus, et cela garantit l'horodatage cohérent avec
                # les messages sans coupler ChatSession au catalogue.
                cur.execute(
                    "UPDATE conversations SET updated_at = %s WHERE id = %s",
                    (_now(), self._conversation_id),
                )


# ---------------------------------------------------------------------------
# Catalogue des conversations : la couche CRUD
# ---------------------------------------------------------------------------
class ConversationRepository:
    """CRUD sur la COLLECTION de conversations (la table `conversations`).

    Séparation des responsabilités :
      - PostgresConversationStore gère les MESSAGES d'UNE conversation ;
      - ConversationRepository gère l'ENSEMBLE des conversations (lister, créer,
        renommer, supprimer).

    C'est la distinction classique « agrégat » vs « repository » : un objet pour
    une entité, un objet pour la collection.
    """

    def __init__(self, pool: ConnectionPool) -> None:
        self._pool: ConnectionPool = pool
        self._initialize_schema()
        self._migrate()

    def _initialize_schema(self) -> None:
        with self._pool.connection() as conn:
            conn.execute(_CREATE_CONVERSATIONS)
            conn.execute(_CREATE_MESSAGES)

    def _migrate(self) -> None:
        """Migration de données, exécutée UNE fois au démarrage.

        Toute conversation présente dans `messages` mais absente du catalogue
        (typiquement un historique importé) reçoit ici sa ligne `conversations`.
        On le fait explicitement, et NON comme effet de bord d'un `list()` : une
        lecture ne doit jamais écrire. (Sur une base neuve, ne trouve rien.)
        """
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                orphans = cur.execute(
                    """
                    SELECT DISTINCT conversation_id
                    FROM messages
                    WHERE conversation_id NOT IN (SELECT id FROM conversations)
                    """
                ).fetchall()
                for (conversation_id,) in orphans:
                    title = self._derive_title(conn, conversation_id)
                    cur.execute(
                        "INSERT INTO conversations (id, title, updated_at) "
                        "VALUES (%s, %s, %s)",
                        (conversation_id, title or DEFAULT_TITLE, _now()),
                    )

    @staticmethod
    def _derive_title(conn: "psycopg.Connection", conversation_id: str) -> str | None:
        """Titre déduit du PREMIER message `user` de la conversation.

        Renvoie None si la conversation n'a encore aucun message utilisateur :
        l'appelant décide alors quoi faire (ne pas titrer, ou poser un défaut).
        """
        row = conn.execute(
            """
            SELECT content
            FROM messages
            WHERE conversation_id = %s AND role = 'user'
            ORDER BY position
            LIMIT 1
            """,
            (conversation_id,),
        ).fetchone()
        if row is None:
            return None
        text = row[0].strip()
        # Titre compact pour la barre latérale.
        return text[:40] + "…" if len(text) > 40 else text

    # ---- READ : lister (alimente la barre latérale) ----
    def list(self) -> list[dict[str, str]]:
        """Toutes les conversations, la plus récemment active en premier.

        Opération PUREMENT en lecture : aucun effet de bord (cf. _migrate)."""
        with self._pool.connection() as conn:
            rows = conn.execute(
                "SELECT id, title, updated_at FROM conversations "
                "ORDER BY updated_at DESC"
            ).fetchall()
        return [
            {"id": id_, "title": title, "updated_at": updated_at.isoformat()}
            for id_, title, updated_at in rows
        ]

    # ---- CREATE ----
    def create(self, title: str = DEFAULT_TITLE) -> str:
        """Crée une conversation vide et renvoie son identifiant (uuid)."""
        conversation_id: str = uuid.uuid4().hex
        with self._pool.connection() as conn:
            conn.execute(
                "INSERT INTO conversations (id, title, updated_at) "
                "VALUES (%s, %s, %s)",
                (conversation_id, title, _now()),
            )
        return conversation_id

    # ---- UPDATE : renommer ----
    def rename(self, conversation_id: str, title: str) -> bool:
        """Renomme une conversation. Renvoie False si l'id n'existe pas
        (l'appelant peut alors répondre 404)."""
        with self._pool.connection() as conn:
            cur = conn.execute(
                "UPDATE conversations SET title = %s WHERE id = %s",
                (title, conversation_id),
            )
            return cur.rowcount > 0

    # ---- DELETE ----
    def delete(self, conversation_id: str) -> bool:
        """Supprime la conversation. Ses messages partent automatiquement grâce
        à la contrainte ON DELETE CASCADE (Postgres applique les clés étrangères
        par défaut — contrairement à SQLite, où on supprimait à la main).

        Renvoie False si l'id n'existait pas."""
        with self._pool.connection() as conn:
            cur = conn.execute(
                "DELETE FROM conversations WHERE id = %s",
                (conversation_id,),
            )
            return cur.rowcount > 0

    def exists(self, conversation_id: str) -> bool:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT 1 FROM conversations WHERE id = %s",
                (conversation_id,),
            ).fetchone()
        return row is not None

    # ---- Titrage automatique ----
    def autotitle(self, conversation_id: str) -> None:
        """Donne à la conversation le titre de son premier message utilisateur.

        À appeler APRÈS la sauvegarde du tour (sinon le message n'est pas encore
        en base). Ne fait rien dans deux cas, par sécurité :
          - aucun message utilisateur encore présent (no-op gracieux : on évite
            d'écrire un titre vide si l'appel arrive trop tôt) ;
          - le titre a déjà été personnalisé (différent du défaut) : on ne
            l'écrase jamais.
        """
        with self._pool.connection() as conn:
            current = conn.execute(
                "SELECT title FROM conversations WHERE id = %s",
                (conversation_id,),
            ).fetchone()
            if current is None or current[0] != DEFAULT_TITLE:
                return  # inexistante, ou déjà titrée manuellement → on n'y touche pas
            title = self._derive_title(conn, conversation_id)
            if title is None:
                return  # pas encore de message utilisateur → no-op gracieux
            conn.execute(
                "UPDATE conversations SET title = %s WHERE id = %s",
                (title, conversation_id),
            )
