"""
Слой работы с OpenAI через structured outputs.

Главный приём: список допустимых service_id подставляется в схему
динамически, прямо из каталога услуг. Модель получает не просьбу
«бери действия из справочника», а тип, в котором других значений
не существует. Плюс вторая проверка в catalog.validate_plan_items.

Если ключа нет или закончились кредиты — включается DEMO-режим:
детерминированный планировщик по тому же каталогу. Приложение
остаётся полностью работоспособным, в ответе стоит "engine": "demo".
"""
from __future__ import annotations

import json
import os
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, create_model

from . import catalog
from .schemas import (
    CasePlanItem, CaseState, GeneratedCasePlan, InterviewQuestion,
    InterviewStep, ParentPhase, Priority, TrackStage,
)

MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# Границы интервью из ТЗ: 8-12 адаптивных вопросов
MIN_QUESTIONS = 8
MAX_QUESTIONS = 12


def _client():
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        return None
    from openai import OpenAI
    return OpenAI(api_key=key)


# ───────────────── динамическое сужение схемы под каталог ─────────────────

def _plan_model_for(region: str, child_age: float):
    """
    Собирает копию GeneratedCasePlan, где service_id — Literal из
    реально доступных услуг. Именно это делает галлюцинацию невозможной.
    """
    ids = tuple(s["id"] for s in catalog.eligible(region, child_age))
    ItemBound = create_model(
        "CasePlanItemBound",
        __base__=CasePlanItem,
        service_id=(Literal[ids], Field(description="Код услуги из справочника")),  # type: ignore[valid-type]
    )
    return create_model(
        "GeneratedCasePlanBound",
        __base__=GeneratedCasePlan,
        items=(list[ItemBound], Field(min_length=1, max_length=15)),
    )


# ──────────────────────────── промпты ────────────────────────────

SAFETY = """
ЖЁСТКИЕ ОГРАНИЧЕНИЯ, нарушать нельзя:
1. Ты НЕ ставишь диагноз, не подтверждаешь и не опровергаешь его. Диагноз ставит только врач.
2. Ты не назначаешь лечение, препараты и дозировки.
3. Ты не придумываешь действия. Каждый шаг плана — это service_id из справочника ниже.
4. Ты не даёшь юридических гарантий и не обещаешь результат.
5. Если данных не хватает — записываешь это в missing_data, а не домысливаешь.
Ты помогаешь семье увидеть маршрут и не потерять время. Это всё.
"""

TONE = {
    "SHOCK": "Родитель в состоянии шока. Пиши очень коротко и просто, без терминов. Один понятный следующий шаг, не перегружай.",
    "DENIAL": "Родитель может не принимать ситуацию. Не спорь и не убеждай. Опирайся на сроки и документы, а не на оценки.",
    "ANGER": "Родитель раздражён системой, и это законно. Признай, что система сложная, и давай максимум конкретики: куда идти, что взять.",
    "BARGAINING": "Родитель ищет быстрые решения. Мягко держись доказательных методов, не осуждая другие попытки.",
    "DEPRESSION": "Родитель истощён. Снижай нагрузку: минимум шагов, обязательно упомяни поддержку для него самого.",
    "ACCEPTANCE": "Родитель — партнёр и ко-терапевт. Можно говорить предметно и подробнее.",
    "UNKNOWN": "Тон спокойный, уважительный, без давления.",
}

INTERVIEW_SYSTEM = """Ты ведёшь адаптивное интервью с родителем ребёнка с расстройством аутистического спектра в Казахстане.

Задача: за 8–12 вопросов понять, на каком этапе межведомственного маршрута находится семья.
Уложись в этот бюджет. Недостающее уточнит куратор при проверке плана — это дешевле,
чем утомить родителя длинной анкетой. Как только основное понятно, ставь is_complete = true.

ГЛАВНОЕ ПРАВИЛО АДАПТИВНОСТИ: никогда не спрашивай то, что уже известно из предыдущих ответов.
Если родитель сказал «у нас есть заключение ПМПК» — не спрашивай «проходили ли вы ПМПК»,
спроси «получили ли вы услуги и условия, рекомендованные в заключении».
Если сказал «инвалидность оформлена» — спрашивай про ИПАР, а затем про то,
предоставляются ли мероприятия ИПАР на деле.

Регион и возраст уже спрошены системой — не спрашивай их повторно.

Базовые темы (порядок подстраивай под ответы): этап;
имеющиеся документы; ПМПК; где ребёнок учится; получаемые услуги; инвалидность и ИПАР;
куда уже обращались; незавершённые обращения и проблемы; как справляется сам родитель.

«Не знаю» — нормальный ответ. Если родитель не знает, что такое ПМПК или ИПАР,
объясни в поле clarification простыми словами и продолжи.

Для single_choice и multi_choice всегда давай готовые варианты — родителю в стрессе
тяжело формулировать. Последний вопрос — про состояние самого родителя.
""" + SAFETY

