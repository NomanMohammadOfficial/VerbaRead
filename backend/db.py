import os
import sqlite3
import threading
import time

DB_PATH = os.environ.get(
    "RU_READER_DB", os.path.join(os.path.dirname(os.path.abspath(__file__)), "ru_reader.db")
)

_local = threading.local()

SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS lessons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    text TEXT NOT NULL,
    source_type TEXT NOT NULL DEFAULT 'text',
    youtube_id TEXT,
    audio_url TEXT,
    cues_json TEXT,
    created_at INTEGER NOT NULL,
    last_opened_at INTEGER,
    position INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS words (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lemma TEXT NOT NULL UNIQUE,
    surface TEXT,
    translation TEXT,
    grammar TEXT,
    status INTEGER NOT NULL DEFAULT 1,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    reps INTEGER NOT NULL DEFAULT 0,
    lapses INTEGER NOT NULL DEFAULT 0,
    ease REAL NOT NULL DEFAULT 2.5,
    interval_days REAL NOT NULL DEFAULT 0,
    due_at INTEGER,
    last_reviewed_at INTEGER
);
CREATE INDEX IF NOT EXISTS idx_words_status ON words(status);
CREATE INDEX IF NOT EXISTS idx_words_due ON words(due_at);

CREATE TABLE IF NOT EXISTS contexts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    word_id INTEGER NOT NULL REFERENCES words(id) ON DELETE CASCADE,
    lesson_id INTEGER REFERENCES lessons(id) ON DELETE SET NULL,
    sentence TEXT NOT NULL,
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_contexts_word ON contexts(word_id);

CREATE TABLE IF NOT EXISTS reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    word_id INTEGER NOT NULL REFERENCES words(id) ON DELETE CASCADE,
    grade INTEGER NOT NULL,
    interval_before REAL NOT NULL,
    interval_after REAL NOT NULL,
    reviewed_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_reviews_time ON reviews(reviewed_at);

CREATE TABLE IF NOT EXISTS translations (
    source TEXT NOT NULL,
    target_lang TEXT NOT NULL,
    result TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    PRIMARY KEY (source, target_lang)
);

CREATE TABLE IF NOT EXISTS dictionary_cache (
    lemma TEXT NOT NULL,
    payload TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    PRIMARY KEY (lemma)
);
"""

SEED_LESSONS = [
    (
        "В гостях у бабушки",
        "В субботу я поехал к бабушке в деревню. Дорога была долгой, но красивой. "
        "За окном автобуса мелькали поля, леса и маленькие дома. Бабушка встретила меня "
        "на пороге и крепко обняла. На столе уже стоял горячий чай, пирог с яблоками и "
        "варенье из малины. Мы долго разговаривали о моей работе и о её саде. Бабушка "
        "рассказала, что лето было тёплым и урожай в этом году очень хороший. После обеда "
        "мы пошли гулять по деревне. Я помог ей полить грядки и собрать яблоки. Вечером "
        "стало прохладно, и мы вернулись домой. Я лёг спать рано, потому что устал, но "
        "было очень приятно слышать тишину и чувствовать запах лета.",
    ),
    (
        "Мой обычный день",
        "Меня зовут Анна, и я живу в Москве. Каждое утро я встаю в семь часов, "
        "делаю зарядку и завтракаю. Обычно я ем кашу и пью кофе. Потом я иду на работу "
        "на метро. Моя работа находится в центре города, в большом офисе. Я работаю "
        "программистом и пишу код для разных проектов. В обед мы с коллегами идём в кафе "
        "или гуляем в парке. После работы я часто захожу в магазин за продуктами. Дома я "
        "готовлю ужин, читаю книгу или смотрю сериал. Иногда я встречаюсь с друзьями, и мы "
        "идём в кино. В выходные я стараюсь больше отдыхать и проводить время на свежем "
        "воздухе. Мне нравится моя жизнь, хотя иногда она кажется слишком быстрой.",
    ),
]


def get_conn():
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = sqlite3.connect(DB_PATH, timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=15000")
        _local.conn = conn
    return conn


def init_db():
    conn = get_conn()
    conn.executescript(SCHEMA)
    conn.commit()
    if conn.execute("SELECT COUNT(*) AS c FROM lessons").fetchone()["c"] == 0:
        now = int(time.time())
        for title, text in SEED_LESSONS:
            conn.execute(
                "INSERT INTO lessons (title, text, source_type, created_at) VALUES (?, ?, 'text', ?)",
                (title, text, now),
            )
        conn.commit()


def rows(sql, params=()):
    return [dict(r) for r in get_conn().execute(sql, params).fetchall()]


def row(sql, params=()):
    r = get_conn().execute(sql, params).fetchone()
    return dict(r) if r else None


def execute(sql, params=()):
    conn = get_conn()
    cur = conn.execute(sql, params)
    conn.commit()
    return cur


def now():
    return int(time.time())
