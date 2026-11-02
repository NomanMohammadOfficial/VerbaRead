import json
import os
import time
import requests
from dotenv import load_dotenv
import db

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

URL = os.getenv("SUPABASE_URL", "").strip()
KEY = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
REMOTE = bool(URL and KEY)
REST = f"{URL}/rest/v1" if URL else ""

class StoreError(RuntimeError):
    pass

def backend():
    return "supabase" if REMOTE else "sqlite"

def target():
    return REST if REMOTE else db.DB_PATH

def now():
    return int(time.time())

def _headers(prefer=None):
    h = {
        "apikey": KEY,
        "Authorization": f"Bearer {KEY}",
        "Content-Type": "application/json"
    }
    if prefer:
        h["Prefer"] = prefer
    return h

def _check(response):
    if 200 <= response.status_code < 300:
        return
    snippet = response.text[:300] if response.text else ""
    raise StoreError(f"Supabase request failed: {response.status_code} {snippet}")

def _rest(method, table, params=None, payload=None, prefer=None, extra=None, return_raw=False):
    url = f"{REST}/{table}"
    if params:
        url += "?" + "&".join(f"{k}={v}" for k, v in params.items())
    headers = _headers(prefer)
    if extra:
        headers.update(extra)
    try:
        if method == "GET":
            r = requests.get(url, headers=headers, timeout=30)
        elif method == "POST":
            r = requests.post(url, headers=headers, json=payload, timeout=30)
        elif method == "PATCH":
            r = requests.patch(url, headers=headers, json=payload, timeout=30)
        elif method == "DELETE":
            r = requests.delete(url, headers=headers, timeout=30)
        else:
            raise ValueError(f"Unsupported method: {method}")
        _check(r)
        if return_raw:
            return r
        if r.headers.get("content-type", "").startswith("application/json") and r.text:
            return r.json()
        return None
    except requests.RequestException as e:
        raise StoreError(f"Network error: {e}")

def _fetch(table, params=None):
    return _rest("GET", table, params)

def _count(table, params=None):
    p = dict(params or {})
    p["select"] = "id"
    p["limit"] = "1"
    r = _rest("GET", table, p, prefer="count=exact", return_raw=True)
    content_range = r.headers.get("Content-Range", "")
    if "/" in content_range:
        total = content_range.split("/")[1].strip()
        if total != "*":
            try:
                return int(total)
            except ValueError:
                pass
    try:
        data = r.json()
        return len(data) if isinstance(data, list) else 0
    except Exception:
        return 0

LESSON_COLUMNS = "id,title,text,source_type,youtube_id,audio_url,cues_json,created_at,last_opened_at,position"
LESSON_FIELDS = ("title", "position", "last_opened_at")
WORD_FIELDS = ("lemma", "surface", "translation", "grammar", "status", "reps", "lapses", "ease", "interval_days", "due_at", "last_reviewed_at")

def lesson_list(limit=100):
    if REMOTE:
        params = {
            "select": LESSON_COLUMNS,
            "order": "last_opened_at.desc.nullslast,created_at.desc",
            "limit": str(limit)
        }
        return _fetch("lessons", params)
    else:
        return db.rows(
            "SELECT id, title, text, source_type, youtube_id, audio_url, cues_json, created_at, last_opened_at, position FROM lessons ORDER BY last_opened_at DESC NULLS LAST, created_at DESC LIMIT ?",
            (limit,)
        )

def lesson_get(lesson_id):
    if REMOTE:
        params = {"select": LESSON_COLUMNS, "id": f"eq.{lesson_id}"}
        rows = _fetch("lessons", params)
        return rows[0] if rows else None
    else:
        return db.row(
            "SELECT id, title, text, source_type, youtube_id, audio_url, cues_json, created_at, last_opened_at, position FROM lessons WHERE id = ?",
            (lesson_id,)
        )