PLAN_SYSTEM = """Ты формируешь межведомственный Case Plan для семьи ребёнка с РАС в Казахстане.

Правила построения плана:
- Каждый шаг — service_id строго из справочника. Другие значения недоступны в схеме.
- Не включай шаги, которые семья уже прошла, кроме случаев, когда требуется продление
  или переосвидетельствование. Если шаг выполнен, ставь already_done = true.
- Соблюдай зависимости: нельзя идти на МСЭ без формы №031/у, а форма №031/у требует
  заключения психиатра. Отражай это в depends_on.
- Приоритет определяется важностью шага для ТЕКУЩЕГО маршрута, а не тяжестью РАС.
  Если ребёнку скоро в школу, а условий нет — ПМПК это HIGH. Информационная консультация — LOW.
- Сроки в due_in_days ориентировочные, их уточняет куратор. Отталкивайся от сроков справочника.
- В explanation объясни родителю простыми словами, зачем шаг нужен именно их ребёнку.
  Без диагнозов, без медицинских оценок, без терминов без расшифровки.
- 5–10 шагов. Лучше меньше и выполнимо, чем много и невозможно.
""" + SAFETY


# ───────────────── что семья уже прошла (общая логика) ─────────────────

def completed_services(state: CaseState) -> set[str]:
    """
    Услуги, которые семья уже получила. Выводится из состояния, а не из
    доверия к модели: наличие инвалидности означает, что и МСЭ, и форма
    №031/у, и консультация психиатра уже позади — иначе инвалидность
    не оформили бы.
    """
    done: set[str] = set(state.services_receiving)

    if state.has_diagnosis:
        done.add("PSYCHIATRIC_CONSULTATION")
    if state.has_pmpc_conclusion:
        done.update({"PMPC_APPLICATION", "VKK_CONCLUSION", "PSYCHIATRIC_CONSULTATION"})
    if state.has_disability:
        done.update({"DISABILITY_ASSESSMENT", "VKK_CONCLUSION", "PSYCHIATRIC_CONSULTATION"})
    if state.has_ipar:
        done.update({"IPAR_APPLICATION", "DISABILITY_ASSESSMENT", "VKK_CONCLUSION",
                     "PSYCHIATRIC_CONSULTATION"})
    if "Форма №031/у" in state.documents_available:
        done.add("VKK_CONCLUSION")

    return done


def drop_completed(items: list, state: CaseState) -> tuple[list, list[str]]:
    """
    Убирает шаги, которые семья уже прошла. Повторяющиеся услуги
    (динамическое наблюдение, контроль терапии) остаются — их нужно
    проходить снова. Возвращает (оставшиеся, причины отсева).
    """
    done = completed_services(state)
    kept, dropped = [], []
    for it in items:
        sid = it.service_id if hasattr(it, "service_id") else it["service_id"]
        svc = catalog.by_id(sid) or {}
        if sid in done and not svc.get("recurring"):
            dropped.append(f"{sid}: у семьи это уже есть")
            continue
        kept.append(it)
    return kept, dropped


# ──────────────────────────── интервью ────────────────────────────

