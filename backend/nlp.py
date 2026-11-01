import re
from functools import lru_cache

from pymorphy3 import MorphAnalyzer

morph = MorphAnalyzer()

TOKEN_RE = re.compile(r"[А-Яа-яЁё]+(?:-[А-Яа-яЁё]+)*|\d+(?:[.,]\d+)?|\s+|[^\sА-Яа-яЁё\d]+")
SENTENCE_RE = re.compile(r"[^.!?…\n]+[.!?…]*")

POS = {
    "NOUN": "noun",
    "ADJF": "adjective",
    "ADJS": "short adjective",
    "COMP": "comparative",
    "VERB": "verb",
    "INFN": "infinitive",
    "PRTF": "participle",
    "PRTS": "short participle",
    "GRND": "gerund",
    "NUMR": "numeral",
    "ADVB": "adverb",
    "NPRO": "pronoun",
    "PRED": "predicate",
    "PREP": "preposition",
    "CONJ": "conjunction",
    "PRCL": "particle",
    "INTJ": "interjection",
}

CASE = {
    "nomn": "nominative",
    "gent": "genitive",
    "datv": "dative",
    "accs": "accusative",
    "ablt": "instrumental",
    "loct": "prepositional",
    "voct": "vocative",
    "gen1": "genitive",
    "gen2": "partitive",
    "acc2": "accusative",
    "loc1": "prepositional",
    "loc2": "locative",
}

NUMBER = {"sing": "singular", "plur": "plural"}
GENDER = {"masc": "masculine", "femn": "feminine", "neut": "neuter"}
TENSE = {"pres": "present", "past": "past", "futr": "future"}
PERSON = {"1per": "1st person", "2per": "2nd person", "3per": "3rd person"}
ASPECT = {"perf": "perfective", "impf": "imperfective"}
MOOD = {"indc": "indicative", "impr": "imperative"}
VOICE = {"actv": "active", "pssv": "passive"}


def _feature(tag, key, table):
    value = getattr(tag, key, None)
    return table.get(value) if value else None


@lru_cache(maxsize=50000)
def analyze(word: str) -> dict:
    parsed = morph.parse(word)
    if not parsed:
        return {"lemma": word.lower(), "pos": "", "grammar": "", "tags": {}}
    best = max(parsed, key=lambda p: (p.score, bool(p.tag.POS)))
    tag = best.tag
    parts = []
    pos = POS.get(tag.POS or "", "")
    if pos:
        parts.append(pos)
    for key, table in (
        ("gender", GENDER),
        ("animacy", {"anim": "animate", "inan": "inanimate"}),
        ("aspect", ASPECT),
        ("tense", TENSE),
        ("person", PERSON),
        ("number", NUMBER),
        ("case", CASE),
        ("mood", MOOD),
        ("voice", VOICE),
    ):
        value = _feature(tag, key, table)
        if value and value not in parts:
            parts.append(value)
    if tag.POS in {"INFN"} and "infinitive" not in parts:
        parts.insert(0, "infinitive")
    return {
        "lemma": best.normal_form,
        "pos": pos,
        "grammar": " · ".join(parts),
        "tags": {k: getattr(tag, k, None) for k in ("POS", "case", "number", "gender", "tense", "person", "aspect", "mood")},
    }


def tokenize(text: str) -> list[dict]:
    spans = [(m.start(), m.end()) for m in SENTENCE_RE.finditer(text)]
    tokens = []
    for match in TOKEN_RE.finditer(text):
        value = match.group()
        start, end = match.span()
        if value.isspace():
            kind = "space"
        elif re.fullmatch(r"\d+(?:[.,]\d+)?", value):
            kind = "number"
        elif value[0].isalpha():
            kind = "word"
        else:
            kind = "punct"
        sentence = ""
        for s_start, s_end in spans:
            if s_start <= start < s_end:
                sentence = text[s_start:s_end].strip()
                break
        tokens.append({"text": value, "kind": kind, "start": start, "end": end, "sentence": sentence})
    return tokens


def cyrillic_ratio(text: str) -> float:
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 0.0
    return sum(1 for c in letters if "а" <= c.lower() <= "я" or c.lower() == "ё") / len(letters)
