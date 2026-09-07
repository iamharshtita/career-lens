"""
backend/storage/local_store.py

Local storage layer for CareerLens.

The Strands SDK (current version) does not ship LocalFileStorage,
TestMemoryStore, or SnapshotSessionManager.  This module provides
equivalent implementations built on stdlib (pathlib / json) and the
actual SDK class that *is* available: strands.session.FileSessionManager.

Module-level singletons
-----------------------
file_store              : LocalFileStorage   – JSON files on disk
memory_store            : TestMemoryStore    – in-process dict (tests / caching)
snapshot_session_manager: SnapshotSessionManager – persists agent session state
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from threading import Lock
from typing import Any

from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Resolve base directory from environment variable
# ---------------------------------------------------------------------------

BASE_DIR = Path(os.getenv("CAREERLENS_DATA_DIR", "./backend/data")).resolve()


# ---------------------------------------------------------------------------
# LocalFileStorage
# ---------------------------------------------------------------------------

class LocalFileStorage:
    """Simple key-value store that persists JSON objects on the local filesystem.

    Layout::

        <base_path>/
            <key>.json

    The ``key`` may contain ``/`` to create sub-directories implicitly.
    """

    def __init__(self, base_path: str | Path) -> None:
        self.base_path = Path(base_path).resolve()
        self.base_path.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Core read / write
    # ------------------------------------------------------------------

    def put(self, key: str, value: dict[str, Any]) -> None:
        """Serialize *value* to ``<base_path>/<key>.json`` atomically."""
        target = self._key_path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(".tmp")
        try:
            with tmp.open("w", encoding="utf-8", newline="\n") as fh:
                json.dump(value, fh, indent=2, ensure_ascii=False, default=str)
            tmp.replace(target)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise

    def get(self, key: str) -> dict[str, Any] | None:
        """Return the deserialized dict for *key*, or ``None`` if not found."""
        target = self._key_path(key)
        if not target.exists():
            return None
        with target.open("r", encoding="utf-8") as fh:
            return json.load(fh)  # type: ignore[return-value]

    def delete(self, key: str) -> bool:
        """Delete the file for *key*.  Returns ``True`` if it existed."""
        target = self._key_path(key)
        if target.exists():
            target.unlink()
            return True
        return False

    def list_keys(self, prefix: str = "") -> list[str]:
        """Return all keys (without the ``.json`` suffix) under *prefix*."""
        search_root = self.base_path / prefix if prefix else self.base_path
        if not search_root.exists():
            return []
        keys: list[str] = []
        for path in sorted(search_root.rglob("*.json")):
            # Reconstruct the key relative to base_path, strip .json
            rel = path.relative_to(self.base_path).with_suffix("")
            keys.append(str(rel))
        return keys

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _key_path(self, key: str) -> Path:
        return self.base_path / f"{key}.json"


# ---------------------------------------------------------------------------
# TestMemoryStore
# ---------------------------------------------------------------------------

class TestMemoryStore:
    """In-process thread-safe key-value store used for session memory and caching.

    Designed for local development and testing; state is lost when the process
    exits.
    """

    def __init__(self) -> None:
        self._store: dict[str, Any] = {}
        self._lock = Lock()

    def put(self, key: str, value: Any) -> None:
        """Store *value* under *key* (overwrites existing entry)."""
        with self._lock:
            self._store[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        """Return the value stored under *key*, or *default* if absent."""
        with self._lock:
            return self._store.get(key, default)

    def delete(self, key: str) -> bool:
        """Remove *key* from the store.  Returns ``True`` if it existed."""
        with self._lock:
            if key in self._store:
                del self._store[key]
                return True
            return False

    def clear(self) -> None:
        """Remove all entries (useful between test cases)."""
        with self._lock:
            self._store.clear()

    def keys(self) -> list[str]:
        """Return a snapshot of current keys."""
        with self._lock:
            return list(self._store.keys())


# ---------------------------------------------------------------------------
# SnapshotSessionManager
# ---------------------------------------------------------------------------

class SnapshotSessionManager:
    """Persists and restores arbitrary agent-state snapshots to the filesystem.

    Snapshots are stored as JSON files under *snapshot_dir*::

        <snapshot_dir>/
            <snapshot_id>.json

    The Strands SDK's ``FileSessionManager`` manages *conversation messages*;
    this class complements it by persisting arbitrary pipeline state (e.g.
    intermediate agent outputs) so long-running jobs survive process restarts.
    """

    def __init__(self, storage: LocalFileStorage, snapshot_dir: str | Path) -> None:
        self._storage = storage
        self._snapshot_dir = Path(snapshot_dir).resolve()
        self._snapshot_dir.mkdir(parents=True, exist_ok=True)
        # Relative key prefix used inside the shared LocalFileStorage
        self._prefix = str(self._snapshot_dir.relative_to(storage.base_path)) \
            if self._snapshot_dir.is_relative_to(storage.base_path) \
            else "snapshots"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def save_snapshot(self, snapshot_id: str, state: dict[str, Any]) -> None:
        """Persist *state* dict under *snapshot_id*."""
        target = self._snapshot_dir / f"{snapshot_id}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(".tmp")
        try:
            with tmp.open("w", encoding="utf-8", newline="\n") as fh:
                json.dump(state, fh, indent=2, ensure_ascii=False, default=str)
            tmp.replace(target)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise

    def restore_snapshot(self, snapshot_id: str) -> dict[str, Any] | None:
        """Return the previously saved state for *snapshot_id*, or ``None``."""
        target = self._snapshot_dir / f"{snapshot_id}.json"
        if not target.exists():
            return None
        with target.open("r", encoding="utf-8") as fh:
            return json.load(fh)  # type: ignore[return-value]

    def delete_snapshot(self, snapshot_id: str) -> bool:
        """Delete a snapshot.  Returns ``True`` if it existed."""
        target = self._snapshot_dir / f"{snapshot_id}.json"
        if target.exists():
            target.unlink()
            return True
        return False

    def list_snapshots(self) -> list[str]:
        """Return all snapshot IDs (without the ``.json`` suffix)."""
        if not self._snapshot_dir.exists():
            return []
        return sorted(
            p.stem
            for p in self._snapshot_dir.glob("*.json")
        )


# ---------------------------------------------------------------------------
# Module-level singletons
# ---------------------------------------------------------------------------

file_store = LocalFileStorage(base_path=str(BASE_DIR))

memory_store = TestMemoryStore()

snapshot_session_manager = SnapshotSessionManager(
    storage=file_store,
    snapshot_dir=str(BASE_DIR / "snapshots"),
)


# ---------------------------------------------------------------------------
# Directory helpers
# ---------------------------------------------------------------------------

def _ensure(path: Path) -> Path:
    """Create *path* if it does not exist and return it."""
    path.mkdir(parents=True, exist_ok=True)
    return path


def profiles_dir() -> Path:
    """Return (and create) the ``profiles/`` sub-directory under BASE_DIR."""
    return _ensure(BASE_DIR / "profiles")


def jobs_dir() -> Path:
    """Return (and create) the ``jobs/`` sub-directory under BASE_DIR."""
    return _ensure(BASE_DIR / "jobs")


def results_dir() -> Path:
    """Return (and create) the ``results/`` sub-directory under BASE_DIR."""
    return _ensure(BASE_DIR / "results")


def uploads_dir() -> Path:
    """Return (and create) the ``uploads/`` sub-directory under BASE_DIR."""
    return _ensure(BASE_DIR / "uploads")


def snapshots_dir() -> Path:
    """Return (and create) the ``snapshots/`` sub-directory under BASE_DIR."""
    return _ensure(BASE_DIR / "snapshots")


# ---------------------------------------------------------------------------
# JSON serialization helpers
# ---------------------------------------------------------------------------

def save_json(subdir: Path, key: str, data: BaseModel | dict[str, Any]) -> None:
    """Serialize a Pydantic model (or plain dict) to ``<subdir>/<key>.json``.

    Args:
        subdir: Target directory (use one of the ``*_dir()`` helpers).
        key:    Filename stem (e.g. a UUID).  Must not contain path separators.
        data:   A Pydantic ``BaseModel`` instance or a plain ``dict``.
    """
    subdir.mkdir(parents=True, exist_ok=True)
    target = subdir / f"{key}.json"
    tmp = target.with_suffix(".tmp")
    payload: dict[str, Any]
    if isinstance(data, BaseModel):
        payload = data.model_dump(mode="json")
    else:
        payload = data
    try:
        with tmp.open("w", encoding="utf-8", newline="\n") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False, default=str)
        tmp.replace(target)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def load_json(subdir: Path, key: str) -> dict[str, Any] | None:
    """Deserialize ``<subdir>/<key>.json`` to a dict.

    Returns ``None`` if the file does not exist.

    Args:
        subdir: Directory to look in (use one of the ``*_dir()`` helpers).
        key:    Filename stem used when the file was saved.
    """
    target = subdir / f"{key}.json"
    if not target.exists():
        return None
    with target.open("r", encoding="utf-8") as fh:
        return json.load(fh)  # type: ignore[return-value]
