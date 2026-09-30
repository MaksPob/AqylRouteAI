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

ГЛАВНОЕ ПРАВИЛО АДАПТИВНОСТИ: никогда не спрашивай то, что уже известно из предыдущих ответов.
Если родитель сказал «у нас есть заключение ПМПК» — не спрашивай «проходили ли вы ПМПК»,
спроси «получили ли вы услуги и условия, рекомендованные в заключении».
Если сказал «инвалидность оформлена» — спрашивай про ИПАР, а затем про то,
предоставляются ли мероприятия ИПАР на деле.

Базовые темы (порядок подстраивай под ответы): регион; возраст ребёнка; этап;
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


# ──────────────────────────── интервью ────────────────────────────

def next_question(history: list[dict], lang: str = "ru") -> tuple[InterviewStep, str]:
    """history: [{question_id, question, answer}]. Возвращает (шаг, движок)."""
    client = _client()
    if client is None:
        return _demo_next_question(history, lang), "demo"

    transcript = "\n".join(
        f"[{h.get('question_id','?')}] Вопрос: {h['question']}\nОтвет родителя: {h['answer']}"
        for h in history
    ) or "(интервью ещё не начато)"

    try:
        r = client.responses.parse(
            model=MODEL,
            instructions=INTERVIEW_SYSTEM + f"\n\nЯзык общения: {lang}.",
            input=f"Ход интервью:\n{transcript}\n\nЗадай следующий вопрос или заверши интервью.",
            text_format=InterviewStep,
        )
        return r.output_parsed, "openai"
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
        plan.items = kept
        return plan, "openai", rejected
    except Exception as e:                                   # noqa: BLE001
        print(f"[ai] план — переход в demo: {type(e).__name__}: {e}")
        return _demo_plan(state, lang), "demo-fallback", []


# ═══════════════════════ DEMO-режим (без ключа) ═══════════════════════
# Детерминированный планировщик по тому же каталогу и тем же правилам.
# Нужен, чтобы демонстрация работала при отсутствии кредитов или сети.

