"""
Persistance de l'historique de conversation.

Ce module définit :
  - ConversationStore     : le CONTRAT (Protocol) — l'équivalent Python d'une
                            interface. Tout stockage doit fournir load/save.
  - SQLiteConversationStore : implémentation base SQLite (N conversations).

ChatSession dépend du CONTRAT, pas d'une implémentation précise : on pourrait
fournir un autre stockage sans changer une ligne de ChatSession.
"""

import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone
from typing import Protocol


# Titre par défaut d'une conversation tant qu'aucun message ne l'a nommée.
DEFAULT_TITLE: str = "Nouvelle conversation"


def _now() -> str:
    """Horodatage ISO 8601 en UTC — du texte, donc triable directement en SQL."""
    return datetime.now(timezone.utc).isoformat()


# SQL de création des tables, partagé. Comme le store ET le repository touchent
# la même base, chacun garantit l'existence des DEUX tables : peu importe lequel
# est construit en premier, le schéma est toujours complet (CREATE IF NOT EXISTS
# est idempotent, donc sans effet si la table existe déjà).
_CREATE_MESSAGES: str = """
    CREATE TABLE IF NOT EXISTS messages (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        conversation_id TEXT    NOT NULL,
        position        INTEGER NOT NULL,
        role            TEXT    NOT NULL,
        content         TEXT    NOT NULL
    )
"""