def next_question(history: list[dict], lang: str = "ru") -> tuple[InterviewStep, str]:
    """history: [{question_id, question, answer}]. Возвращает (шаг, движок)."""
    # Верхняя граница держится сервером: модель склонна уточнять бесконечно,
    # а родителю в стрессе длинная анкета обходится дороже, чем недостающее поле —
    # чего не хватит, куратор уточнит при проверке плана.
    # Регион и возраст — опорные поля: от них зависит весь каталог услуг.
    # Их спрашивает система фиксированным списком, а не модель: свободный
    # текст здесь означает нераспознанный регион и неверный набор услуг.
    answered_ids = {h.get("question_id", "") for h in history}
    for anchor in ("REGION", "CHILD_AGE"):
        if anchor not in answered_ids:
            q = next(x for x in _demo_questions(lang) if x["question_id"] == anchor)
            return InterviewStep(
                is_complete=False,
                progress_current=len(history) + 1,
                progress_total=MIN_QUESTIONS + 2,
                next_question=InterviewQuestion(**q),
                acknowledgement=_ack(history, lang) if history else "",
            ), "anchor"

    if len(history) >= MAX_QUESTIONS:
        return InterviewStep(
            is_complete=True,
            progress_current=len(history),
            progress_total=len(history),
            next_question=None,
            acknowledgement=DONE_MSG.get(lang, DONE_MSG["ru"]),
        ), "limit"

    client = _client()
    if client is None:
        return _demo_next_question(history, lang), "demo"

    transcript = "\n".join(
        f"[{h.get('question_id','?')}] Вопрос: {h['question']}\nОтвет родителя: {h['answer']}"
        for h in history
    ) or "(интервью ещё не начато)"

    asked = [h.get("question_id", "") for h in history if h.get("question_id")]
    left = MAX_QUESTIONS - len(history)
    asked_note = (
        f"\n\nУЖЕ ИСПОЛЬЗОВАННЫЕ question_id: {', '.join(asked)}. "
        "Каждый из них использовать повторно ЗАПРЕЩЕНО. Если нужно уточнить ответ, "
        "задай новый вопрос с новым уникальным question_id (например, REGION_CLARIFY)."
        if asked else ""
    )
    budget_note = (
        f"\n\nЗадано вопросов: {len(history)}. Осталось не больше {left}. "
        f"Интервью должно уложиться в {MIN_QUESTIONS}-{MAX_QUESTIONS} вопросов. "
        + ("Задай последний, самый важный вопрос и заверши интервью."
           if left <= 2 else
           "Выбирай вопросы, которые больше всего меняют маршрут; второстепенные уточнения пропускай.")
    )

    try:
        r = client.responses.parse(
            model=MODEL,
            instructions=INTERVIEW_SYSTEM + f"\n\nЯзык общения: {lang}.",
            input=f"Ход интервью:\n{transcript}{asked_note}{budget_note}\n\nЗадай следующий вопрос или заверши интервью.",
            text_format=InterviewStep,
        )
        step = r.output_parsed
        step.progress_current = len(history) + 1
        step.progress_total = max(MIN_QUESTIONS, min(MAX_QUESTIONS, step.progress_total or MIN_QUESTIONS))
        if step.progress_current > step.progress_total:
            step.progress_total = min(MAX_QUESTIONS, step.progress_current)
        # страховка: вопрос с фиксированным набором ответов не должен
        # превращаться в свободный ввод — иначе ответ не распознается
        if step.next_question and step.next_question.input_type in ("single_choice", "multi_choice") \
                and not step.next_question.options:
            step.next_question.input_type = "text"
        # страховка: модель иногда повторяет код вопроса — делаем его уникальным,
        # иначе ответ перезапишет предыдущий и состояние соберётся неверно
        if step.next_question and step.next_question.question_id in asked:
            base = step.next_question.question_id
            n = 2
            while f"{base}_{n}" in asked:
                n += 1
            step.next_question.question_id = f"{base}_{n}"
        return step, "openai"
    except Exception as e:                                   # noqa: BLE001
        print(f"[ai] интервью — переход в demo: {type(e).__name__}: {e}")
        return _demo_next_question(history, lang), "demo-fallback"


def extract_state(history: list[dict]) -> tuple[CaseState, str]:
    client = _client()
    if client is None:
        return _demo_state(history), "demo"

    transcript = "\n".join(f"Вопрос: {h['question']}\nОтвет: {h['answer']}" for h in history)
    try:
        r = client.responses.parse(
            model=MODEL,
            instructions="Извлеки структурированное состояние кейса из интервью. "
                         "Ничего не домысливай: чего нет в ответах — в missing_data. " + SAFETY,
            input=transcript,
            text_format=CaseState,
        )
        return r.output_parsed, "openai"
    except Exception as e:                                   # noqa: BLE001
        print(f"[ai] состояние — переход в demo: {type(e).__name__}: {e}")
        return _demo_state(history), "demo-fallback"


