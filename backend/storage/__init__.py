"""
backend/storage — local storage layer for CareerLens.

Exports the module-level singletons and helper functions defined in
``local_store`` so callers can simply do::

    from storage import file_store, memory_store, snapshot_session_manager
    from storage import profiles_dir, save_json, load_json
"""

from .local_store import (
    # Classes (re-exported so tests can instantiate fresh instances)
    LocalFileStorage,
    TestMemoryStore,
    SnapshotSessionManager,
    # Singletons
    file_store,
    memory_store,
    snapshot_session_manager,
    # Directory helpers
    profiles_dir,
    jobs_dir,
    results_dir,
    uploads_dir,
    snapshots_dir,
    # JSON helpers
    save_json,
    load_json,
    # Base directory constant
    BASE_DIR,
)

__all__ = [
    # Classes
    "LocalFileStorage",
    "TestMemoryStore",
    "SnapshotSessionManager",
    # Singletons
    "file_store",
    "memory_store",
    "snapshot_session_manager",
    # Directory helpers
    "profiles_dir",
    "jobs_dir",
    "results_dir",
    "uploads_dir",
    "snapshots_dir",
    # JSON helpers
    "save_json",
    "load_json",
    # Constant
    "BASE_DIR",
]