# Table « catalogue » : une ligne par conversation. C'est elle qui alimente la
# barre latérale (titre + date), indépendamment des messages.
_CREATE_CONVERSATIONS: str = """
    CREATE TABLE IF NOT EXISTS conversations (
        id          TEXT PRIMARY KEY,
        title       TEXT NOT NULL,
        updated_at  TEXT NOT NULL
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
# Implémentation : base SQLite
# ---------------------------------------------------------------------------
class SQLiteConversationStore:
    """Persiste les conversations dans une base SQLite.

    Implémente le contrat ConversationStore (load / save) : ChatSession ne
    dépend que du contrat, jamais de cette classe directement.

    Atouts du stockage SQLite :
      - plusieurs conversations cohabitent dans un seul fichier de base,
        identifiées par `conversation_id` ;
      - les écritures sont transactionnelles (ACID) : SQLite garantit
        l'intégrité sans gestion manuelle ;
      - on peut interroger les données en SQL (chercher, lister, filtrer).
    """

    def __init__(
        self,
        db_path: str = "conversations.db",
        conversation_id: str = "default",
    ) -> None:
        self._db_path: str = db_path
        # Identifie LA conversation gérée par cette instance de store.
        self._conversation_id: str = conversation_id
        self._initialize_schema()

    def _connect(self) -> sqlite3.Connection:
        """Ouvre une connexion. Une connexion par opération : c'est simple
        et sûr vis-à-vis des threads (FastAPI peut exécuter les handlers
        dans des threads différents ; une connexion n'est pas partagée)."""
        return sqlite3.connect(self._db_path)

    def _initialize_schema(self) -> None:
        """Crée les tables si elles n'existent pas (idempotent : sans effet si
        elles existent déjà)."""
        with closing(self._connect()) as connection:
            with connection:  # transaction
                connection.execute(_CREATE_MESSAGES)
                connection.execute(_CREATE_CONVERSATIONS)

    def load(self) -> list[dict[str, str]]:
        """Charge, dans l'ordre, les messages de CETTE conversation."""
        with closing(self._connect()) as connection:
            cursor = connection.execute(
                """
                SELECT role, content
                FROM messages
                WHERE conversation_id = ?
                ORDER BY position
                """,
                # Paramètre LIÉ (?), jamais une f-string : c'est ce qui
                # protège contre l'injection SQL.
                (self._conversation_id,),
            )
            rows = cursor.fetchall()

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

        with closing(self._connect()) as connection:
            with connection:  # transaction : commit en sortie, rollback si erreur
                # On efface l'ancienne version de CETTE conversation seulement.
                connection.execute(
                    "DELETE FROM messages WHERE conversation_id = ?",
                    (self._conversation_id,),
                )
                # Puis on réinsère la version courante en un seul appel.
                connection.executemany(
                    """
                    INSERT INTO messages (conversation_id, position, role, content)
                    VALUES (?, ?, ?, ?)
                    """,
                    rows,
                )
                # « Quand les messages ont-ils été écrits pour la dernière
                # fois ? » est un fait du moment de la sauvegarde : on met donc
                # à jour updated_at DANS LA MÊME transaction. La barre latérale
                # trie là-dessus, et cela garantit l'horodatage cohérent avec
                # les messages sans coupler ChatSession au catalogue.
                connection.execute(
                    "UPDATE conversations SET updated_at = ? WHERE id = ?",
                    (_now(), self._conversation_id),
                )


# ---------------------------------------------------------------------------
# Catalogue des conversations : la couche CRUD
# ---------------------------------------------------------------------------
class ConversationRepository:
    """CRUD sur la COLLECTION de conversations (la table `conversations`).

    Séparation des responsabilités :
      - SQLiteConversationStore gère les MESSAGES d'UNE conversation (load/save) ;
      - ConversationRepository gère l'ENSEMBLE des conversations (lister, créer,
        renommer, supprimer).

    C'est la distinction classique « agrégat » vs « repository » : un objet pour
    une entité, un objet pour la collection.
    """

    def __init__(self, db_path: str = "conversations.db") -> None:
        self._db_path: str = db_path
        self._initialize_schema()
        self._migrate()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path)

    def _initialize_schema(self) -> None:
        with closing(self._connect()) as connection:
            with connection:
                connection.execute(_CREATE_MESSAGES)
                connection.execute(_CREATE_CONVERSATIONS)

    def _migrate(self) -> None:
        """Migration de données, exécutée UNE fois au démarrage.

        Toute conversation présente dans `messages` mais absente du catalogue
        (typiquement un historique créé AVANT cette fonctionnalité) reçoit ici
        sa ligne `conversations`. On le fait explicitement, et NON comme effet
        de bord d'un `list()` : une lecture ne doit jamais écrire.
        """
        with closing(self._connect()) as connection:
            with connection:
                orphans = connection.execute(
                    """
                    SELECT DISTINCT conversation_id
                    FROM messages
                    WHERE conversation_id NOT IN (SELECT id FROM conversations)
                    """
                ).fetchall()
                for (conversation_id,) in orphans:
                    title = self._derive_title(connection, conversation_id)
                    connection.execute(
                        "INSERT INTO conversations (id, title, updated_at) "
                        "VALUES (?, ?, ?)",
                        (conversation_id, title or DEFAULT_TITLE, _now()),
                    )

    @staticmethod
    def _derive_title(connection: sqlite3.Connection, conversation_id: str) -> str | None:
        """Titre déduit du PREMIER message `user` de la conversation.

        Renvoie None si la conversation n'a encore aucun message utilisateur :
        l'appelant décide alors quoi faire (ne pas titrer, ou poser un défaut).
        """
        row = connection.execute(
            """
            SELECT content
            FROM messages
            WHERE conversation_id = ? AND role = 'user'
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
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT id, title, updated_at FROM conversations "
                "ORDER BY updated_at DESC"
            ).fetchall()
        return [
            {"id": id_, "title": title, "updated_at": updated_at}
            for id_, title, updated_at in rows
        ]

    # ---- CREATE ----
    def create(self, title: str = DEFAULT_TITLE) -> str:
        """Crée une conversation vide et renvoie son identifiant (uuid)."""
        conversation_id: str = uuid.uuid4().hex
        with closing(self._connect()) as connection:
            with connection:
                connection.execute(
                    "INSERT INTO conversations (id, title, updated_at) "
                    "VALUES (?, ?, ?)",
                    (conversation_id, title, _now()),
                )
        return conversation_id

    # ---- UPDATE : renommer ----
    def rename(self, conversation_id: str, title: str) -> bool:
        """Renomme une conversation. Renvoie False si l'id n'existe pas
        (l'appelant peut alors répondre 404)."""
        with closing(self._connect()) as connection:
            with connection:
                cursor = connection.execute(
                    "UPDATE conversations SET title = ? WHERE id = ?",
                    (title, conversation_id),
                )
            return cursor.rowcount > 0

    # ---- DELETE ----
    def delete(self, conversation_id: str) -> bool:
        """Supprime la conversation ET ses messages, dans UNE transaction.

        Renvoie False si l'id n'existait pas. Suppression manuelle en cascade :
        les clés étrangères de SQLite sont désactivées par défaut, donc rien au
        niveau base ne supprimerait les messages à notre place."""
        with closing(self._connect()) as connection:
            with connection:
                connection.execute(
                    "DELETE FROM messages WHERE conversation_id = ?",
                    (conversation_id,),
                )
                cursor = connection.execute(
                    "DELETE FROM conversations WHERE id = ?",
                    (conversation_id,),
                )
            return cursor.rowcount > 0

    def exists(self, conversation_id: str) -> bool:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT 1 FROM conversations WHERE id = ?",
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
        with closing(self._connect()) as connection:
            with connection:
                current = connection.execute(
                    "SELECT title FROM conversations WHERE id = ?",
                    (conversation_id,),
                ).fetchone()
                if current is None or current[0] != DEFAULT_TITLE:
                    return  # inexistante, ou déjà titrée manuellement → on n'y touche pas
                title = self._derive_title(connection, conversation_id)
                if title is None:
                    return  # pas encore de message utilisateur → no-op gracieux
                connection.execute(
                    "UPDATE conversations SET title = ? WHERE id = ?",
                    (title, conversation_id),
                )