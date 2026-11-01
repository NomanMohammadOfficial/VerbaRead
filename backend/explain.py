import re

from nlp import analyze, tokenize
from translate import translate

INFLECTION = re.compile(
    r"\b(?:singular|plural|genitive|dative|accusative|instrumental|prepositional|"
    r"nominative|present|past|future|imperative|comparative)\b.*\bof\b",
    re.I,
)

CASE_HINT = {
    "nominative": "The nominative marks the subject — the person or thing doing the action.",
    "genitive": "The genitive often marks possession, absence, or a quantity of something.",
    "dative": "The dative marks the indirect object, or the person who receives something.",
    "accusative": "The accusative marks the direct object of the verb.",
    "instrumental": "The instrumental marks the instrument or means, and follows с.",
    "prepositional": "The prepositional is used after в or на to talk about a place.",
    "partitive": "The partitive genitive is used for a portion of something.",
    "locative": "The locative is a second prepositional form used after в or на.",
    "vocative": "The vocative is used when addressing someone directly.",
}

POS_HINT = {
    "noun": "Russian nouns decline: the ending changes with case and number.",
    "verb": "Russian verbs express aspect — perfective for a completed action, imperfective for an ongoing or repeated one.",
    "adjective": "Russian adjectives agree with their noun in gender, number, and case.",
    "participle": "Participles work like adjectives but keep the verb's aspect and tense.",
    "gerund": "Gerunds describe a simultaneous or preceding action and never change form.",
    "adverb": "Adverbs are invariable — their form never changes.",
    "pronoun": "Pronouns change form by case, and some also by gender.",
}


def _hint(tags):
    pos = (tags or {}).get("POS")
    case = (tags or {}).get("case")
    if pos == "NOUN" or pos == "ADJF":
        if case:
            return CASE_HINT.get(case)
    return POS_HINT.get(_pos_key(pos))


def _pos_key(tag_pos):
    table = {
        "NOUN": "noun",
        "ADJF": "adjective",
        "ADJS": "adjective",
        "COMP": "adjective",
        "VERB": "verb",
        "INFN": "verb",
        "PRTF": "participle",
        "PRTS": "participle",
        "GRND": "gerund",
        "ADVB": "adverb",
        "NPRO": "pronoun",
    }
    return table.get(tag_pos or "", "")


def _translate(text):
    if not text:
        return ""
    try:
        result = translate(text)
    except Exception:
        return ""
    return (result or {}).get("translation") or ""


def _single(surface, data, translation, context):
    lemma = data.get("lemma") or surface
    pos = data.get("pos") or "word"
    case = (data.get("tags") or {}).get("case")
    from nlp import CASE

    summary = f"{lemma} is a {pos}"
    if case and CASE.get(case):
        summary += f" in the {CASE[case]} case"
    summary += "."
    if translation:
        summary += f' Here it means "{translation}".'

    points = []
    if surface.lower() != lemma.lower():
        points.append(f'"{surface}" is an inflected form of the lemma "{lemma}".')
    else:
        points.append(f'The lemma is "{lemma}".')
    if data.get("grammar"):
        points.append(f"Parsed as {data['grammar']}.")
    hint = _hint(data.get("tags"))
    if hint:
        points.append(hint)
    if context.strip():
        points.append(f'In this sentence: "{context.strip()}"')
    return summary, points


def _phrase(query, words, translation):
    glosses = []
    used = 0
    for token in words:
        if used >= 8:
            break
        data = analyze(token["text"])
        detail = data.get("grammar") or data.get("pos") or "word"
        glosses.append(f'{token["text"]} → {data["lemma"]} ({detail})')
        used += 1
    summary = f'"{query}" means "{translation}".' if translation else f'"{query}" — phrase analysis.'
    points = [f"Word by word: {'; '.join(glosses)}."] if glosses else []
    if translation:
        points.append("Read the phrase as one unit: Russian word order is flexible, so case endings carry the grammar.")
    return summary, points


def explain(query, context="", translation=""):
    query = (query or "").strip()
    if not query:
        return {"query": "", "error": "Nothing to explain", "source": "local"}
    words = [token for token in tokenize(query) if token["kind"] == "word"]
    if not translation:
        translation = _translate(query)
    if not words:
        return {
            "query": query,
            "translation": translation,
            "summary": "",
            "points": [],
            "source": "local",
        }
    if len(words) == 1:
        data = analyze(words[0]["text"])
        lemma = data.get("lemma") or ""
        if lemma and lemma != words[0]["text"].lower() and INFLECTION.search(translation or ""):
            better = _translate(lemma)
            if better:
                translation = better
        summary, points = _single(words[0]["text"], data, translation, context)
        return {
            "query": query,
            "lemma": data.get("lemma") or "",
            "pos": data.get("pos") or "",
            "grammar": data.get("grammar") or "",
            "translation": translation,
            "summary": summary,
            "points": points,
            "source": "local",
        }
    summary, points = _phrase(query, words, translation)
    return {
        "query": query,
        "translation": translation,
        "summary": summary,
        "points": points,
        "words": [
            {"text": token["text"], "lemma": analyze(token["text"])["lemma"]}
            for token in words[:8]
        ],
        "source": "local",
    }