def lesson_create(title, text, source_type, youtube_id=None, audio_url=None, cues_json=None):
    ts = now()
    if REMOTE:
        payload = {
            "title": title,
            "text": text,
            "source_type": source_type,
            "youtube_id": youtube_id,
            "audio_url": audio_url,
            "cues_json": cues_json,
            "created_at": ts
        }
        rows = _rest("POST", "lessons", payload=payload, prefer="return=representation")
        return rows[0] if rows else None
    else:
        db.execute(
            "INSERT INTO lessons (title, text, source_type, youtube_id, audio_url, cues_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (title, text, source_type, youtube_id, audio_url, cues_json, ts)
        )
        return db.row("SELECT id, title, text, source_type, youtube_id, audio_url, cues_json, created_at, last_opened_at, position FROM lessons WHERE id = last_insert_rowid()")

def lesson_update(lesson_id, **fields):
    filtered = {k: v for k, v in fields.items() if k in LESSON_FIELDS}
    if not filtered:
        return
    if REMOTE:
        filtered["updated_at"] = now()
        params = {"id": f"eq.{lesson_id}"}
        _rest("PATCH", "lessons", params, filtered, prefer="return=minimal")
    else:
        pairs = ", ".join(f"{k} = ?" for k in filtered.keys())
        db.execute(f"UPDATE lessons SET {pairs} WHERE id = ?", (*filtered.values(), lesson_id))

def lesson_delete(lesson_id):
    if REMOTE:
        params = {"id": f"eq.{lesson_id}"}
        _rest("DELETE", "lessons", params)
    else:
        db.execute("DELETE FROM lessons WHERE id = ?", (lesson_id,))

def lesson_total():
    if REMOTE:
        return _count("lessons")
    else:
        return db.row("SELECT COUNT(*) AS c FROM lessons")["c"]

def word_vocab():
    if REMOTE:
        params = {"select": "id,lemma,status"}
        rows = _fetch("words", params)
        return {r["lemma"]: r for r in rows}
    else:
        rows = db.rows("SELECT id, lemma, status FROM words")
        return {r["lemma"]: r for r in rows}

def word_table():
    if REMOTE:
        params = {"select": "id,lemma,surface,translation,grammar,status,ease,interval_days,reps,lapses,due_at,created_at,updated_at,last_reviewed_at"}
        rows = _fetch("words", params)
        return {r["lemma"]: r for r in rows}
    else:
        rows = db.rows("SELECT id, lemma, surface, translation, grammar, status, ease, interval_days, reps, lapses, due_at, created_at, updated_at, last_reviewed_at FROM words")
        return {r["lemma"]: r for r in rows}

def word_by_lemma(lemma):
    if REMOTE:
        params = {"select": "id,lemma,surface,translation,grammar,status,ease,interval_days,reps,lapses,due_at,created_at,updated_at,last_reviewed_at", "lemma": f"eq.{lemma}"}
        rows = _fetch("words", params)
        return rows[0] if rows else None
    else:
        return db.row("SELECT id, lemma, surface, translation, grammar, status, ease, interval_days, reps, lapses, due_at, created_at, updated_at, last_reviewed_at FROM words WHERE lemma = ?", (lemma,))

def word_by_id(word_id):
    if REMOTE:
        params = {"select": "id,lemma,surface,translation,grammar,status,ease,interval_days,reps,lapses,due_at,created_at,updated_at,last_reviewed_at", "id": f"eq.{word_id}"}
        rows = _fetch("words", params)
        return rows[0] if rows else None
    else:
        return db.row("SELECT id, lemma, surface, translation, grammar, status, ease, interval_days, reps, lapses, due_at, created_at, updated_at, last_reviewed_at FROM words WHERE id = ?", (word_id,))

