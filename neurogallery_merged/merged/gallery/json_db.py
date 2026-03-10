"""
gallery/json_db.py
==================
Thread-safe JSON file storage engine for NeuroGallery.
Replaces MySQL / Django ORM for all app-specific data.

Each "table" is a plain JSON file inside BASE_DIR/data/:
  photos.json, albums.json, persons.json,
  tags.json, face_encodings.json, photo_similarities.json,
  user_profiles.json
"""

import json
import os
import threading
from datetime import datetime

from django.conf import settings

# ── Paths ──────────────────────────────────────────────────────────────────────
DATA_DIR = str(settings.JSON_DATA_DIR)
os.makedirs(DATA_DIR, exist_ok=True)

# ── Per-collection threading locks ────────────────────────────────────────────
_locks: dict = {}
_locks_meta = threading.Lock()


def _get_lock(collection: str) -> threading.Lock:
    with _locks_meta:
        if collection not in _locks:
            _locks[collection] = threading.Lock()
        return _locks[collection]


# ── File helpers ──────────────────────────────────────────────────────────────

def _path(collection: str) -> str:
    return os.path.join(DATA_DIR, f'{collection}.json')


def _load(collection: str) -> list:
    p = _path(collection)
    if not os.path.exists(p):
        return []
    with open(p, 'r', encoding='utf-8') as f:
        return json.load(f)


def _save(collection: str, data: list) -> None:
    with open(_path(collection), 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, default=str, ensure_ascii=False)


def _next_id(data: list) -> int:
    if not data:
        return 1
    return max(r['id'] for r in data) + 1


def _now() -> str:
    return datetime.now().isoformat()


# ── Public CRUD API ───────────────────────────────────────────────────────────

def get_all(collection: str) -> list:
    """Return all records from a collection."""
    return _load(collection)


def get_by_id(collection: str, id_: int):
    """Return the record with the given id, or None."""
    for item in _load(collection):
        if item['id'] == id_:
            return item
    return None


def filter_records(collection: str, **kwargs) -> list:
    """
    Return records matching ALL keyword filters.
    Supports exact match only (for complex filters use filter_fn).
    """
    results = _load(collection)
    for key, val in kwargs.items():
        results = [r for r in results if r.get(key) == val]
    return results


def filter_fn(collection: str, predicate) -> list:
    """Return records for which predicate(record) is True."""
    return [r for r in _load(collection) if predicate(r)]


def insert(collection: str, record: dict) -> dict:
    """Insert a new record; auto-assigns id and created_at. Returns the saved record."""
    lock = _get_lock(collection)
    with lock:
        data = _load(collection)
        record = dict(record)
        record['id'] = _next_id(data)
        if 'created_at' not in record:
            record['created_at'] = _now()
        data.append(record)
        _save(collection, data)
    return record


def update_record(collection: str, id_: int, **updates) -> None:
    """Update fields on the record with the given id."""
    lock = _get_lock(collection)
    with lock:
        data = _load(collection)
        for item in data:
            if item['id'] == id_:
                item.update(updates)
                break
        _save(collection, data)


def delete_record(collection: str, id_: int) -> None:
    """Delete the record with the given id."""
    lock = _get_lock(collection)
    with lock:
        data = _load(collection)
        data = [r for r in data if r['id'] != id_]
        _save(collection, data)


def delete_many(collection: str, predicate) -> int:
    """Delete all records matching predicate. Returns count deleted."""
    lock = _get_lock(collection)
    with lock:
        data = _load(collection)
        kept = [r for r in data if not predicate(r)]
        removed = len(data) - len(kept)
        _save(collection, kept)
    return removed


def bulk_update(collection: str, predicate, **updates) -> int:
    """Update fields on all records matching predicate. Returns count updated."""
    lock = _get_lock(collection)
    with lock:
        data = _load(collection)
        count = 0
        for item in data:
            if predicate(item):
                item.update(updates)
                count += 1
        _save(collection, data)
    return count


def upsert(collection: str, match: dict, record: dict) -> dict:
    """
    If a record matching all fields in `match` exists, return it.
    Otherwise insert `record` and return the new record.
    """
    lock = _get_lock(collection)
    with lock:
        data = _load(collection)
        for item in data:
            if all(item.get(k) == v for k, v in match.items()):
                return item, False
        record = dict(record)
        record['id'] = _next_id(data)
        if 'created_at' not in record:
            record['created_at'] = _now()
        data.append(record)
        _save(collection, data)
    return record, True


def count(collection: str, **kwargs) -> int:
    """Count records matching kwargs."""
    return len(filter_records(collection, **kwargs))


def exists(collection: str, **kwargs) -> bool:
    """Return True if any record matches kwargs."""
    for item in _load(collection):
        if all(item.get(k) == v for k, v in kwargs.items()):
            return True
    return False
