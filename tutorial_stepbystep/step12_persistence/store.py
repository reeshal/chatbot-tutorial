"""
Persistance de l'historique de conversation.

Ce module définit :
  - ConversationStore     : le CONTRAT (Protocol) — l'équivalent Python d'une
                            interface. Tout stockage doit fournir load/save.
  - JsonConversationStore : implémentation fichier JSON (une conversation).
  - SQLiteConversationStore : implémentation base SQLite (N conversations).

ChatSession dépend du CONTRAT, pas d'une implémentation précise. On peut donc
remplacer le JSON par SQLite en changeant une seule ligne à la construction.
"""

import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Protocol


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
# Implémentation 1 : fichier JSON
# ---------------------------------------------------------------------------
class JsonConversationStore:
    """Sauvegarde une conversation au format JSON dans un fichier."""

    def __init__(self, path: str = "conversation.json") -> None:
        self._path: Path = Path(path)

    def load(self) -> list[dict[str, str]]:
        if not self._path.exists():
            return []
        try:
            with self._path.open("r", encoding="utf-8") as file:
                import json
                return json.load(file)
        except (ValueError, OSError):
            # Fichier corrompu ou illisible : on repart d'une conversation vide.
            return []

    def save(self, conversation: list[dict[str, str]]) -> None:
        import json
        # Écriture atomique : fichier temporaire puis renommage (os.replace).
        temp_path: Path = self._path.with_suffix(self._path.suffix + ".tmp")
        with temp_path.open("w", encoding="utf-8") as file:
            json.dump(conversation, file, ensure_ascii=False, indent=2)
        import os
        os.replace(temp_path, self._path)


# ---------------------------------------------------------------------------
# Implémentation 2 : base SQLite
# ---------------------------------------------------------------------------
class SQLiteConversationStore:
    """Persiste les conversations dans une base SQLite.

    Même interface que JsonConversationStore (load / save) : remplacement
    direct, ChatSession ne change pas.

    Avantages sur le JSON :
      - plusieurs conversations cohabitent dans un seul fichier de base,
        identifiées par `conversation_id` ;
      - les écritures sont transactionnelles (ACID) : plus besoin du
        renommage atomique manuel, SQLite garantit l'intégrité ;
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
        """Crée la table si elle n'existe pas (idempotent : sans effet si
        elle existe déjà)."""
        with closing(self._connect()) as connection:
            with connection:  # transaction
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS messages (
                        id              INTEGER PRIMARY KEY AUTOINCREMENT,
                        conversation_id TEXT    NOT NULL,
                        position        INTEGER NOT NULL,
                        role            TEXT    NOT NULL,
                        content         TEXT    NOT NULL
                    )
                    """
                )

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