def word_create(lemma, surface, translation, grammar):
    ts = now()
    if REMOTE:
        payload = {
            "lemma": lemma,
            "surface": surface,
            "translation": translation,
            "grammar": grammar,
            "status": 1,
            "due_at": ts,
            "created_at": ts
        }
        rows = _rest("POST", "words", payload=payload, prefer="return=representation")
        return rows[0] if rows else None
    else:
        db.execute(
            "INSERT INTO words (lemma, surface, translation, grammar, status, due_at, created_at) VALUES (?, ?, ?, ?, 1, ?, ?)",
            (lemma, surface, translation, grammar, ts, ts)
        )
        return db.row("SELECT id, lemma, surface, translation, grammar, status, ease, interval_days, reps, lapses, due_at, created_at, updated_at, last_reviewed_at FROM words WHERE id = last_insert_rowid()")

def word_update(word_id, **fields):
    filtered = {k: v for k, v in fields.items() if k in WORD_FIELDS}
    if not filtered:
        return
    if REMOTE:
        filtered["updated_at"] = now()
        # Ensure integer and float fields have matching types for Supabase
        for int_field in ("status", "reps", "lapses", "due_at", "last_reviewed_at"):
            if int_field in filtered and filtered[int_field] is not None:
                filtered[int_field] = int(filtered[int_field])
        for float_field in ("ease", "interval_days"):
            if float_field in filtered and filtered[float_field] is not None:
                filtered[float_field] = float(filtered[float_field])
        params = {"id": f"eq.{word_id}"}
        _rest("PATCH", "words", params, filtered, prefer="return=minimal")
    else:
        filtered["updated_at"] = now()
        pairs = ", ".join(f"{k} = ?" for k in filtered.keys())
        db.execute(f"UPDATE words SET {pairs} WHERE id = ?", (*filtered.values(), word_id))

def word_delete(word_id):
    if REMOTE:
        params = {"id": f"eq.{word_id}"}
        _rest("DELETE", "words", params)
    else:
        db.execute("DELETE FROM words WHERE id = ?", (word_id,))

def word_query(status=None, q=None, due=None, limit=100):
    if REMOTE:
        params = {"select": "id,lemma,surface,translation,grammar,status,ease,interval_days,reps,lapses,due_at,created_at,updated_at,last_reviewed_at", "limit": str(limit)}
        filters = []
        if status is not None:
            filters.append(f"status.eq.{status}")
        if q:
            filters.append(f"lemma.ilike.*{q}*")
        if due is not None:
            filters.append(f"or(due_at.is.null,due_at.lte.{due})")
        if len(filters) > 1:
            params["and"] = f"({','.join(filters)})"
        elif len(filters) == 1:
            parts = filters[0].split(".", 1)
            params[parts[0]] = parts[1] if len(parts) > 1 else ""
        return _fetch("words", params)
    else:
        conds = []
        args = []
        if status is not None:
            conds.append("status = ?")
            args.append(status)
        if q:
            conds.append("lemma LIKE ?")
            args.append(f"%{q}%")
        if due is not None:
            conds.append("(due_at IS NULL OR due_at <= ?)")
            args.append(due)
        where = " AND ".join(conds) if conds else "1"
        args.append(limit)
        return db.rows(f"SELECT id, lemma, surface, translation, grammar, status, ease, interval_days, reps, lapses, due_at, created_at, updated_at, last_reviewed_at FROM words WHERE {where} LIMIT ?", args)

def word_due():
    ts = now()
    if REMOTE:
        params = {
            "select": "id,lemma,surface,translation,status,reps",
            "order": "due_at.asc.nullsfirst,lemma.asc"
        }
        params["or"] = f"(due_at.is.null,due_at.lte.{ts})"
        return _fetch("words", params)
    else:
        return db.rows("SELECT id, lemma, surface, translation, status, reps FROM words WHERE due_at IS NULL OR due_at <= ? ORDER BY due_at ASC, lemma ASC", (ts,))

def word_status_counts():
    if REMOTE:
        rows = _fetch("words", {"select": "status"})
        counts = {}
        for r in rows:
            s = r["status"]
            counts[s] = counts.get(s, 0) + 1
        return counts
    else:
        rows = db.rows("SELECT status, COUNT(*) AS c FROM words GROUP BY status")
        return {r["status"]: r["c"] for r in rows}