def build_plan(state: CaseState, lang: str = "ru") -> tuple[GeneratedCasePlan, str, list[str]]:
    """Возвращает (план, движок, отклонённые шаги)."""
    client = _client()
    if client is None:
        return _demo_plan(state, lang), "demo", []

    services_text = catalog.compact_for_prompt(state.region.value, state.child_age, lang)
    facilities = {
        s["id"]: catalog.facility_for(state.region.value, s["id"])
        for s in catalog.eligible(state.region.value, state.child_age)
        if catalog.facility_for(state.region.value, s["id"])
    }

    prompt = f"""СПРАВОЧНИК УСЛУГ (только из него можно брать шаги):
{services_text}

ПЛОЩАДКИ РЕГИОНА:
{json.dumps(facilities, ensure_ascii=False, indent=1)}

СОСТОЯНИЕ СЕМЬИ:
{state.model_dump_json(indent=1)}

ТОН: {TONE.get(state.parent_phase.value, TONE['UNKNOWN'])}

Сформируй Case Plan. Сегодня {date.today().isoformat()}."""

    try:
        Bound = _plan_model_for(state.region.value, state.child_age)
        r = client.responses.parse(
            model=MODEL,
            instructions=PLAN_SYSTEM + f"\n\nЯзык плана: {lang}.",
            input=prompt,
            text_format=Bound,
        )
        plan = r.output_parsed
        kept, rejected = catalog.validate_plan_items(plan.items, state.region.value, state.child_age)
        kept, already = drop_completed(kept, state)
        plan.items = _renumber(kept)
        return plan, "openai", rejected + already
    except Exception as e:                                   # noqa: BLE001
        print(f"[ai] план — переход в demo: {type(e).__name__}: {e}")
        return _demo_plan(state, lang), "demo-fallback", []


def _renumber(items: list) -> list:
    """После отсева коды шагов идут подряд, а ссылки depends_on остаются валидными."""
    mapping = {}
    for n, it in enumerate(items, 1):
        old = it.id if hasattr(it, "id") else it["id"]
        mapping[old] = f"CP-{n:03d}"
    alive = set(mapping)
    for it in items:
        if hasattr(it, "id"):
            it.depends_on = [mapping[d] for d in it.depends_on if d in alive]
            it.id = mapping[it.id]
        else:
            it["depends_on"] = [mapping[d] for d in it.get("depends_on", []) if d in alive]
            it["id"] = mapping[it["id"]]
    return items


# ═══════════════════════ DEMO-режим (без ключа) ═══════════════════════
# Детерминированный планировщик по тому же каталогу и тем же правилам.
# Нужен, чтобы демонстрация работала при отсутствии кредитов или сети.

def _demo_questions(lang: str = "ru") -> list[dict]:
    """Вопросы demo-режима на языке интервью. Загружаются из data/questions.json."""
    raw = json.loads((catalog.DATA / "questions.json").read_text(encoding="utf-8"))["questions"]
    out = []
    for q in raw:
        out.append({
            "question_id": q["question_id"],
            "text": q["text"].get(lang, q["text"]["ru"]),
            "why": q["why"].get(lang, q["why"]["ru"]),
            "input_type": q["input_type"],
            "options": [{"value": o["value"], "label": o["label"].get(lang, o["label"]["ru"])}
                        for o in q.get("options", [])],
            "allow_dont_know": True,
            "clarification": (q.get("clarification") or {}).get(lang, (q.get("clarification") or {}).get("ru", "")),
        })
    return out


ACK = {
    "tired": {
        "ru": "Спасибо, что сказали об этом. Я учту вашу нагрузку и не буду перегружать план.",
        "kk": "Айтқаныңыз үшін рахмет. Жүктемеңізді ескеремін, жоспарды артық толтырмаймын.",
        "en": "Thank you for saying that. I'll take your load into account and keep the plan light.",
    },
    "unknown": {
        "ru": "Это нормальный ответ, разберёмся вместе.",
        "kk": "Бұл қалыпты жауап, бірге шешеміз.",
        "en": "That's a perfectly normal answer — we'll work it out together.",
    },
    "ok": {"ru": "Принято.", "kk": "Қабылданды.", "en": "Got it."},
}

