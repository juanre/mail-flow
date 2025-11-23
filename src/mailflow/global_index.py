import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Optional


@dataclass
class GlobalIndex:
    indexes_path: Path

    def __init__(self, indexes_path: str):
        self.indexes_path = Path(indexes_path).expanduser().resolve()
        self.indexes_path.mkdir(parents=True, exist_ok=True)
        self._init_dbs()

    @property
    def meta_db(self) -> Path:
        return self.indexes_path / "metadata.db"

    @property
    def fts_db(self) -> Path:
        return self.indexes_path / "fts.db"

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(str(self.meta_db))
        try:
            conn.row_factory = sqlite3.Row
            yield conn
        finally:
            conn.close()

    @contextmanager
    def _fts_conn(self):
        conn = sqlite3.connect(str(self.fts_db))
        try:
            conn.row_factory = sqlite3.Row
            yield conn
        finally:
            conn.close()

    def _init_dbs(self) -> None:
        # Metadata DB
        with self._conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS documents (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  entity TEXT NOT NULL,
                  date TEXT NOT NULL,
                  filename TEXT NOT NULL,
                  rel_path TEXT NOT NULL,
                  hash TEXT,
                  size INTEGER,
                  type TEXT NOT NULL,
                  source TEXT NOT NULL,
                  workflow TEXT,
                  category TEXT,
                  confidence REAL,
                  origin_json TEXT NOT NULL,
                  structured_json TEXT
                )
                """
            )
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS ux_documents_entity_rel ON documents(entity, rel_path)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS ix_documents_entity_date ON documents(entity, date)"
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS streams (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  entity TEXT NOT NULL,
                  kind TEXT NOT NULL,
                  channel_or_mailbox TEXT NOT NULL,
                  date TEXT NOT NULL,
                  rel_path TEXT NOT NULL,
                  origin_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS ux_streams_entity_rel ON streams(entity, rel_path)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS ix_streams_kind_channel ON streams(kind, channel_or_mailbox)"
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS links (
                  stream_id INTEGER NOT NULL,
                  document_id INTEGER NOT NULL,
                  PRIMARY KEY (stream_id, document_id)
                )
                """
            )
            conn.commit()

        # FTS DB
        with self._fts_conn() as conn:
            conn.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS pdf_search
                USING fts5(filename, email_subject, email_from, search_content)
                """
            )
            conn.commit()

    # Upserts
    def upsert_document(self, data: Dict[str, Any]) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO documents(entity, date, filename, rel_path, hash, size, type, source, workflow, category, confidence, origin_json, structured_json)
                VALUES(:entity, :date, :filename, :rel_path, :hash, :size, :type, :source, :workflow, :category, :confidence, :origin_json, :structured_json)
                ON CONFLICT(entity, rel_path) DO UPDATE SET
                  hash=excluded.hash,
                  size=excluded.size,
                  workflow=excluded.workflow,
                  category=excluded.category,
                  confidence=excluded.confidence,
                  origin_json=excluded.origin_json,
                  structured_json=excluded.structured_json
                """,
                data,
            )
            doc_id = cur.lastrowid or conn.execute(
                "SELECT id FROM documents WHERE entity=? AND rel_path=?",
                (data["entity"], data["rel_path"]),
            ).fetchone()[0]
            conn.commit()
            return int(doc_id)

    def upsert_stream(self, data: Dict[str, Any]) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO streams(entity, kind, channel_or_mailbox, date, rel_path, origin_json)
                VALUES(:entity, :kind, :channel_or_mailbox, :date, :rel_path, :origin_json)
                ON CONFLICT(entity, rel_path) DO UPDATE SET
                  origin_json=excluded.origin_json
                """,
                data,
            )
            sid = cur.lastrowid or conn.execute(
                "SELECT id FROM streams WHERE entity=? AND rel_path=?",
                (data["entity"], data["rel_path"]),
            ).fetchone()[0]
            conn.commit()
            return int(sid)

    def add_link(self, stream_id: int, document_id: int) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO links(stream_id, document_id) VALUES(?, ?)",
                (stream_id, document_id),
            )
            conn.commit()

    def upsert_fts(self, doc_id: int, filename: str, email_subject: str, email_from: str, search_content: str) -> None:
        with self._fts_conn() as conn:
            conn.execute(
                "DELETE FROM pdf_search WHERE rowid=?",
                (doc_id,),
            )
            conn.execute(
                "INSERT INTO pdf_search(rowid, filename, email_subject, email_from, search_content) VALUES(?,?,?,?,?)",
                (doc_id, filename, email_subject, email_from, search_content),
            )
            conn.commit()

    # Query
    def search(self, query: str, limit: int = 20, *, entity: Optional[str] = None, source: Optional[str] = None, workflow: Optional[str] = None, category: Optional[str] = None) -> Iterable[Dict[str, Any]]:
        if not query:
            with self._conn() as conn:
                sql = "SELECT * FROM documents"
                params: list[Any] = []
                clauses = []
                if entity:
                    clauses.append("entity=?")
                    params.append(entity)
                if source:
                    clauses.append("source=?")
                    params.append(source)
                if workflow:
                    clauses.append("workflow=?")
                    params.append(workflow)
                if category:
                    clauses.append("category=?")
                    params.append(category)
                if clauses:
                    sql += " WHERE " + " AND ".join(clauses)
                sql += " ORDER BY date DESC, id DESC LIMIT ?"
                params.append(limit)
                rows = conn.execute(sql, params)
                for r in rows:
                    yield dict(r)
            return

        with self._fts_conn() as fts, self._conn() as meta:
            rows = fts.execute(
                "SELECT rowid, bm25(pdf_search) AS score FROM pdf_search WHERE pdf_search MATCH ? ORDER BY score LIMIT ?",
                (query, limit),
            ).fetchall()
            if not rows:
                return

            for r in rows:
                doc_id = int(r["rowid"])
                clauses = ["id=?"]
                params: list[Any] = [doc_id]
                if entity:
                    clauses.append("entity=?")
                    params.append(entity)
                if source:
                    clauses.append("source=?")
                    params.append(source)
                if workflow:
                    clauses.append("workflow=?")
                    params.append(workflow)
                if category:
                    clauses.append("category=?")
                    params.append(category)

                sql = f"SELECT * FROM documents WHERE {' AND '.join(clauses)}"
                row = meta.execute(sql, params).fetchone()
                if row:
                    yield dict(row)