def word_total():
    if REMOTE:
        return _count("words")
    else:
        return db.row("SELECT COUNT(*) AS c FROM words")["c"]

def word_due_total():
    ts = now()
    if REMOTE:
        params = {"or": f"(due_at.is.null,due_at.lte.{ts})"}
        return _count("words", params)
    else:
        return db.row("SELECT COUNT(*) AS c FROM words WHERE due_at IS NULL OR due_at <= ?", (ts,))["c"]

def word_all():
    if REMOTE:
        params = {"select": "id,lemma,surface,translation,grammar,status,ease,interval_days,reps,lapses,due_at,created_at,updated_at,last_reviewed_at"}
        return _fetch("words", params)
    else:
        return db.rows("SELECT id, lemma, surface, translation, grammar, status, ease, interval_days, reps, lapses, due_at, created_at, updated_at, last_reviewed_at FROM words")

def context_exists(word_id, sentence):
    if REMOTE:
        params = {"select": "id", "word_id": f"eq.{word_id}", "sentence": f"eq.{sentence}"}
        rows = _fetch("contexts", params)
        return bool(rows)
    else:
        return db.row("SELECT 1 FROM contexts WHERE word_id = ? AND sentence = ?", (word_id, sentence)) is not None

def context_add(word_id, lesson_id, sentence):
    ts = now()
    if REMOTE:
        payload = {"word_id": word_id, "lesson_id": lesson_id, "sentence": sentence, "created_at": ts}
        _rest("POST", "contexts", payload=payload, prefer="return=minimal")
    else:
        db.execute("INSERT INTO contexts (word_id, lesson_id, sentence, created_at) VALUES (?, ?, ?, ?)", (word_id, lesson_id, sentence, ts))

def context_recent(word_id, limit=3):
    if REMOTE:
        params = {
            "select": "sentence,lesson_id,lessons(title)",
            "word_id": f"eq.{word_id}",
            "order": "created_at.desc",
            "limit": str(limit)
        }
        rows = _fetch("contexts", params)
        for r in rows:
            if "lessons" in r and r["lessons"]:
                r["lesson_title"] = r["lessons"]["title"]
            del r["lessons"]
        return rows
    else:
        return db.rows("""
            SELECT c.sentence, c.lesson_id, l.title AS lesson_title
            FROM contexts c
            LEFT JOIN lessons l ON c.lesson_id = l.id
            WHERE c.word_id = ?
            ORDER BY c.created_at DESC
            LIMIT ?
        """, (word_id, limit))

def context_titles(word_id, limit=8):
    if REMOTE:
        params = {
            "select": "lesson_id,lessons(title)",
            "word_id": f"eq.{word_id}",
            "order": "created_at.desc",
            "limit": str(limit)
        }
        rows = _fetch("contexts", params)
        result = []
        for r in rows:
            if "lessons" in r and r["lessons"]:
                result.append({"lesson_id": r["lesson_id"], "lesson_title": r["lessons"]["title"]})
        return result
    else:
        return db.rows("""
            SELECT c.lesson_id, l.title AS lesson_title
            FROM contexts c
            LEFT JOIN lessons l ON c.lesson_id = l.id
            WHERE c.word_id = ?
            ORDER BY c.created_at DESC
            LIMIT ?
        """, (word_id, limit))

def context_latest(word_id):
    if REMOTE:
        params = {
            "select": "sentence",
            "word_id": f"eq.{word_id}",
            "order": "created_at.desc",
            "limit": "1"
        }
        rows = _fetch("contexts", params)
        return rows[0]["sentence"] if rows else None
    else:
        r = db.row("SELECT sentence FROM contexts WHERE word_id = ? ORDER BY created_at DESC LIMIT 1", (word_id,))
        return r["sentence"] if r else None