DONE_MSG = {
    "ru": "Спасибо. Я собрал достаточно, чтобы построить ваш маршрут.",
    "kk": "Рахмет. Бағытыңызды құруға жеткілікті ақпарат жинадым.",
    "en": "Thank you. I have enough to build your route.",
}


def _answered(history: list[dict]) -> dict[str, str]:
    return {h.get("question_id", ""): str(h.get("answer", "")) for h in history}


def _demo_next_question(history: list[dict], lang: str) -> InterviewStep:
    """Адаптивность в demo: пропускаем вопросы, ответ на которые уже выводится из сказанного."""
    a = _answered(history)
    questions = _demo_questions(lang)
    skip: set[str] = set()

    stage = a.get("STAGE", "")
    docs = a.get("DOCUMENTS", "")
    if "PMPC" in docs or stage == "HAS_PMPC":
        skip.add("PMPC")                     # заключение уже есть — спрашивать незачем
    if "DISABILITY" in docs or stage in ("HAS_DISABILITY", "RECEIVING_HELP"):
        skip.add("DISABILITY")
    if stage == "SUSPECTED":
        skip |= {"DISABILITY", "SERVICES"}   # оформлять ещё нечего

    for q in questions:
        if q["question_id"] in a or q["question_id"] in skip:
            continue
        total = len([x for x in questions if x["question_id"] not in skip])
        return InterviewStep(
            is_complete=False,
            progress_current=len(a) + 1,
            progress_total=max(8, min(12, total)),
            next_question=InterviewQuestion(**q),
            acknowledgement=_ack(history, lang),
        )

    return InterviewStep(is_complete=True, progress_current=len(a), progress_total=len(a),
                         next_question=None, acknowledgement=DONE_MSG.get(lang, DONE_MSG["ru"]))


def _ack(history: list[dict], lang: str = "ru") -> str:
    if not history:
        return ""
    last = str(history[-1].get("answer", "")).upper()
    if "EXHAUSTED" in last or "ALONE" in last:
        key = "tired"
    elif "NONE" in last or "UNKNOWN" in last:
        key = "unknown"
    else:
        key = "ok"
    return ACK[key].get(lang, ACK[key]["ru"])


def _demo_state(history: list[dict]) -> CaseState:
    a = _answered(history)
    docs, stage = a.get("DOCUMENTS", ""), a.get("STAGE", "")

    has_disability = "DISABILITY" in docs or a.get("DISABILITY") == "YES" or stage in ("HAS_DISABILITY", "RECEIVING_HELP")
    has_pmpc = "PMPC" in docs or stage == "HAS_PMPC"
    has_diag = stage not in ("SUSPECTED", "UNKNOWN", "") or "DOCTOR" in docs

    if has_pmpc or has_disability:
        cur = TrackStage.REHABILITATION if stage == "RECEIVING_HELP" else TrackStage.EDUCATIONAL
    elif has_diag:
        cur = TrackStage.SOCIAL_LEGAL
    else:
        cur = TrackStage.DIAGNOSTIC

    pstate = a.get("PARENT_STATE", "")
    phase = {"EXHAUSTED": ParentPhase.DEPRESSION, "ALONE": ParentPhase.DEPRESSION,
             "HARD": ParentPhase.BARGAINING}.get(pstate, ParentPhase.UNKNOWN)
    if stage == "SUSPECTED":
        phase = ParentPhase.SHOCK

    doc_names = {"DOCTOR": "Заключение врача-психиатра", "PMPC": "Заключение ПМПК", "DISABILITY": "Справка об инвалидности",
                 "IPAR": "ИПАР", "SCHOOL": "Характеристика из организации образования", "REHAB": "Документы о реабилитации"}

    try:
        age = float(str(a.get("CHILD_AGE", "5")).replace(",", ".").strip() or 5)
    except ValueError:
        age = 5.0

    return CaseState(
        region=a.get("REGION", "ASTANA"),
        child_age=max(0.0, min(18.0, age)),
        current_stage=cur,
        has_diagnosis=has_diag,
        has_disability=has_disability,
        has_ipar="IPAR" in docs,
        has_pmpc_conclusion=has_pmpc,
        documents_available=[v for k, v in doc_names.items() if k in docs],
        services_receiving=[s for s in a.get("SERVICES", "").split(",") if s and s != "NONE"],
        organizations_contacted=[s for s in a.get("CONTACTED", "").split(",") if s and s != "NONE"],
        open_problems=[s for s in a.get("PROBLEMS", "").split(",") if s and s != "NONE"],
        parent_phase=phase,
        parent_needs_support=pstate in ("EXHAUSTED", "ALONE"),
        education_setting=a.get("EDUCATION", ""),
        on_medication=False,
        missing_data=[q["question_id"] for q in _demo_questions("ru") if q["question_id"] not in a],
    )


