import json
import os
import time

import requests

import db

URL = (os.environ.get("SUPABASE_URL") or "").strip().rstrip("/")
KEY = (os.environ.get("SUPABASE_SERVICE_KEY") or os.environ.get("SUPABASE_KEY") or "").strip()
REMOTE = bool(URL and KEY)
REST = f"{URL}/rest/v1"

LESSON_COLUMNS = "id,title,text,source_type,youtube_id,audio_url,cues_json,created_at,last_opened_at,position"
LESSON_FIELDS = ("title", "position", "last_opened_at")
WORD_FIELDS = (
    "lemma",
    "surface",
    "translation",
    "grammar",
    "status",
    "reps",
    "lapses",
    "ease",
    "interval_days",
    "due_at",
    "last_reviewed_at",
)
TABLES = (
    ("lessons", "id"),
    ("words", "id"),
    ("contexts", "id"),
    ("reviews", "id"),
    ("translations", "source"),
    ("dictionary_cache", "lemma"),
)


class StoreError(RuntimeError):
    pass


def backend() -> str:
    return "supabase" if REMOTE else "sqlite"


def target() -> str:
    return URL if REMOTE else db.DB_PATH


def now() -> int:
    return int(time.time())


def _headers(prefer: str | None = None) -> dict:
    headers = {
        "apikey": KEY,
        "Authorization": f"Bearer {KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer
    return headers


def _check(response, table: str, method: str):
    if response.status_code < 400:
        return
    detail = (response.text or "").strip().replace("\n", " ")
    raise StoreError(f"{method} {table} failed with {response.status_code}: {detail[:280]}")


def _request(method: str, table: str, params=None, payload=None, prefer=None, headers=None):
    request_headers = _headers(prefer)
    if headers:
        request_headers.update(headers)
    try:
        response = requests.request(
            method,
            f"{REST}/{table}",
            headers=request_headers,
            params=params or {},
            json=payload,
            timeout=20,
        )
    except requests.RequestException as exc:
        raise StoreError(f"{method} {table} could not reach Supabase ({exc.__class__.__name__})") from exc
    _check(response, table, method)
    return response


def _rest(method: str, table: str, params=None, payload=None, prefer=None, headers=None):
    response = _request(method, table, params, payload, prefer, headers)
    if not response.content:
        return None
    try:
        return response.json()
    except ValueError:
        return None


def _fetch(table: str, params=None) -> list:
    return _rest("GET", table, params) or []


def _count(table: str, params=None, column: str = "id") -> int:
    query = dict(params or {})
    query["select"] = column
    response = _request("GET", table, query, headers={"Range": "0-0", "Prefer": "count=exact"})
    total = (response.headers.get("content-range") or "").split("/")[-1]
    return int(total) if total.isdigit() else 0


def init():
    if not REMOTE:
        db.init_db()
        return
    for table, column in TABLES:
        try:
            _fetch(table, {"select": column, "limit": "1"})
        except StoreError as exc:
            raise StoreError(
                f"Supabase table '{table}' is not ready: {exc}. "
                "Run supabase/schema.sql in the Supabase SQL editor, or unset SUPABASE_URL and "
                "SUPABASE_SERVICE_KEY to keep using the local database."
            ) from exc
    if lesson_total() == 0:
        for title, text in db.SEED_LESSONS:
            lesson_create(title, text, "text", None, None, None)


def lesson_list() -> list:
    if not REMOTE:
        return db.rows(
            f"SELECT {LESSON_COLUMNS} FROM lessons ORDER BY COALESCE(last_opened_at, created_at) DESC"
        )
    return _fetch(
        "lessons",
        {"select": LESSON_COLUMNS, "order": "last_opened_at.desc.nullslast,created_at.desc"},
    )


def lesson_get(lesson_id: int) -> dict | None:
    if not REMOTE:
        return db.row(f"SELECT {LESSON_COLUMNS} FROM lessons WHERE id = ?", (lesson_id,))
    found = _fetch("lessons", {"select": LESSON_COLUMNS, "id": f"eq.{lesson_id}", "limit": "1"})
    return found[0] if found else None


def lesson_create(title, text, source_type, youtube_id, audio_url, cues_json):
    created_at = now()
    payload = {
        "title": title,
        "text": text,
        "source_type": source_type,
        "youtube_id": youtube_id,
        "audio_url": audio_url,
        "cues_json": cues_json,
        "created_at": created_at,
    }
    if not REMOTE:
        cursor = db.execute(
            "INSERT INTO lessons (title, text, source_type, youtube_id, audio_url, cues_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (title, text, source_type, youtube_id, audio_url, cues_json, created_at),
        )
        return cursor.lastrowid
    created = _rest("POST", "lessons", None, payload, "return=representation")
    return created[0]["id"]


def lesson_update(lesson_id: int, **fields):
    allowed = {key: value for key, value in fields.items() if key in LESSON_FIELDS}
    if not allowed:
        return lesson_get(lesson_id)
    if not REMOTE:
        assignments = ", ".join(f"{key} = ?" for key in allowed)
        db.execute(f"UPDATE lessons SET {assignments} WHERE id = ?", (*allowed.values(), lesson_id))
        return lesson_get(lesson_id)
    updated = _rest("PATCH", "lessons", {"id": f"eq.{lesson_id}"}, allowed, "return=representation")
    return updated[0] if updated else lesson_get(lesson_id)


def lesson_delete(lesson_id: int):
    if not REMOTE:
        db.execute("DELETE FROM lessons WHERE id = ?", (lesson_id,))
        return
    _rest("DELETE", "lessons", {"id": f"eq.{lesson_id}"})


def lesson_total() -> int:
    if not REMOTE:
        return db.row("SELECT COUNT(*) AS c FROM lessons")["c"]
    return _count("lessons")


def word_vocab() -> dict:
    if not REMOTE:
        return {word["lemma"]: word for word in db.rows("SELECT id, lemma, status FROM words")}
    return {word["lemma"]: word for word in _fetch("words", {"select": "id,lemma,status"})}


def word_table() -> dict:
    if not REMOTE:
        return {word["lemma"]: word for word in db.rows("SELECT * FROM words")}
    return {word["lemma"]: word for word in _fetch("words", {"select": "*"})}


def word_by_lemma(lemma: str) -> dict | None:
    if not REMOTE:
        return db.row("SELECT * FROM words WHERE lemma = ?", (lemma,))
    found = _fetch("words", {"select": "*", "lemma": f"eq.{lemma}", "limit": "1"})
    return found[0] if found else None


def word_by_id(word_id: int) -> dict | None:
    if not REMOTE:
        return db.row("SELECT * FROM words WHERE id = ?", (word_id,))
    found = _fetch("words", {"select": "*", "id": f"eq.{word_id}", "limit": "1"})
    return found[0] if found else None


def word_create(lemma, surface, translation, grammar) -> dict:
    stamp = now()
    payload = {
        "lemma": lemma,
        "surface": surface,
        "translation": translation,
        "grammar": grammar,
        "status": 1,
        "created_at": stamp,
        "updated_at": stamp,
        "due_at": stamp,
    }
    if not REMOTE:
        cursor = db.execute(
            "INSERT INTO words (lemma, surface, translation, grammar, status, created_at, updated_at, due_at) "
            "VALUES (?, ?, ?, ?, 1, ?, ?, ?)",
            (lemma, surface, translation, grammar, stamp, stamp, stamp),
        )
        return word_by_id(cursor.lastrowid)
    created = _rest("POST", "words", None, payload, "return=representation")
    return created[0] if created else word_by_lemma(lemma)


def word_update(word_id: int, **fields) -> dict | None:
    allowed = {key: value for key, value in fields.items() if key in WORD_FIELDS}
    if not allowed:
        return word_by_id(word_id)
    allowed["updated_at"] = now()
    if not REMOTE:
        assignments = ", ".join(f"{key} = ?" for key in allowed)
        db.execute(f"UPDATE words SET {assignments} WHERE id = ?", (*allowed.values(), word_id))
        return word_by_id(word_id)
    updated = _rest("PATCH", "words", {"id": f"eq.{word_id}"}, allowed, "return=representation")
    return updated[0] if updated else word_by_id(word_id)


def word_delete(word_id: int):
    if not REMOTE:
        db.execute("DELETE FROM words WHERE id = ?", (word_id,))
        return
    _rest("DELETE", "words", {"id": f"eq.{word_id}"})


def word_query(status=None, q=None, due: bool = False, limit: int = 500) -> list:
    if not REMOTE:
        sql = "SELECT * FROM words WHERE 1=1"
        params: list = []
        if status is not None:
            sql += " AND status = ?"
            params.append(status)
        if q:
            sql += " AND (lemma LIKE ? OR translation LIKE ?)"
            params.extend([f"%{q}%", f"%{q}%"])
        if due:
            sql += " AND (due_at IS NULL OR due_at <= ?)"
            params.append(now())
        sql += " ORDER BY CASE WHEN due_at IS NULL THEN 0 ELSE 1 END, due_at, lemma LIMIT ?"
        params.append(limit)
        return db.rows(sql, params)
    params = {
        "select": "*",
        "order": "due_at.asc.nullsfirst,lemma.asc",
        "limit": str(limit),
    }
    if status is not None:
        params["status"] = f"eq.{status}"
    if q and due:
        params["and"] = (
            f"(or(lemma.ilike.*{q}*,translation.ilike.*{q}*),"
            f"or(due_at.is.null,due_at.lte.{now()}))"
        )
    elif q:
        params["or"] = f"(lemma.ilike.*{q}*,translation.ilike.*{q}*)"
    elif due:
        params["or"] = f"(due_at.is.null,due_at.lte.{now()})"
    return _fetch("words", params)


def word_due(limit: int = 20) -> list:
    if not REMOTE:
        return db.rows(
            "SELECT * FROM words WHERE status >= 1 AND (due_at IS NULL OR due_at <= ?) "
            "ORDER BY CASE WHEN due_at IS NULL THEN 0 ELSE 1 END, due_at LIMIT ?",
            (now(), limit),
        )
    return _fetch(
        "words",
        {
            "select": "*",
            "status": "gte.1",
            "or": f"(due_at.is.null,due_at.lte.{now()})",
            "order": "due_at.asc.nullsfirst,lemma.asc",
            "limit": str(limit),
        },
    )


def word_status_counts() -> dict:
    if not REMOTE:
        return {
            item["status"]: item["c"]
            for item in db.rows("SELECT status, COUNT(*) AS c FROM words GROUP BY status")
        }
    counts: dict = {}
    for item in _fetch("words", {"select": "status"}):
        counts[item["status"]] = counts.get(item["status"], 0) + 1
    return counts


def word_total() -> int:
    if not REMOTE:
        return db.row("SELECT COUNT(*) AS c FROM words")["c"]
    return _count("words")


def word_due_total() -> int:
    if not REMOTE:
        return db.row(
            "SELECT COUNT(*) AS c FROM words WHERE status >= 1 AND (due_at IS NULL OR due_at <= ?)",
            (now(),),
        )["c"]
    return _count("words", {"status": "gte.1", "or": f"(due_at.is.null,due_at.lte.{now()})"})


def word_all() -> list:
    if not REMOTE:
        return db.rows("SELECT * FROM words ORDER BY created_at")
    return _fetch("words", {"select": "*", "order": "created_at.asc"})


def context_exists(word_id: int, sentence: str) -> bool:
    if not REMOTE:
        return (
            db.row(
                "SELECT id FROM contexts WHERE word_id = ? AND sentence = ?",
                (word_id, sentence),
            )
            is not None
        )
    return bool(
        _fetch(
            "contexts",
            {"select": "id", "word_id": f"eq.{word_id}", "sentence": f"eq.{sentence}", "limit": "1"},
        )
    )


def context_add(word_id: int, lesson_id, sentence: str):
    created_at = now()
    if not REMOTE:
        db.execute(
            "INSERT INTO contexts (word_id, lesson_id, sentence, created_at) VALUES (?, ?, ?, ?)",
            (word_id, lesson_id, sentence, created_at),
        )
        return
    _rest(
        "POST",
        "contexts",
        None,
        {"word_id": word_id, "lesson_id": lesson_id, "sentence": sentence, "created_at": created_at},
        "return=minimal",
    )


def context_recent(word_id: int, limit: int = 3) -> list:
    if not REMOTE:
        return db.rows(
            "SELECT lesson_id, sentence FROM contexts WHERE word_id = ? ORDER BY id DESC LIMIT ?",
            (word_id, limit),
        )
    return _fetch(
        "contexts",
        {
            "select": "lesson_id,sentence",
            "word_id": f"eq.{word_id}",
            "order": "id.desc",
            "limit": str(limit),
        },
    )


def context_titles(word_id: int, limit: int = 8) -> list:
    if not REMOTE:
        return db.rows(
            "SELECT c.sentence, c.lesson_id, l.title FROM contexts c "
            "LEFT JOIN lessons l ON l.id = c.lesson_id WHERE c.word_id = ? ORDER BY c.id DESC LIMIT ?",
            (word_id, limit),
        )
    found = _fetch(
        "contexts",
        {
            "select": "sentence,lesson_id,lessons(title)",
            "word_id": f"eq.{word_id}",
            "order": "id.desc",
            "limit": str(limit),
        },
    )
    return [
        {
            "sentence": item.get("sentence"),
            "lesson_id": item.get("lesson_id"),
            "title": (item.get("lessons") or {}).get("title"),
        }
        for item in found
    ]


def context_latest(word_id: int) -> str | None:
    found = context_recent(word_id, 1)
    return found[0]["sentence"] if found else None


def context_count(word_id: int) -> int:
    if not REMOTE:
        return db.row("SELECT COUNT(*) AS c FROM contexts WHERE word_id = ?", (word_id,))["c"]
    return _count("contexts", {"word_id": f"eq.{word_id}"})


def review_add(word_id: int, grade: int, interval_before, interval_after, reviewed_at=None):
    stamp = reviewed_at or now()
    if not REMOTE:
        db.execute(
            "INSERT INTO reviews (word_id, grade, interval_before, interval_after, reviewed_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (word_id, grade, float(interval_before or 0), interval_after, stamp),
        )
        return
    _rest(
        "POST",
        "reviews",
        None,
        {
            "word_id": word_id,
            "grade": grade,
            "interval_before": float(interval_before or 0),
            "interval_after": interval_after,
            "reviewed_at": stamp,
        },
        "return=minimal",
    )


def review_times_since(start: int) -> list:
    if not REMOTE:
        return [
            item["reviewed_at"]
            for item in db.rows("SELECT reviewed_at FROM reviews WHERE reviewed_at >= ?", (start,))
        ]
    return [
        item["reviewed_at"]
        for item in _fetch("reviews", {"select": "reviewed_at", "reviewed_at": f"gte.{start}"})
    ]


def translation_get(source: str, target_lang: str = "en") -> str | None:
    if not REMOTE:
        found = db.row(
            "SELECT result FROM translations WHERE source = ? AND target_lang = ?",
            (source, target_lang),
        )
        return found["result"] if found else None
    found = _fetch(
        "translations",
        {
            "select": "result",
            "source": f"eq.{source}",
            "target_lang": f"eq.{target_lang}",
            "limit": "1",
        },
    )
    return found[0]["result"] if found else None


def translation_put(source: str, target_lang: str, result: str):
    created_at = now()
    if not REMOTE:
        db.execute(
            "INSERT OR REPLACE INTO translations (source, target_lang, result, created_at) VALUES (?, ?, ?, ?)",
            (source, target_lang, result, created_at),
        )
        return
    _rest(
        "POST",
        "translations",
        {"on_conflict": "source,target_lang"},
        {"source": source, "target_lang": target_lang, "result": result, "created_at": created_at},
        "resolution=merge-duplicates,return=minimal",
    )


def dictionary_get(lemma: str) -> dict | None:
    if not REMOTE:
        found = db.row("SELECT payload FROM dictionary_cache WHERE lemma = ?", (lemma,))
        return json.loads(found["payload"]) if found else None
    found = _fetch("dictionary_cache", {"select": "payload", "lemma": f"eq.{lemma}", "limit": "1"})
    return json.loads(found[0]["payload"]) if found else None


def dictionary_put(lemma: str, payload: str):
    created_at = now()
    if not REMOTE:
        db.execute(
            "INSERT OR REPLACE INTO dictionary_cache (lemma, payload, created_at) VALUES (?, ?, ?)",
            (lemma, payload, created_at),
        )
        return
    _rest(
        "POST",
        "dictionary_cache",
        {"on_conflict": "lemma"},
        {"lemma": lemma, "payload": payload, "created_at": created_at},
        "resolution=merge-duplicates,return=minimal",
    )