def context_count(word_id):
    if REMOTE:
        params = {"word_id": f"eq.{word_id}"}
        return _count("contexts", params)
    else:
        return db.row("SELECT COUNT(*) AS c FROM contexts WHERE word_id = ?", (word_id,))["c"]

def review_add(word_id, grade, interval_before, interval_after, reviewed_at):
    if REMOTE:
        payload = {
            "word_id": int(word_id),
            "grade": int(grade),
            "interval_before": float(interval_before),
            "interval_after": float(interval_after),
            "reviewed_at": int(reviewed_at),
        }
        _rest("POST", "reviews", payload=payload, prefer="return=minimal")
    else:
        db.execute(
            "INSERT INTO reviews (word_id, grade, interval_before, interval_after, reviewed_at) VALUES (?, ?, ?, ?, ?)",
            (word_id, grade, interval_before, interval_after, reviewed_at)
        )

def review_times_since(ts):
    if REMOTE:
        params = {
            "select": "reviewed_at",
            "reviewed_at": f"gte.{ts}",
            "order": "reviewed_at.asc",
            "limit": "100000"
        }
        rows = _fetch("reviews", params)
        return [r["reviewed_at"] for r in rows]
    else:
        rows = db.rows("SELECT reviewed_at FROM reviews WHERE reviewed_at >= ? ORDER BY reviewed_at ASC", (ts,))
        return [r["reviewed_at"] for r in rows]

def translation_get(text, target_lang):
    if REMOTE:
        params = {"select": "result", "source": f"eq.{text}", "target_lang": f"eq.{target_lang}"}
        rows = _fetch("translations", params)
        return rows[0]["result"] if rows else None
    else:
        r = db.row("SELECT result FROM translations WHERE source = ? AND target_lang = ?", (text, target_lang))
        return r["result"] if r else None

def translation_put(text, target_lang, result):
    ts = now()
    if REMOTE:
        payload = {"source": text, "target_lang": target_lang, "result": result, "created_at": ts}
        _rest("POST", "translations", payload=payload, prefer="resolution=merge-duplicates,return=minimal")
    else:
        db.execute("INSERT OR REPLACE INTO translations (source, target_lang, result, created_at) VALUES (?, ?, ?, ?)", (text, target_lang, result, ts))

def dictionary_get(lemma):
    if REMOTE:
        params = {"select": "payload", "lemma": f"eq.{lemma}"}
        rows = _fetch("dictionary_cache", params)
        return json.loads(rows[0]["payload"]) if rows else None
    else:
        r = db.row("SELECT payload FROM dictionary_cache WHERE lemma = ?", (lemma,))
        return json.loads(r["payload"]) if r else None

def dictionary_put(lemma, payload):
    ts = now()
    payload_str = json.dumps(payload, ensure_ascii=False)
    if REMOTE:
        p = {"lemma": lemma, "payload": payload_str, "created_at": ts}
        _rest("POST", "dictionary_cache", payload=p, prefer="resolution=merge-duplicates,return=minimal")
    else:
        db.execute("INSERT OR REPLACE INTO dictionary_cache (lemma, payload, created_at) VALUES (?, ?, ?)", (lemma, payload_str, ts))

def init():
    if REMOTE:
        probe = {
            "lessons": "id",
            "words": "id",
            "contexts": "id",
            "reviews": "id",
            "translations": "source",
            "dictionary_cache": "lemma"
        }
        for table, col in probe.items():
            try:
                params = {"select": col, "limit": "1"}
                _fetch(table, params)
            except StoreError as e:
                raise StoreError(f"Supabase table '{table}' not accessible. Run supabase/schema.sql in the Supabase SQL editor, or unset SUPABASE_URL and SUPABASE_SERVICE_KEY to use the local database.")
        if lesson_total() == 0:
            for lesson in db.SEED_LESSONS:
                title = lesson[0]
                existing = _fetch("lessons", {"select": "id", "title": f"eq.{title}", "limit": "1"})
                if not existing:
                    lesson_create(lesson[0], lesson[1], "text")
    else:
        db.init_db()
