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
import store
import transcripts
from dictionary import lookup as dictionary_lookup
from explain import explain as explain_word
from nlp import analyze, cyrillic_ratio, tokenize
from translate import translate

app = FastAPI(title="RU Reader", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

store.init()


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
    lesson = store.lesson_get(lesson_id)
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")
    return lesson


def lesson_counts(text: str, vocab: dict[str, dict] | None = None) -> dict:
    vocab = vocab if vocab is not None else store.word_vocab()
    lemmas = {analyze(t["text"])["lemma"] for t in tokenize(text) if t["kind"] == "word"}
    total = len(lemmas)
    known = sum(1 for lemma in lemmas if vocab.get(lemma, {}).get("status", 0) >= 3)
    learning = sum(1 for lemma in lemmas if vocab.get(lemma, {}).get("status", 0) in (1, 2))
    return {"uniqueWords": total, "knownWords": known, "learningWords": learning, "newWords": max(0, total - known - learning)}


def add_context(word_id: int, lesson_id: int | None, sentence: str | None):
    sentence = (sentence or "").strip()
    if not sentence:
        return
    if not store.context_exists(word_id, sentence):
        store.context_add(word_id, lesson_id, sentence)


@app.get("/api/health")
def health():
    return {"ok": True, "db": store.target(), "store": store.backend()}


@app.get("/api/lessons")
def list_lessons():
    vocab = store.word_vocab()
    lessons = store.lesson_list()
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
    lesson = store.lesson_create(title, text, source_type, video, body.audio_url, cues_json)
    return {"id": lesson["id"], "title": title, "source_type": source_type, "youtube_id": video, "cues": len(cues or [])}


@app.get("/api/lessons/{lesson_id}")
def get_lesson(lesson_id: int):
    lesson = lesson_or_404(lesson_id)
    lesson["cues"] = json.loads(lesson["cues_json"]) if lesson["cues_json"] else []
    lesson.pop("cues_json", None)
    return lesson


@app.patch("/api/lessons/{lesson_id}")
def patch_lesson(lesson_id: int, body: LessonPatch):
    lesson_or_404(lesson_id)
    fields = {}
    if body.title is not None:
        fields["title"] = body.title.strip() or "Untitled"
    if body.position is not None:
        fields["position"] = max(0, body.position)
    if body.touched:
        fields["last_opened_at"] = store.now()
    if fields:
        store.lesson_update(lesson_id, **fields)
    return get_lesson(lesson_id)


@app.delete("/api/lessons/{lesson_id}")
def delete_lesson(lesson_id: int):
    lesson_or_404(lesson_id)
    store.lesson_delete(lesson_id)
    return {"ok": True}


@app.get("/api/lessons/{lesson_id}/reader")
def reader(lesson_id: int):
    lesson = lesson_or_404(lesson_id)
    vocab = store.word_table()
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
    word = store.word_by_lemma(lemma)
    is_new = False
    if not word:
        is_new = True
        translation = translate(lemma)["translation"] or None
        word = store.word_create(lemma, surface, translation, info["grammar"])
    elif not word.get("translation"):
        translation = translate(lemma)["translation"]
        if translation:
            store.word_update(word["id"], translation=translation)
            word = store.word_by_id(word["id"])
    add_context(word["id"], body.lesson_id, body.sentence)
    contexts = store.context_recent(word["id"], 3)
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
    vocab = store.word_vocab()
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
    word = store.word_by_lemma(text)
    is_new = False
    if body.save:
        if not word:
            is_new = True
            word = store.word_create(text, text, translation or None, None)
        elif not word.get("translation") and translation:
            store.word_update(word["id"], translation=translation)
            word = store.word_by_id(word["id"])
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
    due_ts = store.now() if due else None
    words = store.word_query(status=status, q=q, due=due_ts, limit=limit)
    for word in words:
        word["due_label"] = srs.label(word["interval_days"]) if word.get("due_at") else "new"
        word["context_count"] = store.context_count(word["id"])
    return words


@app.get("/api/words/{word_id}")
def get_word(word_id: int):
    word = store.word_by_id(word_id)
    if not word:
        raise HTTPException(status_code=404, detail="Word not found")
    word["contexts"] = store.context_titles(word_id, 8)
    word["due_label"] = srs.label(word["interval_days"]) if word.get("due_at") else "new"
    return word_payload(word) | {"contexts": word["contexts"]}


@app.patch("/api/words/{word_id}")
def patch_word(word_id: int, body: WordPatch):
    word = store.word_by_id(word_id)
    if not word:
        raise HTTPException(status_code=404, detail="Word not found")
    fields = {}
    if body.translation is not None:
        fields["translation"] = body.translation.strip()
    if body.grammar is not None:
        fields["grammar"] = body.grammar.strip()
    if body.status is not None:
        fields["status"] = max(0, min(4, body.status))
    if fields:
        store.word_update(word_id, **fields)
    return get_word(word_id)


@app.delete("/api/words/{word_id}")
def delete_word(word_id: int):
    if not store.word_by_id(word_id):
        raise HTTPException(status_code=404, detail="Word not found")
    store.word_delete(word_id)
    return {"ok": True}


@app.get("/api/practice/due")
def practice_due(limit: int = 20):
    limit = max(1, min(100, int(limit)))
    words = store.word_due()[:limit]
    ts = store.now()
    for word in words:
        sentence = store.context_latest(word["id"])
        word["context"] = sentence
        word["options"] = {
            str(grade): srs.label(srs.schedule(word, grade, ts)["interval_days"])
            for grade in (1, 2, 3, 4)
        }
    return {"due": len(words), "words": words}


@app.post("/api/practice/{word_id}")
def practice_grade(word_id: int, body: GradeIn):
    word = store.word_by_id(word_id)
    if not word:
        raise HTTPException(status_code=404, detail="Word not found")
    grade = max(1, min(4, body.grade))
    ts = store.now()
    plan = srs.schedule(word, grade, ts)
    store.word_update(
        word_id,
        ease=plan["ease"],
        interval_days=plan["interval_days"],
        reps=plan["reps"],
        lapses=plan["lapses"],
        due_at=plan["due_at"],
        status=plan["status"],
        last_reviewed_at=plan["last_reviewed_at"],
    )
    store.review_add(word_id, grade, float(word["interval_days"] or 0), plan["interval_days"], ts)
    updated = store.word_by_id(word_id)
    return {
        "word": word_payload(updated),
        "next_due": srs.label(plan["interval_days"]),
        "status": plan["status"],
    }


@app.get("/api/stats")
def stats():
    by_status = {str(i): 0 for i in range(5)}
    status_counts = store.word_status_counts()
    for status, count in status_counts.items():
        by_status[str(status)] = count
    total = sum(by_status.values())
    due = store.word_due_total()
    lessons = store.lesson_total()
    today = int(time.time())
    week_start = today - 6 * 86400
    review_times = store.review_times_since(week_start)
    reviews_by_day = []
    for offset in range(6, -1, -1):
        start = today - offset * 86400
        midnight = start - (start % 86400)
        count = sum(1 for t in review_times if midnight <= t < midnight + 86400)
        reviews_by_day.append({"day": midnight, "count": count})
    reviewed_today = reviews_by_day[-1]["count"] if reviews_by_day else 0
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
    words = store.word_all()
    lines = [
        "#separator:tab",
        "#html:true",
        "#columns:Word\tTranslation\tContext\tGrammar\tStatus",
    ]
    for word in words:
        sentence = store.context_latest(word["id"]) or ""
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