DEMO_QUESTIONS: list[dict] = [
    {"question_id": "REGION", "text": "В каком городе или области вы сейчас живёте?", "why": "От региона зависит, какие организации и услуги вам доступны.", "input_type": "single_choice",
     "options": [{"value": "ASTANA", "label": "Астана"}, {"value": "KARAGANDA", "label": "Караганда и Карагандинская область"}, {"value": "ALMATY", "label": "Алматы"}]},
    {"question_id": "CHILD_AGE", "text": "Сколько лет ребёнку?", "why": "Возраст определяет, какие этапы маршрута сейчас актуальны.", "input_type": "number", "options": []},
    {"question_id": "STAGE", "text": "На каком этапе вы сейчас?", "why": "Это отправная точка маршрута. «Не знаю» — нормальный ответ.", "input_type": "single_choice",
     "options": [{"value": "SUSPECTED", "label": "Нам только сказали, что у ребёнка может быть РАС"},
                 {"value": "CONFIRMED", "label": "Диагноз уже подтверждён"},
                 {"value": "CONFIRMED_NO_DOCS", "label": "Диагноз подтверждён, но дальше ничего не оформляли"},
                 {"value": "HAS_DISABILITY", "label": "Уже получили инвалидность, не знаем что дальше"},
                 {"value": "HAS_PMPC", "label": "Прошли ПМПК, определили тип образования"},
                 {"value": "RECEIVING_HELP", "label": "Все документы есть, ребёнок получает помощь"},
                 {"value": "UNKNOWN", "label": "Не знаю, на каком мы этапе"}]},
    {"question_id": "DOCUMENTS", "text": "Какие документы у вас уже есть?", "why": "Чтобы не отправлять вас собирать то, что уже на руках.", "input_type": "multi_choice",
     "options": [{"value": "DOCTOR", "label": "Заключение врача"}, {"value": "PMPC", "label": "Заключение ПМПК"},
                 {"value": "SCHOOL", "label": "Документы из детского сада или школы"}, {"value": "DISABILITY", "label": "Документы об инвалидности"},
                 {"value": "IPAR", "label": "ИПАР"}, {"value": "REHAB", "label": "Документы о реабилитации"},
                 {"value": "OTHER", "label": "Другое"}, {"value": "NONE", "label": "Пока ничего нет"}]},
    {"question_id": "PMPC", "text": "Проходили ли вы ПМПК?", "why": "ПМПК определяет, какие образовательные условия нужны ребёнку.", "input_type": "single_choice",
     "options": [{"value": "YES", "label": "Да"}, {"value": "NO", "label": "Нет"}, {"value": "SCHEDULED", "label": "Записались"},
                 {"value": "NO_RESULT", "label": "Проходили, но заключение не получили"}, {"value": "WHAT", "label": "Не знаю, что это"}],
     "clarification": "ПМПК — это психолого-медико-педагогическая консультация. Она определяет особые образовательные потребности ребёнка: нужен ли тьютор, по какой программе учиться и в какой форме. Сейчас уточню ещё пару вопросов, чтобы понять, нужен ли вам этот этап."},
    {"question_id": "EDUCATION", "text": "Где сейчас ребёнок получает образование?", "why": "От этого зависит, какие условия нужно организовать.", "input_type": "single_choice",
     "options": [{"value": "HOME", "label": "Дома"}, {"value": "KINDERGARTEN", "label": "Детский сад"}, {"value": "SPECIAL_KINDERGARTEN", "label": "Специальный детский сад"},
                 {"value": "SCHOOL", "label": "Школа"}, {"value": "SPECIAL_SCHOOL", "label": "Специальная школа"}, {"value": "NONE", "label": "Не посещает"}]},
    {"question_id": "SERVICES", "text": "Какие услуги ребёнок получает сейчас?", "why": "Чтобы не дублировать то, что уже есть.", "input_type": "multi_choice",
     "options": [{"value": "PSYCHOLOGICAL_PEDAGOGICAL_SUPPORT", "label": "Психолого-педагогическая помощь"}, {"value": "REHABILITATION_REFERRAL", "label": "Реабилитация"},
                 {"value": "SPEECH_AND_OT", "label": "Логопед, дефектолог, эрготерапевт"}, {"value": "ABA_THERAPY", "label": "Поведенческая помощь (ABA)"},
                 {"value": "EARLY_INTERVENTION", "label": "Раннее вмешательство"}, {"value": "NONE", "label": "Пока никаких"}]},
    {"question_id": "DISABILITY", "text": "Оформлена ли ребёнку инвалидность?", "why": "Инвалидность открывает доступ к ИПАР, пособиям и реабилитации.", "input_type": "single_choice",
     "options": [{"value": "YES", "label": "Да"}, {"value": "NO", "label": "Нет"}, {"value": "SUBMITTED", "label": "Документы поданы"}, {"value": "UNKNOWN", "label": "Не знаю"}]},
    {"question_id": "CONTACTED", "text": "Куда вы уже обращались?", "why": "Чтобы вам не пришлось повторно собирать то же самое.", "input_type": "multi_choice",
     "options": [{"value": "CLINIC", "label": "Поликлиника"}, {"value": "PMPC", "label": "ПМПК"}, {"value": "REHAB", "label": "Реабилитационный центр"},
                 {"value": "SOCIAL", "label": "Соцзащита"}, {"value": "NONE", "label": "Никуда"}]},
    {"question_id": "PROBLEMS", "text": "Есть ли сейчас незавершённое обращение или проблема, которую не удаётся решить?", "why": "Здесь мы находим, где именно маршрут остановился.", "input_type": "multi_choice",
     "options": [{"value": "WAITING_DOC", "label": "Ждём документ"}, {"value": "WAITING_REFERRAL", "label": "Ждём направление"},
                 {"value": "NO_PMPC_SLOT", "label": "Не можем попасть на ПМПК"}, {"value": "SERVICE_NOT_PROVIDED", "label": "Услуга назначена, но не предоставляется"},
                 {"value": "LOST", "label": "Не знаем, куда идти"}, {"value": "OVERDUE", "label": "Срок уже прошёл"}, {"value": "NONE", "label": "Нет таких"}]},
    {"question_id": "PARENT_STATE", "text": "А как вы сами сейчас справляетесь? Есть ли у вас поддержка?", "why": "Ваше состояние напрямую влияет на то, что реально выполнимо. Это не формальность.", "input_type": "single_choice",
     "options": [{"value": "OK", "label": "В целом справляюсь, поддержка есть"}, {"value": "HARD", "label": "Тяжело, но держусь"},
                 {"value": "EXHAUSTED", "label": "Очень тяжело, сил почти нет"}, {"value": "ALONE", "label": "Справляюсь один, поддержки нет"}]},
]


