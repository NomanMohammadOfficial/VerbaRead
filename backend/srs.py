DAY = 86400
MIN_EASE = 1.3
MAX_EASE = 3.0
MAX_INTERVAL = 365.0


def schedule(word: dict, grade: int, timestamp: int) -> dict:
    """SM-2 variant. grade: 1 again, 2 hard, 3 good, 4 easy."""
    ease = float(word.get("ease") or 2.5)
    interval = float(word.get("interval_days") or 0)
    reps = int(word.get("reps") or 0)
    lapses = int(word.get("lapses") or 0)

    if grade <= 1:
        interval = 10 / 1440
        reps = 0
        lapses += 1
        ease = max(MIN_EASE, ease - 0.2)
        due_at = timestamp + 600
    else:
        if interval <= 0:
            interval = {2: 1.0, 3: 1.0, 4: 3.0}[grade]
        elif grade == 2:
            interval = interval * 1.2
        elif grade == 3:
            interval = interval * ease
        else:
            interval = interval * ease * 1.35
        interval = min(MAX_INTERVAL, round(interval, 2))
        if grade >= 3:
            reps += 1
        if grade == 4:
            ease = min(MAX_EASE, ease + 0.15)
        if grade == 2:
            ease = max(MIN_EASE, ease - 0.15)
        due_at = timestamp + int(interval * DAY)

    if reps >= 6:
        status = 4
    elif reps >= 3:
        status = 3
    elif reps >= 1:
        status = 2
    else:
        status = 1

    return {
        "ease": round(ease, 3),
        "interval_days": interval,
        "reps": reps,
        "lapses": lapses,
        "due_at": due_at,
        "status": max(status, int(word.get("status") or 1)) if grade >= 3 else status,
        "last_reviewed_at": timestamp,
    }


def label(days: float) -> str:
    if days <= 0:
        return "now"
    if days < 1 / 24:
        return f"{round(days * 1440)} min"
    if days < 1:
        return f"{round(days * 24)} h"
    if days < 30:
        return f"{round(days)} d"
    if days < 365:
        return f"{round(days / 30)} mo"
    return f"{round(days / 365, 1)} y"
