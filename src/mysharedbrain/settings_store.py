"""Settings storage: the vault database, not a loose file.

The config the settings page shows is state, so it lives with the rest of the
vault's state in ``.brain/brain.db`` — one row holding the document as JSON.
Layering, lowest to highest:

1. model defaults,
2. the YAML seed file (``$BRAIN_CONFIG``, e.g. a mounted configmap),
3. this table — whatever the settings page last saved,
4. environment variables (``BRAIN__AGENT__MODEL``, secrets).

The file is never written: it is a starting point, so a read-only mount still
works. :meth:`SettingsStore.source` reports which layer is actually in play, and
the settings page shows it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

from mysharedbrain.db import Database

Source = Literal["database", "file", "defaults"]


@dataclass(frozen=True)
class StoredSettings:
    """The saved document plus when it was written."""

    document: dict[str, Any]
    updated_at: str


class SettingsStore:
    """Save/load the settings document for one vault."""

    def __init__(self, root: Path) -> None:
        self.db = Database(root)

    def get(self) -> StoredSettings | None:
        """The saved settings, or ``None`` when nothing has been saved yet."""
        with self.db.connection() as conn:
            row = conn.execute(
                "SELECT document, updated_at FROM settings WHERE id = 1"
            ).fetchone()
        if row is None:
            return None
        try:
            document: Any = json.loads(str(row["document"]))
        except json.JSONDecodeError:
            # A corrupt row must not brick the app: fall back to the seed file.
            return None
        if not isinstance(document, dict):
            return None
        return StoredSettings(
            document=cast("dict[str, Any]", document),
            updated_at=str(row["updated_at"]),
        )

    def document(self) -> dict[str, Any]:
        """The saved document as a settings source (``{}`` when unsaved)."""
        stored = self.get()
        return stored.document if stored else {}

    def save(self, document: dict[str, Any]) -> StoredSettings:
        """Replace the stored settings (one row, upserted)."""
        now = datetime.now(UTC).isoformat()
        payload = json.dumps(document, ensure_ascii=False)
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT INTO settings (id, document, updated_at) VALUES (1, ?, ?)"
                " ON CONFLICT(id) DO UPDATE SET document = excluded.document,"
                " updated_at = excluded.updated_at",
                (payload, now),
            )
        return StoredSettings(document=document, updated_at=now)

    def clear(self) -> None:
        """Forget the saved settings and fall back to the seed file."""
        with self.db.transaction() as conn:
            conn.execute("DELETE FROM settings WHERE id = 1")

    def source(self, seed_file: Path) -> Source:
        """Which layer is providing settings right now."""
        if self.get() is not None:
            return "database"
        return "file" if seed_file.is_file() else "defaults"