def _demo_plan(state: CaseState, lang: str) -> GeneratedCasePlan:
    """Планировщик по зависимостям каталога: берём то, что доступно и ещё не сделано."""
    eligible = catalog.eligible(state.region.value, state.child_age)
    have_docs = set(state.documents_available)
    done = completed_services(state)

    items: list[CasePlanItem] = []
    n = 0
    for s in eligible:
        if len(items) >= 8:
            break
        sid = s["id"]
        if sid in done and not s.get("recurring"):
            continue
        if s.get("conditional") == "only_if_medication" and not state.on_medication:
            continue
        if s.get("for_parent") and not state.parent_needs_support:
            continue
        # зависимости: включаем, только если предпосылка выполнена или тоже попала в план
        prereqs = s.get("prerequisites") or []
        if any(p not in done and p not in {i.service_id for i in items} for p in prereqs):
            continue

        n += 1
        blocked_problem = "SERVICE_NOT_PROVIDED" in state.open_problems and sid in ("EDUCATIONAL_SUPPORT", "REHABILITATION_REFERRAL")
        prio = s["default_priority"]
        if sid == "PMPC_APPLICATION" and 5.5 <= state.child_age <= 7 and not state.has_pmpc_conclusion:
            prio = "HIGH"      # скоро школа, условий нет

        items.append(CasePlanItem(
            id=f"CP-{n:03d}",
            service_id=sid,
            title=s["title"].get(lang, s["title"]["ru"]),
            description=s["purpose"].get(lang, s["purpose"]["ru"]),
            priority=Priority(prio),
            responsible_role=s["responsible_role"],
            due_in_days=s["default_duration_days"],
            documents=[{"name": d, "status": "available" if d in have_docs else "missing"}
                       for d in s.get("required_documents", [])],
            explanation=s["purpose"].get(lang, s["purpose"]["ru"]) +
                        (" Эта услуга назначена, но пока не предоставляется — куратор возьмёт это на контроль."
                         if blocked_problem else ""),
            depends_on=[i.id for i in items if i.service_id in prereqs],
            already_done=False,
        ))
        done.add(sid)

    stage_ru = {"DIAGNOSTIC": "оформления медицинских документов", "SOCIAL_LEGAL": "социально-правового оформления",
                "EDUCATIONAL": "определения образовательного маршрута", "REHABILITATION": "реабилитации и коррекции",
                "VOCATIONAL": "подготовки к взрослой жизни"}[state.current_stage.value]

    summary = (f"Сейчас вы находитесь на этапе {stage_ru}. "
               f"В плане {len(items)} шагов, начните с первого — остальные зависят от него. "
               f"План проверит куратор, прежде чем он станет окончательным.")
    if state.parent_phase == ParentPhase.SHOCK:
        summary = ("Вы в самом начале пути, и это нормально, что сейчас непонятно, куда идти. "
                   f"Я собрал {len(items)} шагов. Достаточно начать с первого — остальное подождёт.")

    support = ""
    if state.parent_needs_support:
        support = ("Вы написали, что сейчас тяжело. Это важно, и это не второстепенно: ваше состояние "
                   "напрямую влияет на то, что реально выполнимо. В плане есть шаг о поддержке для вас — "
                   "он такой же настоящий, как остальные.")

    return GeneratedCasePlan(summary=summary, items=items, parent_support_note=support)
