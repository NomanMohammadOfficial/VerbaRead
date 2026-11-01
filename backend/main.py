import json
import os
import time
from typing import Literal

from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import srs
import transcripts
from db import DB_PATH, execute, init_db, now, row, rows
from dictionary import lookup as dictionary_lookup
from explain import explain as explain_word
from nlp import analyze, cyrillic_ratio, tokenize
from translate import translate

app = FastAPI(title="RU Reader", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:8000", "http://127.0.0.1:8000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()


class LessonIn(BaseModel):
    title: str | None = None
    text: str | None = None
    source_type: Literal["text", "youtube"] = "text"
    youtube_url: str | None = None
    audio_url: str | None = None
    cues: list[dict] | None = None


class LessonPatch(BaseModel):
    title: str | None = None
    position: int | None = None
    touched: bool = False


class LookupIn(BaseModel):
    word: str
    lesson_id: int | None = None
    sentence: str | None = None


class WordPatch(BaseModel):
    translation: str | None = None
    grammar: str | None = None
    status: int | None = None


class GradeIn(BaseModel):
    grade: int


class PhraseIn(BaseModel):
    phrase: str
    lesson_id: int | None = None
    sentence: str | None = None
    save: bool = True


class ExplainIn(BaseModel):
    word: str
    sentence: str | None = None
    translation: str | None = None


def word_payload(w: dict) -> dict:
    return {
        "id": w["id"],
        "lemma": w["lemma"],
        "surface": w.get("surface"),
        "translation": w.get("translation"),
        "grammar": w.get("grammar"),
        "status": w["status"],
        "reps": w["reps"],
        "lapses": w["lapses"],
        "ease": w["ease"],
        "interval_days": w["interval_days"],
        "due_at": w.get("due_at"),
        "due_label": srs.label(w["interval_days"]) if w.get("due_at") else "not studied",
        "created_at": w.get("created_at"),
    }


def lesson_or_404(lesson_id: int) -> dict:
    lesson = row("SELECT * FROM lessons WHERE id = ?", (lesson_id,))
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")
    return lesson


def lesson_counts(text: str, vocab: dict[str, dict] | None = None) -> dict:
    vocab = vocab if vocab is not None else {w["lemma"]: w for w in rows("SELECT id, lemma, status FROM words")}
    lemmas = {analyze(t["text"])["lemma"] for t in tokenize(text) if t["kind"] == "word"}
    total = len(lemmas)
    known = sum(1 for lemma in lemmas if vocab.get(lemma, {}).get("status", 0) >= 3)
    learning = sum(1 for lemma in lemmas if vocab.get(lemma, {}).get("status", 0) in (1, 2))
    return {"uniqueWords": total, "knownWords": known, "learningWords": learning, "newWords": max(0, total - known - learning)}


def add_context(word_id: int, lesson_id: int | None, sentence: str | None):
    sentence = (sentence or "").strip()
    if not sentence:
        return
    exists = row(
        "SELECT id FROM contexts WHERE word_id = ? AND sentence = ?",
        (word_id, sentence),
    )
    if not exists:
        execute(
            "INSERT INTO contexts (word_id, lesson_id, sentence, created_at) VALUES (?, ?, ?, ?)",
            (word_id, lesson_id, sentence, now()),
        )


@app.get("/api/health")
def health():
    return {"ok": True, "db": DB_PATH}


@app.get("/api/lessons")
def list_lessons():
    vocab = {w["lemma"]: w for w in rows("SELECT id, lemma, status FROM words")}
    lessons = rows(
        "SELECT id, title, text, source_type, youtube_id, audio_url, created_at, last_opened_at, position, cues_json FROM lessons ORDER BY COALESCE(last_opened_at, created_at) DESC"
    )
    result = []
    for lesson in lessons:
        stats = lesson_counts(lesson["text"], vocab)
        result.append(
            {
                "id": lesson["id"],
                "title": lesson["title"],
                "source_type": lesson["source_type"],
                "youtube_id": lesson["youtube_id"],
                "audio_url": lesson["audio_url"],
                "created_at": lesson["created_at"],
                "last_opened_at": lesson["last_opened_at"],
                "position": lesson["position"],
                "has_cues": bool(lesson["cues_json"]),
                "excerpt": lesson["text"][:180],
                **stats,
            }
        )
    return result


@app.post("/api/lessons", status_code=201)
def create_lesson(body: LessonIn):
    text = (body.text or "").strip()
    video = None
    cues = body.cues
    source_type = body.source_type

    if source_type == "youtube" or body.youtube_url:
        source_type = "youtube"
        video = transcripts.video_id(body.youtube_url or "") or transcripts.video_id(text)
        if not video:
            raise HTTPException(status_code=400, detail="Could not find a YouTube video id in that URL")
        if not cues:
            fetched = transcripts.fetch(video)
            cues = fetched.get("cues") or []
            if not text and cues:
                text = " ".join(cue["text"] for cue in cues)
        if cues and not text:
            text = " ".join(cue["text"] for cue in cues)
        if not text:
            raise HTTPException(
                status_code=422,
                detail="No transcript found for this video. Paste the Russian transcript text instead.",
            )
    if not text:
        raise HTTPException(status_code=422, detail="Lesson text is empty")
    if cyrillic_ratio(text) < 0.35:
        raise HTTPException(status_code=422, detail="This does not look like Russian text")

    title = (body.title or "").strip() or ("YouTube lesson" if source_type == "youtube" else text[:48] + ("…" if len(text) > 48 else ""))
    cues_json = json.dumps(cues, ensure_ascii=False) if cues else None
    cursor = execute(
        "INSERT INTO lessons (title, text, source_type, youtube_id, audio_url, cues_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (title, text, source_type, video, body.audio_url, cues_json, now()),
    )
    return {"id": cursor.lastrowid, "title": title, "source_type": source_type, "youtube_id": video, "cues": len(cues or [])}


@app.get("/api/lessons/{lesson_id}")
def get_lesson(lesson_id: int):
    lesson = lesson_or_404(lesson_id)
    lesson["cues"] = json.loads(lesson["cues_json"]) if lesson["cues_json"] else []
    lesson.pop("cues_json", None)
    return lesson


@app.patch("/api/lessons/{lesson_id}")
def patch_lesson(lesson_id: int, body: LessonPatch):
    lesson_or_404(lesson_id)
    if body.title is not None:
        execute("UPDATE lessons SET title = ? WHERE id = ?", (body.title.strip() or "Untitled", lesson_id))
    if body.position is not None:
        execute("UPDATE lessons SET position = ? WHERE id = ?", (max(0, body.position), lesson_id))
    if body.touched:
        execute("UPDATE lessons SET last_opened_at = ? WHERE id = ?", (now(), lesson_id))
    return get_lesson(lesson_id)


@app.delete("/api/lessons/{lesson_id}")
def delete_lesson(lesson_id: int):
    lesson_or_404(lesson_id)
    execute("DELETE FROM lessons WHERE id = ?", (lesson_id,))
    return {"ok": True}


@app.get("/api/lessons/{lesson_id}/reader")
def reader(lesson_id: int):
    lesson = lesson_or_404(lesson_id)
    vocab = {w["lemma"]: w for w in rows("SELECT * FROM words")}
    tokens = []
    for token in tokenize(lesson["text"]):
        if token["kind"] == "word":
            info = analyze(token["text"])
            word = vocab.get(info["lemma"])
            token.update(
                {
                    "lemma": info["lemma"],
                    "pos": info["pos"],
                    "grammar": info["grammar"],
                    "word_id": word["id"] if word else None,
                    "status": word["status"] if word else 0,
                    "translation": word["translation"] if word else None,
                }
            )
        tokens.append(token)
    lesson["cues"] = json.loads(lesson["cues_json"]) if lesson["cues_json"] else []
    lesson.pop("cues_json", None)
    stats = lesson_counts(lesson["text"], vocab)
    return {"lesson": lesson, "tokens": tokens, "stats": stats}


@app.post("/api/lookup")
def lookup(body: LookupIn):
    surface = body.word.strip()
    if not surface:
        raise HTTPException(status_code=422, detail="Word is empty")
    info = analyze(surface)
    lemma = info["lemma"]
    word = row("SELECT * FROM words WHERE lemma = ?", (lemma,))
    is_new = False
    if not word:
        is_new = True
        translation = translate(lemma)["translation"] or None
        cursor = execute(
            "INSERT INTO words (lemma, surface, translation, grammar, status, created_at, updated_at, due_at) VALUES (?, ?, ?, ?, 1, ?, ?, ?)",
            (lemma, surface, translation, info["grammar"], now(), now(), now()),
        )
        word = row("SELECT * FROM words WHERE id = ?", (cursor.lastrowid,))
    elif not word.get("translation"):
        translation = translate(lemma)["translation"]
        if translation:
            execute("UPDATE words SET translation = ?, updated_at = ? WHERE id = ?", (translation, now(), word["id"]))
            word = row("SELECT * FROM words WHERE id = ?", (word["id"],))
    add_context(word["id"], body.lesson_id, body.sentence)
    contexts = rows(
        "SELECT lesson_id, sentence FROM contexts WHERE word_id = ? ORDER BY id DESC LIMIT 3",
        (word["id"],),
    )
    payload = word_payload(word)
    payload.update(
        {
            "surface": surface,
            "pos": info["pos"],
            "tags": info["tags"],
            "is_new": is_new,
            "contexts": contexts,
        }
    )
    return payload


@app.get("/api/dictionary")
def dictionary(word: str, cache: bool = True):
    return dictionary_lookup(word, use_cache=cache)


@app.post("/api/explain")
def explain(body: ExplainIn):
    return explain_word(body.word, body.sentence or "", body.translation or "")


@app.post("/api/phrase")
def phrase(body: PhraseIn):
    text = (body.phrase or "").strip()
    if not text:
        raise HTTPException(status_code=422, detail="Phrase is empty")
    parts = [t for t in tokenize(text) if t["kind"] == "word"]
    if not parts:
        raise HTTPException(status_code=422, detail="Phrase has no Russian words")
    vocab = {w["lemma"]: w for w in rows("SELECT id, lemma, status FROM words")}
    words = []
    for part in parts:
        info = analyze(part["text"])
        known = vocab.get(info["lemma"])
        words.append(
            {
                "text": part["text"],
                "lemma": info["lemma"],
                "pos": info["pos"],
                "grammar": info["grammar"],
                "status": known["status"] if known else 0,
                "word_id": known["id"] if known else None,
            }
        )
    translation = translate(text)["translation"] or ""
    word = row("SELECT * FROM words WHERE lemma = ?", (text,))
    is_new = False
    if body.save:
        if not word:
            is_new = True
            cursor = execute(
                "INSERT INTO words (lemma, surface, translation, grammar, status, created_at, updated_at, due_at) VALUES (?, ?, ?, ?, 1, ?, ?, ?)",
                (text, text, translation or None, None, now(), now(), now()),
            )
            word = row("SELECT * FROM words WHERE id = ?", (cursor.lastrowid,))
        elif not word.get("translation") and translation:
            execute("UPDATE words SET translation = ?, updated_at = ? WHERE id = ?", (translation, now(), word["id"]))
            word = row("SELECT * FROM words WHERE id = ?", (word["id"],))
        add_context(word["id"], body.lesson_id, body.sentence)
    return {
        "phrase": text,
        "translation": translation,
        "lemma": text,
        "words": words,
        "word": word_payload(word) if word else None,
        "is_new": is_new,
    }


@app.get("/api/words")
def list_words(
    status: int | None = None,
    q: str | None = None,
    due: bool = False,
    limit: int = 500,
):
    limit = max(1, min(2000, int(limit)))
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
    words = rows(sql, params)
    for word in words:
        word["due_label"] = srs.label(word["interval_days"]) if word.get("due_at") else "new"
        word["context_count"] = row("SELECT COUNT(*) AS c FROM contexts WHERE word_id = ?", (word["id"],))["c"]
    return words


@app.get("/api/words/{word_id}")
def get_word(word_id: int):
    word = row("SELECT * FROM words WHERE id = ?", (word_id,))
    if not word:
        raise HTTPException(status_code=404, detail="Word not found")
    word["contexts"] = rows(
        "SELECT c.sentence, c.lesson_id, l.title FROM contexts c LEFT JOIN lessons l ON l.id = c.lesson_id WHERE c.word_id = ? ORDER BY c.id DESC LIMIT 8",
        (word_id,),
    )
    word["due_label"] = srs.label(word["interval_days"]) if word.get("due_at") else "new"
    return word_payload(word) | {"contexts": word["contexts"]}


@app.patch("/api/words/{word_id}")
def patch_word(word_id: int, body: WordPatch):
    word = row("SELECT * FROM words WHERE id = ?", (word_id,))
    if not word:
        raise HTTPException(status_code=404, detail="Word not found")
    if body.translation is not None:
        execute("UPDATE words SET translation = ?, updated_at = ? WHERE id = ?", (body.translation.strip(), now(), word_id))
    if body.grammar is not None:
        execute("UPDATE words SET grammar = ?, updated_at = ? WHERE id = ?", (body.grammar.strip(), now(), word_id))
    if body.status is not None:
        status = max(0, min(4, body.status))
        execute("UPDATE words SET status = ?, updated_at = ? WHERE id = ?", (status, now(), word_id))
    return get_word(word_id)


@app.delete("/api/words/{word_id}")
def delete_word(word_id: int):
    if not row("SELECT id FROM words WHERE id = ?", (word_id,)):
        raise HTTPException(status_code=404, detail="Word not found")
    execute("DELETE FROM words WHERE id = ?", (word_id,))
    return {"ok": True}


@app.get("/api/practice/due")
def practice_due(limit: int = 20):
    limit = max(1, min(100, int(limit)))
    words = rows(
        "SELECT * FROM words WHERE status >= 1 AND (due_at IS NULL OR due_at <= ?) ORDER BY CASE WHEN due_at IS NULL THEN 0 ELSE 1 END, due_at LIMIT ?",
        (now(), limit),
    )
    for word in words:
        contexts = rows(
            "SELECT sentence, lesson_id FROM contexts WHERE word_id = ? ORDER BY id DESC LIMIT 1",
            (word["id"],),
        )
        word["context"] = contexts[0]["sentence"] if contexts else None
        word["options"] = {
            str(grade): srs.label(srs.schedule(word, grade, now())["interval_days"])
            for grade in (1, 2, 3, 4)
        }
    return {"due": len(words), "words": words}


@app.post("/api/practice/{word_id}")
def practice_grade(word_id: int, body: GradeIn):
    word = row("SELECT * FROM words WHERE id = ?", (word_id,))
    if not word:
        raise HTTPException(status_code=404, detail="Word not found")
    grade = max(1, min(4, body.grade))
    plan = srs.schedule(word, grade, now())
    execute(
        "UPDATE words SET ease = ?, interval_days = ?, reps = ?, lapses = ?, due_at = ?, status = ?, last_reviewed_at = ?, updated_at = ? WHERE id = ?",
        (
            plan["ease"],
            plan["interval_days"],
            plan["reps"],
            plan["lapses"],
            plan["due_at"],
            plan["status"],
            plan["last_reviewed_at"],
            now(),
            word_id,
        ),
    )
    execute(
        "INSERT INTO reviews (word_id, grade, interval_before, interval_after, reviewed_at) VALUES (?, ?, ?, ?, ?)",
        (word_id, grade, float(word["interval_days"] or 0), plan["interval_days"], now()),
    )
    updated = row("SELECT * FROM words WHERE id = ?", (word_id,))
    return {
        "word": word_payload(updated),
        "next_due": srs.label(plan["interval_days"]),
        "status": plan["status"],
    }


@app.get("/api/stats")
def stats():
    by_status = {str(i): 0 for i in range(5)}
    for item in rows("SELECT status, COUNT(*) AS c FROM words GROUP BY status"):
        by_status[str(item["status"])] = item["c"]
    total = sum(by_status.values())
    due = row("SELECT COUNT(*) AS c FROM words WHERE status >= 1 AND (due_at IS NULL OR due_at <= ?)", (now(),))["c"]
    lessons = row("SELECT COUNT(*) AS c FROM lessons")["c"]
    reviews_by_day = []
    today = int(time.time())
    for offset in range(6, -1, -1):
        start = today - offset * 86400
        midnight = start - (start % 86400)
        count = row(
            "SELECT COUNT(*) AS c FROM reviews WHERE reviewed_at >= ? AND reviewed_at < ?",
            (midnight, midnight + 86400),
        )["c"]
        reviews_by_day.append({"day": midnight, "count": count})
    reviewed_today = row(
        "SELECT COUNT(*) AS c FROM reviews WHERE reviewed_at >= ?",
        (today - (today % 86400),),
    )["c"]
    return {
        "totalWords": total,
        "byStatus": by_status,
        "due": due,
        "lessons": lessons,
        "reviewedToday": reviewed_today,
        "reviewsByDay": reviews_by_day,
        "streakDays": sum(1 for day in reversed(reviews_by_day) if day["count"] > 0),
    }


@app.get("/api/translate")
def translate_endpoint(text: str, target: str = "en"):
    return translate(text, target=target)


@app.get("/api/youtube")
def youtube(url: str):
    found = transcripts.video_id(url)
    if not found:
        raise HTTPException(status_code=400, detail="Not a YouTube URL")
    return transcripts.fetch(found)


@app.get("/api/export/anki")
def export_anki():
    words = rows("SELECT * FROM words ORDER BY created_at")
    lines = [
        "#separator:tab",
        "#html:true",
        "#columns:Word\tTranslation\tContext\tGrammar\tStatus",
    ]
    for word in words:
        context = row(
            "SELECT sentence FROM contexts WHERE word_id = ? ORDER BY id DESC LIMIT 1",
            (word["id"],),
        )
        sentence = context["sentence"] if context else ""
        lines.append(
            "\t".join(
                [
                    word["lemma"],
                    (word.get("translation") or "").replace("\t", " ").replace("\n", " "),
                    sentence.replace("\t", " ").replace("\n", " "),
                    (word.get("grammar") or "").replace("\t", " "),
                    str(word["status"]),
                ]
            )
        )
    return Response(
        content="\n".join(lines),
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="russian-words.tsv"'},
    )


DIST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend", "dist")
if os.path.isdir(DIST):
    assets = os.path.join(DIST, "assets")
    if os.path.isdir(assets):
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        candidate = os.path.join(DIST, path)
        if path and os.path.isfile(candidate):
            return FileResponse(candidate)
        return FileResponse(os.path.join(DIST, "index.html"))
