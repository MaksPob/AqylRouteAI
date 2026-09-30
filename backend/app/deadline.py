"""
Движок сроков и эскалации.

Правило из ТЗ п.12 намеренно механическое: AI не решает, когда эскалировать.
    IF status != DONE AND due_date < today THEN OVERDUE
Пороги эскалации: 1 / 3 / 7 / 14 дней просрочки.
"""
from __future__ import annotations

from datetime import date

LEVELS = [
    (14, "HIGH_ESCALATION", "Высокий уровень эскалации"),
    (7, "ESCALATION", "Эскалация: куратор связывается с организацией"),
    (3, "NOTIFY_CURATOR", "Уведомление родителю и куратору"),
    (1, "NOTIFY_PARENT", "Уведомление родителю"),
]

ACTIVE = {"TODO", "IN_PROGRESS", "WAITING", "BLOCKED", "OVERDUE"}


def days_overdue(due: date, today: date | None = None) -> int:
    today = today or date.today()
    return max(0, (today - due).days)


def escalation_for(overdue_days: int) -> tuple[str, str]:
    for threshold, level, action in LEVELS:
        if overdue_days >= threshold:
            return level, action
    return "NONE", ""


def apply(item: dict, today: date | None = None) -> dict:
    """
    Пересчитывает живые поля шага. Вызывается при каждом чтении плана,
    поэтому просрочка появляется сама, без фоновых задач.
    """
    today = today or date.today()
    status = item.get("status", "TODO")

    if status in ("DONE", "CANCELLED"):
        item["days_overdue"] = 0
        item["escalation_level"] = "NONE"
        item["escalation_action"] = ""
        return item

    due = item.get("due_date")
    if isinstance(due, str):
        due = date.fromisoformat(due)

    od = days_overdue(due, today) if due else 0
    item["days_overdue"] = od

    # BLOCKED важнее OVERDUE: у куратора разные сценарии действий
    if od > 0 and status in ACTIVE and status != "BLOCKED":
        item["status"] = "OVERDUE"

    level, action = escalation_for(od)
    item["escalation_level"] = level
    item["escalation_action"] = action
    return item


def case_summary(items: list[dict]) -> dict:
    """Сводка для панели куратора: не «17 просрочено», а по причинам."""
    counts = {"overdue": 0, "active": 0, "done": 0, "blocked": 0}
    by_blocker: dict[str, int] = {}
    max_level, max_od = "NONE", 0

    for it in items:
        st = it.get("status")
        if st == "DONE":
            counts["done"] += 1
        elif st == "BLOCKED":
            counts["blocked"] += 1
            bt = (it.get("blocker") or {}).get("type", "UNKNOWN")
            by_blocker[bt] = by_blocker.get(bt, 0) + 1
        elif st == "OVERDUE":
            counts["overdue"] += 1
        elif st in ACTIVE:
            counts["active"] += 1

        if it.get("days_overdue", 0) > max_od:
            max_od = it["days_overdue"]
            max_level = it.get("escalation_level", "NONE")

    return {
        **counts,
        "by_blocker": by_blocker,
        "max_escalation": max_level,
        "max_days_overdue": max_od,
    }
