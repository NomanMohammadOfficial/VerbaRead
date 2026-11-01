import html
import re
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote

import requests

from db import execute, row, now

GOOGLE = "https://translate.googleapis.com/translate_a/single"
GOOGLE_ALT = "https://translate.google.com/translate_a/single"
MEMORY = "https://api.mymemory.translated.net/get"
WIKTIONARY = "https://en.wiktionary.org/api/rest_v1/page/definition/{word}"
HEADERS = {
    "User-Agent": "RuReader/1.0 (language-learning app; contact: local)"
}

WORD_RE = re.compile(r"[А-Яа-яЁё][А-Яа-яЁё-]*")
TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(value: str) -> str:
    text = TAG_RE.sub("", value or "")
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _is_echo(text: str, result: str) -> bool:
    return result.strip().lower() == text.strip().lower()


def _clean_gloss(gloss: str) -> str:
    while gloss.startswith("("):
        end = gloss.find(")")
        if end == -1:
            break
        gloss = gloss[end + 1 :].lstrip()
    if "(" in gloss:
        head = gloss.split("(", 1)[0].strip(" ;,")
        if len(head) >= 2:
            gloss = head
    gloss = re.sub(r"\s{2,}", " ", gloss).strip(" ;,/-–—")
    if len(gloss) > 80:
        gloss = gloss[:80].rsplit(" ", 1)[0].rstrip(" ;,/-–—")
    return gloss


def _wiktionary_entry(word: str) -> dict | None:
    try:
        response = requests.get(
            WIKTIONARY.format(word=quote(word)), headers=HEADERS, timeout=8
        )
        if response.status_code != 200:
            return None
        return response.json()
    except Exception:
        return None


def _wiktionary(word: str) -> str | None:
    if " " in word or not WORD_RE.match(word):
        return None
    data = _wiktionary_entry(word)
    if not data and word[:1].islower():
        data = _wiktionary_entry(word[:1].upper() + word[1:])
    if not data:
        return None

    entries = data.get("ru") or []
    if not entries:
        return None

    senses: list[str] = []
    for entry in entries:
        for definition in entry.get("definitions") or []:
            gloss = _strip_html(definition.get("definition", ""))
            if not gloss or gloss.lower().startswith("archaic"):
                continue
            senses.append(gloss)
        if senses:
            break

    if not senses:
        return None

    cleaned = []
    for sense in senses:
        gloss = _clean_gloss(sense)
        if gloss and gloss.lower() not in {c.lower() for c in cleaned}:
            cleaned.append(gloss)
        if len(cleaned) >= 2:
            break
    return "; ".join(cleaned) if cleaned else None


def _google_one(url: str, text: str, source: str, target: str) -> str | None:
    params = {"client": "gtx", "sl": source, "tl": target, "dt": "t", "q": text}
    response = requests.get(url, params=params, headers=HEADERS, timeout=8)
    response.raise_for_status()
    data = response.json()
    chunks = [seg[0] for seg in data[0] if seg and seg[0]]
    result = "".join(chunks).strip()
    return result or None


def _google(text: str, source: str, target: str) -> str | None:
    for attempt in range(2):
        for url in (GOOGLE, GOOGLE_ALT):
            try:
                result = _google_one(url, text, source, target)
                if result and not _is_echo(text, result):
                    return result
            except Exception:
                pass
        if attempt == 0:
            time.sleep(0.5)
    return None


def _mymemory(text: str, source: str, target: str) -> str | None:
    try:
        response = requests.get(
            MEMORY,
            params={"q": text, "langpair": f"{source}|{target}"},
            headers=HEADERS,
            timeout=8,
        )
        response.raise_for_status()
        data = response.json()
    except Exception:
        return None

    candidates: list[tuple[float, str]] = []
    primary = (data.get("responseData") or {}).get("translatedText")
    if primary and "MYMEMORY WARNING" not in primary and "INVALID" not in primary.upper():
        candidates.append(
            (float((data.get("responseData") or {}).get("match") or 0), primary)
        )
    for match in data.get("matches") or []:
        translated = match.get("translation")
        if not translated or "MYMEMORY WARNING" in translated:
            continue
        score = max(
            float(match.get("match") or 0), float(match.get("quality") or 0) / 100.0
        )
        candidates.append((score, translated))

    def rank(item: tuple[float, str]) -> tuple:
        score, result = item
        result = result.strip()
        single_word = 0 if " " not in result else 1
        weird = 1 if re.search(r"[^\w\s.,;:!?'\"-]", result) else 0
        lowercase = 0 if result[:1].islower() else 1
        return (weird, single_word, -score, lowercase)

    filtered = [
        item
        for item in candidates
        if item[1].strip() and not _is_echo(text, item[1]) and re.search(r"[A-Za-zА-Яа-я]", item[1])
    ]
    if not filtered:
        return None
    filtered.sort(key=rank)
    return filtered[0][1].strip()


def _settle(job) -> str | None:
    try:
        return job.result()
    except Exception:
        return None


def cached(text: str, target: str = "en") -> str | None:
    found = row(
        "SELECT result FROM translations WHERE source = ? AND target_lang = ?",
        (text, target),
    )
    return found["result"] if found else None


def save_cache(text: str, result: str, target: str = "en"):
    execute(
        "INSERT OR REPLACE INTO translations (source, target_lang, result, created_at) VALUES (?, ?, ?, ?)",
        (text, target, result, now()),
    )


def translate(
    text: str, source: str = "ru", target: str = "en", use_cache: bool = True
) -> dict:
    text = (text or "").strip()
    if not text:
        return {"text": text, "translation": "", "cached": False}
    if use_cache:
        hit = cached(text, target)
        if hit and not _is_echo(text, hit):
            return {"text": text, "translation": hit, "cached": True}

    is_word = bool(WORD_RE.fullmatch(text))
    result = None
    if is_word and target == "en" and source == "ru":
        with ThreadPoolExecutor(max_workers=2) as pool:
            wiki = pool.submit(_wiktionary, text)
            google = pool.submit(_google, text, source, target)
            result = _settle(wiki) or _settle(google)
    else:
        result = _google(text, source, target)
    if not result:
        result = _mymemory(text, source, target)

    if result:
        save_cache(text, result, target)
    return {"text": text, "translation": result or "", "cached": False}
