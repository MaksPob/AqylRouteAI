"""Справочник услуг: загрузка, фильтрация по региону и возрасту, проверка ответов AI."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"


@lru_cache(maxsize=1)
def catalog() -> dict:
    return json.loads((DATA / "services.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def enums() -> dict:
    return json.loads((DATA.parent.parent / "domain" / "enums.json").read_text(encoding="utf-8"))


def services() -> list[dict]:
    return catalog()["services"]


def service_ids() -> list[str]:
    """Полный список допустимых service_id — идёт в JSON Schema как enum."""
    return [s["id"] for s in services()]


def by_id(service_id: str) -> dict | None:
    return next((s for s in services() if s["id"] == service_id), None)


def eligible(region: str, child_age: float) -> list[dict]:
    """Услуги, подходящие региону и возрасту. Сужает выбор AI ещё до вызова модели."""
    out = []
    for s in services():
        if not (s.get("age_min", 0) <= child_age <= s.get("age_max", 18)):
            continue
        region_cfg = catalog()["regions"].get(region, {})
        avail = region_cfg.get("available_services", "all")
        if avail != "all" and s["id"] not in avail:
            continue
        out.append(s)
    return out


def facility_for(region: str, service_id: str) -> list[dict]:
    """Конкретные площадки региона для услуги — то, что делает план не абстрактным."""
    return catalog()["regions"].get(region, {}).get("facilities", {}).get(service_id, [])


def compact_for_prompt(region: str, child_age: float, lang: str = "ru") -> str:
    """Каталог в виде компактного текста для промпта — без лишних токенов."""
    lines = []
    for s in eligible(region, child_age):
        prereq = ", ".join(s.get("prerequisites") or []) or "нет"
        lines.append(
            f"- {s['id']} | этап {s['stage']} | {s['title'].get(lang, s['title']['ru'])} "
            f"| ответственный {s['responsible_role']} | срок ~{s['default_duration_days']} дн "
            f"| приоритет по умолчанию {s['default_priority']} | требует раньше: {prereq}"
        )
    return "\n".join(lines)


def validate_plan_items(items: list, region: str, child_age: float) -> tuple[list, list[str]]:
    """
    Вторая линия защиты после structured outputs.

    Schema не даёт выдумать service_id, но не проверяет, подходит ли услуга
    возрасту и региону — это делаем здесь. Непрошедшие шаги отбрасываются,
    причина возвращается для журнала куратора.
    """
    allowed = {s["id"] for s in eligible(region, child_age)}
    kept, rejected = [], []
    for it in items:
        sid = it.service_id if hasattr(it, "service_id") else it["service_id"]
        if sid in allowed:
            kept.append(it)
        else:
            reason = "нет в справочнике" if not by_id(sid) else "не подходит по возрасту или региону"
            rejected.append(f"{sid}: {reason}")
    return kept, rejected