def _answered(history: list[dict]) -> dict[str, str]:
    return {h.get("question_id", ""): str(h.get("answer", "")) for h in history}


def _demo_next_question(history: list[dict], lang: str) -> InterviewStep:
    """Адаптивность в demo: пропускаем вопросы, ответ на которые уже выводится из сказанного."""
    a = _answered(history)
    skip: set[str] = set()

    stage = a.get("STAGE", "")
    docs = a.get("DOCUMENTS", "")
    if "PMPC" in docs or stage == "HAS_PMPC":
        skip.add("PMPC")                     # заключение уже есть — спрашивать незачем
    if "DISABILITY" in docs or stage in ("HAS_DISABILITY", "RECEIVING_HELP"):
        skip.add("DISABILITY")
    if stage == "SUSPECTED":
        skip |= {"DISABILITY", "SERVICES"}   # оформлять ещё нечего

    for q in DEMO_QUESTIONS:
        if q["question_id"] in a or q["question_id"] in skip:
            continue
        total = len([x for x in DEMO_QUESTIONS if x["question_id"] not in skip])
        return InterviewStep(
            is_complete=False,
            progress_current=len(a) + 1,
            progress_total=max(8, min(12, total)),
            next_question=InterviewQuestion(**q),
            acknowledgement=_ack(history),
        )

    return InterviewStep(is_complete=True, progress_current=len(a), progress_total=len(a),
                         next_question=None, acknowledgement="Спасибо. Я собрал достаточно, чтобы построить ваш маршрут.")


def _ack(history: list[dict]) -> str:
    if not history:
        return ""
    last = str(history[-1].get("answer", "")).upper()
    if "EXHAUSTED" in last or "ALONE" in last:
        return "Спасибо, что сказали об этом. Я учту вашу нагрузку и не буду перегружать план."
    if "NONE" in last or "UNKNOWN" in last or "НЕ ЗНАЮ" in last:
        return "Это нормальный ответ, разберёмся вместе."
    return "Принято."


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
        missing_data=[q["question_id"] for q in DEMO_QUESTIONS if q["question_id"] not in a],
    )


def _demo_plan(state: CaseState, lang: str) -> GeneratedCasePlan:
    """Планировщик по зависимостям каталога: берём то, что доступно и ещё не сделано."""
    eligible = catalog.eligible(state.region.value, state.child_age)
    have_docs = set(state.documents_available)
    done: set[str] = set(state.services_receiving)

    if state.has_diagnosis:
        done.add("PSYCHIATRIC_CONSULTATION")
    if "Форма №031/у" in have_docs or state.has_disability:
        done.add("VKK_CONCLUSION")
    if state.has_disability:
        done.add("DISABILITY_ASSESSMENT")
    if state.has_ipar:
        done.add("IPAR_APPLICATION")
    if state.has_pmpc_conclusion:
        done.add("PMPC_APPLICATION")

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
