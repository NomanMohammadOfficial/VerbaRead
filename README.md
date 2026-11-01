# VerbaRead

A reading-first app for learning Russian: import your own texts or YouTube videos,
read along with synchronised audio, and turn every word you meet into long-term memory.

## What it does

- **Library** — paste Russian text or a YouTube link. Video lessons get a transcript
  with timed cues, so playback follows the words as they are spoken.
- **Reader** — click any word for its lemma, translation, dictionary entry and a short
  grammar explanation; drag across several words to translate a whole phrase.
  Word status is colour-coded from unknown to known.
- **Practice** — SM-2 spaced repetition over the words you saved, graded 1–4,
  with due counts and a daily streak.
- **Stats** — vocabulary growth, status breakdown and review history.
- **Anki export** — download the vocabulary list as a TSV for Anki.

## Stack

- Backend: FastAPI + Uvicorn, `pymorphy3` morphology, SQLite (Supabase-ready store layer)
- Frontend: React 19 + Vite, plain CSS
- Data sources: openrussian.org dictionary, Google/Wiktionary translation, YouTube timedtext

## Running locally

```bash
cd backend
python3 -m venv venv
./venv/bin/pip install fastapi "uvicorn[standard]" pymorphy3 pymorphy3-dicts-ru requests youtube-transcript-api
./venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000
```

The backend serves the built frontend from `frontend/dist`, so build it first:

```bash
cd frontend
npm install
npm run build
```

Then open <http://127.0.0.1:8000>.

For frontend development, run `npm run dev` (port 5173) alongside the backend; `/api`
is proxied to port 8000.

## Tests

```bash
cd frontend
node --test src/timing.test.js
npm run lint
```
