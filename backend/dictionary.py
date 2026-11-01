import json
import re
from urllib.parse import quote

import requests

from db import execute, now, row
from translate import HEADERS

BASE = "https://en.openrussian.org/ru/"
NEXT_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S
)
ACUTE = "\u0301"


def stress(text):
    if not text:
        return text
    return text.replace(ACUTE, "").replace("'", ACUTE)


def search(lemma):
    key = (lemma or "").strip().lower()
    url = BASE + quote(key)
    resp = requests.get(url, headers=HEADERS, timeout=15)
    return url, resp


def parse(html):
    match = NEXT_RE.search(html)
    if not match:
        return None, None
    try:
        data = json.loads(match.group(1))
    except ValueError:
        return None, None
    props = data.get("props") or {}
    page = props.get("pageProps") or {}
    info = page.get("info") or {}
    words = info.get("words") or []
    if not words:
        return info, None
    return info, words[0]


def _glosses(entries):
    out = []
    for entry in entries or []:
        for gloss in entry.get("tls") or []:
            gloss = (gloss or "").strip()
            if gloss and gloss not in out:
                out.append(gloss)
    return out


def _declension(noun):
    source = (noun or {}).get("declension")
    if not source:
        return None
    return {
        "sg": {key: stress(value) for key, value in (source.get("sg") or {}).items()},
        "pl": {key: stress(value) for key, value in (source.get("pl") or {}).items()},
    }


def build(word):
    noun = word.get("noun") or {}
    translations = _glosses(word.get("translations"))
    meanings = []
    for item in word.get("meanings") or []:
        glosses = _glosses([item])
        definition = (item.get("definition") or "").strip()
        if not glosses and not definition:
            continue
        meanings.append(
            {
                "definition": definition,
                "glosses": glosses,
                "example_ru": stress(item.get("exampleRu") or ""),
                "example_tl": (item.get("exampleTl") or "").strip(),
                "rare": bool(item.get("isRare")),
            }
        )
    examples = [
        {"ru": stress(item.get("ru") or ""), "tl": (item.get("tl") or "").strip()}
        for item in (word.get("sentences") or [])[:5]
    ]
    return {
        "lemma": word.get("bare"),
        "accented": stress(word.get("accented") or ""),
        "type": word.get("type") or "",
        "level": word.get("level") or "",
        "rank": word.get("rank"),
        "gender": noun.get("gender") or "",
        "animate": bool(noun.get("animate")),
        "audio": word.get("audio") or "",
        "translations": translations,
        "meanings": meanings,
        "examples": examples,
        "forms": _declension(noun),
    }


def lookup(lemma, use_cache=True):
    key = (lemma or "").strip().lower()
    if not key:
        return {"lemma": "", "found": False, "error": "Empty word"}
    if use_cache:
        cached = row("SELECT payload FROM dictionary_cache WHERE lemma = ?", (key,))
        if cached:
            payload = json.loads(cached["payload"])
            payload["cached"] = True
            return payload
    try:
        url, resp = search(key)
    except requests.RequestException as exc:
        return {
            "lemma": key,
            "found": False,
            "error": f"Dictionary is unreachable ({exc.__class__.__name__})",
        }
    if resp.status_code != 200:
        return {
            "lemma": key,
            "found": False,
            "error": f"openrussian returned {resp.status_code}",
        }
    info, word = parse(resp.text)
    if not word:
        return {"lemma": key, "found": False, "error": "No dictionary entry for this word"}
    payload = build(word)
    payload["found"] = True
    payload["source"] = "openrussian"
    payload["url"] = url
    if info.get("redirectTo"):
        payload["redirect_to"] = info["redirectTo"]
    execute(
        "INSERT OR REPLACE INTO dictionary_cache (lemma, payload, created_at) VALUES (?, ?, ?)",
        (key, json.dumps(payload, ensure_ascii=False), now()),
    )
    return payload
