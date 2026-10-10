import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from pydantic import ValidationError

from schema import SiteSchema


_SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS created_websites (
    id TEXT PRIMARY KEY CHECK (length(id) = 36),
    prompt TEXT NOT NULL,
    brand_name VARCHAR(255) NOT NULL,
    theme VARCHAR(32) NOT NULL,
    schema_json TEXT NOT NULL CHECK (
        json_valid(schema_json) AND json_type(schema_json) = 'object'
    ),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""


class SiteStorage:
    """Thread-safe SQLite persistence for generated SiteSchema websites."""

    def __init__(self, database_path: str | Path = "created_websites.sqlite3") -> None:
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(
            str(database_path),
            timeout=5.0,
            check_same_thread=False,
            isolation_level=None,
        )
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA busy_timeout = 5000")
        self._connection.execute("PRAGMA journal_mode = WAL")
        self._connection.execute(_SQLITE_SCHEMA)

    @staticmethod
    def _normalize_id(site_id: str | UUID) -> str:
        try:
            return str(UUID(str(site_id)))
        except (AttributeError, TypeError, ValueError) as error:
            raise ValueError("site_id must be a valid UUID") from error

    @staticmethod
    def _serialize_json(value: dict[str, Any]) -> str:
        try:
            return json.dumps(
                value,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            )
        except (TypeError, ValueError) as error:
            raise ValueError("value must contain only valid JSON data") from error

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="microseconds")

    @staticmethod
    def _decode_row(row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        result["schema_json"] = json.loads(result["schema_json"])
        return result

    def save_site(
        self,
        prompt: str,
        schema_json: dict[str, Any],
        site_id: str | UUID | None = None,
    ) -> str:
        """Validate and save a site, returning its UUID string."""
        if not isinstance(prompt, str):
            raise TypeError("prompt must be a string")
        if not isinstance(schema_json, dict):
            raise TypeError("schema_json must be a dict")

        validated_site = SiteSchema.model_validate(schema_json)
        serialized_site = self._serialize_json(schema_json)
        normalized_id = str(uuid4()) if site_id is None else self._normalize_id(site_id)
        timestamp = self._timestamp()

        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                self._connection.execute(
                    """INSERT INTO created_websites
                       (id, prompt, brand_name, theme, schema_json, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        normalized_id,
                        prompt,
                        validated_site.metadata.brand_name,
                        validated_site.metadata.theme,
                        serialized_site,
                        timestamp,
                        timestamp,
                    ),
                )
                self._connection.commit()
            except Exception:
                self._connection.rollback()
                raise

        return normalized_id

    def get_site(self, site_id: str | UUID) -> dict[str, Any] | None:
        """Return a site record, decoding schema_json, or None if it does not exist."""
        normalized_id = self._normalize_id(site_id)
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM created_websites WHERE id = ?",
                (normalized_id,),
            ).fetchone()
        return self._decode_row(row) if row is not None else None

    def update_site_section(
        self,
        site_id: str | UUID,
        section_type: str,
        new_data: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Atomically replace one validated section and return the updated site."""
        normalized_id = self._normalize_id(site_id)
        if section_type not in SiteSchema.model_fields:
            raise ValueError(f"Unknown SiteSchema section: {section_type}")
        if not isinstance(new_data, dict):
            raise TypeError("new_data must be a dict")

        section_model = SiteSchema.model_fields[section_type].annotation
        try:
            section_model.model_validate(new_data)
        except ValidationError as error:
            raise ValueError(f"new_data is invalid for section '{section_type}'") from error
        serialized_section = self._serialize_json(new_data)
        timestamp = self._timestamp()

        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                row = self._connection.execute(
                    "SELECT schema_json FROM created_websites WHERE id = ?",
                    (normalized_id,),
                ).fetchone()
                if row is None:
                    self._connection.rollback()
                    return None

                site = json.loads(row["schema_json"])
                if section_type not in site:
                    raise ValueError(f"Stored site has no '{section_type}' section")
                site[section_type] = json.loads(serialized_section)
                serialized_site = self._serialize_json(site)
                metadata = site["metadata"]

                self._connection.execute(
                    """UPDATE created_websites
                       SET brand_name = ?, theme = ?, schema_json = ?, updated_at = ?
                       WHERE id = ?""",
                    (
                        metadata["brand_name"],
                        metadata["theme"],
                        serialized_site,
                        timestamp,
                        normalized_id,
                    ),
                )
                self._connection.commit()
            except Exception:
                self._connection.rollback()
                raise

        return self.get_site(normalized_id)

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        with self._lock:
            self._connection.close()