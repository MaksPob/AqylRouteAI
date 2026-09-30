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

# Как звучат вопросы:
#   "adaptive"  — модель переформулирует канонический вопрос под уже сказанное
#                 (тема и коды ответов остаются прежними);
#   "canonical" — вопрос звучит ровно так, как записан в справочнике.
# Переключается в .env: INTERVIEW_MODE=canonical
INTERVIEW_MODE = os.getenv("INTERVIEW_MODE", "adaptive").strip().lower()


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
- ОПИРАЙСЯ ТОЛЬКО НА ОТВЕТЫ ИНТЕРВЬЮ. Не включай шаг, если из ответов не следует,
  что он нужен. Например: не предлагай оформить форму №031/у, если про неё
  не спрашивали и в документах её нет — неизвестно, есть она у семьи или нет.
  Про что нет данных — пиши в explanation соседнего шага или опускай вовсе.
- Если диагноз подтверждён, консультация психиатра для постановки диагноза
  больше не нужна. Дальше идёт динамическое наблюдение — это отдельная услуга.
- Соблюдай зависимости: нельзя идти на МСЭ без формы №031/у, а форма №031/у требует
  заключения психиатра. Отражай это в depends_on.
- Приоритет определяется важностью шага для ТЕКУЩЕГО маршрута, а не тяжестью РАС.
  Если ребёнку скоро в школу, а условий нет — ПМПК это HIGH. Информационная консультация — LOW.
- Сроки в due_in_days ориентировочные, их уточняет куратор. Отталкивайся от сроков справочника.
- В explanation объясни родителю простыми словами, зачем шаг нужен именно их ребёнку.
  Без диагнозов, без медицинских оценок, без терминов без расшифровки.
- 5–8 шагов. Строй ЦЕПОЧКУ целиком, а не один ближайший шаг: если семья в самом
  начале, план выглядит как консультация психиатра -> ВКК и форма №031/у -> МСЭ ->
  ИПАР -> ПМПК, и каждый следующий шаг ссылается на предыдущий в depends_on.
  Родителю важно видеть весь маршрут, а не только первый шаг: именно отсутствие
  такой картины и заставляет семьи ходить по кругу.
- Первым ставь то, что выполнимо прямо сейчас. Остальное идёт следом по зависимостям.
""" + SAFETY


# ───────────── интервью: модель выбирает вопрос, а не придумывает ─────────────

def _question_ids() -> list[str]:
    return [q["question_id"] for q in _demo_questions("ru")]


class RephrasedOption(BaseModel):
    """
    Вариант ответа после переформулировки. value остаётся прежним:
    на этих кодах держится разбор состояния кейса, менять их нельзя.
    """
    value: str = Field(description="Код варианта — скопируй БЕЗ ИЗМЕНЕНИЙ из исходного списка")
    label: str = Field(description="Текст варианта для родителя; можно смягчить формулировку")


def _decision_model(rephrase: bool):
    """
    Схема решения по интервью. next_question_id ограничен каноническим
    списком ТЗ, поэтому модель не может придумать свой вопрос или задать
    несколько вопросов об одном и том же.

    При rephrase модель дополнительно формулирует тот же вопрос живым языком
    с учётом уже сказанного. Тема при этом остаётся канонической.
    """
    ids = tuple(_question_ids()) + ("NONE",)
    fields = dict(
        is_complete=(bool, Field(description="true, когда собрано достаточно для построения плана")),
        next_question_id=(Literal[ids], Field(  # type: ignore[valid-type]
            description="Код следующего вопроса из списка, либо NONE если интервью завершено")),
        skip_reason=(str, Field(default="", description=(
            "Если какие-то вопросы пропущены, потому что ответ уже известен из "
            "предыдущих реплик — перечисли их коды и причину. Иначе пустая строка"))),
        acknowledgement=(str, Field(default="", description=(
            "Короткая человечная реакция на предыдущий ответ, одно предложение. "
            "Без медицинских оценок и без диагнозов"))),
        clarification=(str, Field(default="", description=(
            "Пояснение простыми словами, если из последнего ответа видно, что родитель "
            "не понимает термин. Иначе пустая строка"))),
    )
    if rephrase:
        fields.update(
            question_text=(str, Field(description=(
                "ОБЯЗАТЕЛЬНО заполни. Тот же вопрос, обращённый к этой конкретной семье "
                "с учётом уже сказанного. СМЫСЛ и ТЕМА совпадают с каноническим вопросом — "
                "это переформулировка, а не новый вопрос. Одно предложение, живым языком, "
                "без канцелярита и без терминов без расшифровки"))),
            why_text=(str, Field(description=(
                "ОБЯЗАТЕЛЬНО заполни. Одно предложение: зачем этот вопрос нужен именно "
                "этой семье, со ссылкой на то, что она уже рассказала"))),
            options=(list[RephrasedOption], Field(description=(
                "ОБЯЗАТЕЛЬНО перечисли ВСЕ варианты исходного вопроса: те же value, "
                "человечные label. Ни одного не пропусти и не добавь. "
                "Для вопроса без вариантов — пустой список"))),
        )
    return create_model("InterviewDecision", **fields)


DECISION_SYSTEM = """Ты ведёшь адаптивное интервью с родителем ребёнка с расстройством аутистического спектра в Казахстане.

Вопросы уже написаны и пронумерованы — ты их НЕ придумываешь. Твоя работа: решить,
какой вопрос задать следующим, и какие пропустить.

ПРАВИЛА:
1. Задавай вопросы в порядке списка, пропуская те, ответ на которые уже однозначно
   следует из предыдущих ответов. Пропуск обязательно объясни в skip_reason.
2. Пропускать можно только при однозначном ответе. Примеры:
   - родитель отметил «Заключение ПМПК» среди документов -> пропусти PMPC;
   - родитель выбрал «Уже получили инвалидность» -> пропусти DISABILITY;
   - диагноза ещё нет («только предположение») -> пропусти DISABILITY и SERVICES,
     оформлять пока нечего.
3. НИКОГДА не пропускай вопрос просто потому, что он кажется неважным. Если
   сомневаешься — задай. Недостающий ответ дороже лишнего вопроса.
4. Один вопрос на одну тему. Повторно уточнять то же самое другими словами запрещено.
5. Когда заданы все применимые вопросы — is_complete = true, next_question_id = NONE.
6. Если из ответа видно, что родитель не понимает термин, объясни его в clarification
   простыми словами. Диагноз при этом не обсуждается.
""" + SAFETY

REPHRASE_RULES = """

ФОРМУЛИРОВКА ВОПРОСА (question_text, why_text, options):
Канонический вопрос задаёт ТЕМУ. Ты формулируешь его живым языком, связывая
с тем, что родитель уже рассказал. Правила:
- Смысл не меняется. «Какие документы у вас есть» нельзя превратить
  в «расскажите о вашей ситуации».
- Опирайся на сказанное: если родитель назвал возраст 6 лет и скоро школа —
  вопрос про ПМПК уместно связать с поступлением.
- Коды вариантов (value) копируй БУКВАЛЬНО. Менять их запрещено: на них
  держится вся дальнейшая логика. Смягчать можно только видимый текст (label).
- Перечисляй ВСЕ варианты исходного вопроса — ни одного не убирай и не добавляй.
- Одно предложение. Без канцелярита, без терминов без расшифровки.
- Поля question_text, why_text и options заполняй ВСЕГДА, а не только когда
  видишь необходимость. Родитель должен слышать живого собеседника, который
  помнит предыдущие ответы, а не анкету.

Пример. Канонический вопрос: «Проходили ли вы ПМПК?»
Родитель до этого сказал, что ребёнку 6 лет и он ходит в обычный детский сад.
Хорошая формулировка: «Аминe скоро в школу — проходили ли вы уже ПМПК,
где определяют, какие условия нужны ребёнку для учёбы?»
Плохая: «Расскажите о вашем образовательном маршруте» — тема подменена.
"""


# ───────────────── что семья уже прошла (общая логика) ─────────────────

def unverified_services(state: CaseState) -> set[str]:
    """
    Услуги, про которые интервью НЕ дало ответа. Ставить такой шаг в план —
    значит гадать. Такие шаги не включаются, а попадают в список уточнений,
    который куратор разбирает при проверке плана.

    Важно различать два случая. «Родитель ответил на вопрос о документах и
    формы №031/у среди них нет» — это знание: форму нужно оформить. А вот
    «вопрос о документах вообще не задавали» — незнание, и тогда шаг ставить
    нельзя. Раньше эти случаи смешивались, и форма пропадала из плана даже
    тогда, когда родитель прямо сказал, что документов у него нет.
    """
    unknown: set[str] = set()
    not_asked = set(state.missing_data)

    # Про документы не спрашивали — значит про форму №031/у ничего не известно
    if "DOCUMENTS" in not_asked and not (state.has_disability or state.has_pmpc_conclusion):
        unknown.add("VKK_CONCLUSION")

    # Фармакотерапию отдельным вопросом не выясняли — контроль дозы не назначаем
    if not state.on_medication:
        unknown.add("MEDICATION_TITRATION_CONTROL")

    return unknown


def derive_stage(state: CaseState) -> TrackStage:
    """
    Этап межведомственного трека выводится из документов семьи, а не из
    оценки модели: модель регулярно называла диагностическим этап семьи,
    у которой уже оформлена инвалидность. Порядок проверок — от позднего
    этапа к раннему.
    """
    if state.child_age >= 14:
        return TrackStage.VOCATIONAL
    if state.has_pmpc_conclusion:
        return TrackStage.REHABILITATION if state.services_receiving else TrackStage.EDUCATIONAL
    if state.has_ipar or state.has_disability:
        return TrackStage.EDUCATIONAL
    if state.has_diagnosis:
        return TrackStage.SOCIAL_LEGAL
    return TrackStage.DIAGNOSTIC


def completed_services(state: CaseState) -> set[str]:
    """
    Услуги, которые семья уже получила. Выводится из состояния, а не из
    доверия к модели: наличие инвалидности означает, что и МСЭ, и форма
    №031/у, и консультация психиатра уже позади — иначе инвалидность
    не оформили бы.
    """
    done: set[str] = set(state.services_receiving)

    if state.has_diagnosis:
        # диагноз уже поставлен врачом: направлять к психиатру снова незачем,
        # дальше идёт динамическое наблюдение, а это отдельная услуга
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
    Убирает шаги, которые семья уже прошла, и шаги, про которые интервью
    не дало данных. Повторяющиеся услуги (динамическое наблюдение) остаются.
    Возвращает (оставшиеся, причины отсева для журнала куратора).
    """
    done = completed_services(state)
    unknown = unverified_services(state)
    kept, dropped = [], []
    for it in items:
        sid = it.service_id if hasattr(it, "service_id") else it["service_id"]
        svc = catalog.by_id(sid) or {}
        if sid in done and not svc.get("recurring"):
            dropped.append(f"{sid}: у семьи это уже есть")
            continue
        if sid in unknown:
            dropped.append(f"{sid}: об этом не спрашивали — нужно уточнить у родителя")
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

    questions = {q["question_id"]: q for q in _demo_questions(lang)}
    answered = {h.get("question_id", "") for h in history}
    remaining = [qid for qid in questions if qid not in answered]

    if not remaining:
        return InterviewStep(is_complete=True, progress_current=len(history),
                             progress_total=len(history), next_question=None,
                             acknowledgement=DONE_MSG.get(lang, DONE_MSG["ru"])), "canon"

    transcript = "\n".join(
        f"[{h.get('question_id','?')}] {h['question']}\n   ответ: {h['answer']}"
        for h in history
    ) or "(интервью только начато)"

    catalogue = "\n".join(
        f"- {qid}: {questions[qid]['text']}" + ("  [УЖЕ ЗАДАН]" if qid in answered else "")
        for qid in questions
    )

    rephrase = INTERVIEW_MODE == "adaptive"

    try:
        Decision = _decision_model(rephrase)
        r = client.responses.parse(
            model=MODEL,
            instructions=DECISION_SYSTEM + (REPHRASE_RULES if rephrase else "")
                         + f"\n\nЯзык общения: {lang}.",
            input=(f"СПИСОК ВОПРОСОВ:\n{catalogue}\n\n"
                   f"ХОД ИНТЕРВЬЮ:\n{transcript}\n\n"
                   f"Ещё не заданы: {', '.join(remaining)}.\n"
                   "Какой вопрос задать следующим?"),
            text_format=Decision,
        )
        d = r.output_parsed

        qid = d.next_question_id
        # страховка: модель могла выбрать уже заданный вопрос или NONE раньше времени
        if qid in answered or qid == "NONE":
            if d.is_complete or not remaining:
                return InterviewStep(is_complete=True, progress_current=len(history),
                                     progress_total=len(history), next_question=None,
                                     acknowledgement=d.acknowledgement or DONE_MSG.get(lang, DONE_MSG["ru"])), "openai"
            qid = remaining[0]

        q = dict(questions[qid])

        # Переформулировка принимается только если она не ломает разбор ответов:
        # набор кодов вариантов обязан совпасть с каноническим до единого значения.
        if rephrase:
            text = (getattr(d, "question_text", "") or "").strip()
            if text:
                q["text"] = text
            why = (getattr(d, "why_text", "") or "").strip()
            if why:
                q["why"] = why

            opts = getattr(d, "options", None) or []
            if q["options"]:
                canon = {o["value"] for o in q["options"]}
                got = {o.value for o in opts}
                if opts and got == canon:
                    labels = {o.value: o.label.strip() for o in opts if o.label.strip()}
                    q["options"] = [{"value": o["value"], "label": labels.get(o["value"], o["label"])}
                                    for o in q["options"]]      # порядок сохраняем канонический
                elif opts:
                    print(f"[ai] переформулировка вариантов отклонена для {qid}: "
                          f"лишние {got - canon}, потерянные {canon - got}")

        # пояснение от модели дополняет заготовленное, а не заменяет его
        if d.clarification:
            q["clarification"] = d.clarification

        if d.skip_reason:
            print(f"[ai] пропущены вопросы: {d.skip_reason}")

        return InterviewStep(
            is_complete=False,
            progress_current=len(history) + 1,
            progress_total=min(MAX_QUESTIONS, len(history) + len(remaining)),
            next_question=InterviewQuestion(**q),
            acknowledgement=d.acknowledgement,
        ), "openai"

    except Exception as e:                                   # noqa: BLE001
        print(f"[ai] выбор вопроса — переход в канон: {type(e).__name__}: {e}")
        return _demo_next_question(history, lang), "canon-fallback"


def extract_state(history: list[dict]) -> tuple[CaseState, str]:
    client = _client()
    if client is None:
        return _demo_state(history), "demo"

    transcript = "\n".join(f"Вопрос: {h['question']}\nОтвет: {h['answer']}" for h in history)
    try:
        r = client.responses.parse(
            model=MODEL,
            instructions=(
                "Извлеки структурированное состояние кейса из интервью. "
                "Ничего не домысливай: чего нет в ответах — в missing_data.\n\n"
                "parent_phase определяй по ответу о самочувствии и по этапу маршрута:\n"
                "- диагноз только предположили -> SHOCK;\n"
                "- отвечает «очень тяжело, сил почти нет» или «справляюсь один, поддержки нет» -> DEPRESSION;\n"
                "- отвечает «тяжело, но держусь» -> BARGAINING;\n"
                "- отвечает «в целом справляюсь» и маршрут идёт -> ACCEPTANCE;\n"
                "- ответа о самочувствии нет -> UNKNOWN.\n"
                "parent_needs_support = true, если родитель сообщил о сильной усталости, "
                "выгорании или отсутствии поддержки.\n\n"
                "В missing_data перечисли КОДЫ вопросов, на которые ответа не было "
                "(REGION, CHILD_AGE, STAGE, DIAGNOSIS, DOCUMENTS, PMPC, EDUCATION, "
                "SERVICES, DISABILITY, CONTACTED, PROBLEMS, PARENT_STATE). "
                "Это критично: по этому списку система решает, о чём нельзя строить догадки.\n"
            ) + SAFETY,
            input=transcript,
            text_format=CaseState,
        )
        st = r.output_parsed
        st.current_stage = derive_stage(st)      # этап считаем сами
        return st, "openai"
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

    chains = []
    for svc in catalog.eligible(state.region.value, state.child_age):
        pre = svc.get("prerequisites") or []
        if pre:
            chains.append(f"  {svc['id']} возможен только после: {', '.join(pre)}")

    prompt = f"""СПРАВОЧНИК УСЛУГ (только из него можно брать шаги):
{services_text}

ОБЯЗАТЕЛЬНЫЙ ПОРЯДОК (нарушать нельзя — это требование процедуры, а не пожелание):
{chr(10).join(chains)}
Шаг, предпосылка которого не выполнена и не входит в этот же план, будет отброшен.

ПЛОЩАДКИ РЕГИОНА:
{json.dumps(facilities, ensure_ascii=False, indent=1)}

СОСТОЯНИЕ СЕМЬИ:
{state.model_dump_json(indent=1)}

ТОН: {TONE.get(state.parent_phase.value, TONE['UNKNOWN'])}

ВНИМАНИЕ: этап семьи уже определён — {state.current_stage.value}. В summary опирайся
именно на него, не переопределяй. Если инвалидность оформлена, семья точно не на
диагностическом этапе.

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
        kept, impossible = enforce_prerequisites(kept, state, lang)
        plan.items = _renumber(kept)
        return plan, "openai", rejected + already + impossible
    except Exception as e:                                   # noqa: BLE001
        print(f"[ai] план — переход в demo: {type(e).__name__}: {e}")
        return _demo_plan(state, lang), "demo-fallback", []


def enforce_prerequisites(items: list, state: CaseState, lang: str = "ru") -> tuple[list, list[str]]:
    """
    Приводит план в административно исполнимый вид.

    Модель регулярно выдаёт шаг, минуя предпосылку: например, МСЭ у семьи,
    где формы №031/у ещё нет. МСЭ проводится на основании этой формы, а её
    оформляет ВКК — порядок здесь требование процедуры, а не пожелание.

    Недостающую предпосылку ДОСТРАИВАЕМ, а не выбрасываем зависимый шаг:
    семье нужен весь маршрут, и удаление превращало план в пустой список.
    Выбрасываем только то, чего нельзя достроить — если услуга недоступна
    региону или возрасту.
    """
    done = completed_services(state)
    unknown = unverified_services(state)
    allowed = {x["id"] for x in catalog.eligible(state.region.value, state.child_age)}

    kept = list(items)
    notes: list[str] = []

    for _ in range(6):                       # цепочки в каталоге короткие
        planned = {(i.service_id if hasattr(i, "service_id") else i["service_id"]) for i in kept}
        added = False

        for it in list(kept):
            sid = it.service_id if hasattr(it, "service_id") else it["service_id"]
            prereqs = (catalog.by_id(sid) or {}).get("prerequisites") or []
            for pre in prereqs:
                if pre in done or pre in planned:
                    continue
                svc = catalog.by_id(pre)
                if not svc or pre not in allowed or pre in unknown:
                    kept.remove(it)
                    notes.append(f"{sid}: невозможно без {pre}")
                    added = True
                    break
                kept.insert(kept.index(it), _item_from_service(svc, len(kept) + 1, lang))
                planned.add(pre)
                notes.append(f"{pre}: добавлен — без него {sid} невозможен")
                added = True
            if added:
                break

        if not added:
            break

    # шаги идут в порядке зависимостей: предпосылка раньше того, что её требует
    order = {sid: n for n, sid in enumerate(
        [x["id"] for x in catalog.services()])}
    kept.sort(key=lambda i: order.get(i.service_id if hasattr(i, "service_id") else i["service_id"], 99))

    return kept, notes


def _item_from_service(svc: dict, n: int, lang: str = "ru") -> CasePlanItem:
    """Шаг, собранный прямо из справочника, — для достройки цепочки."""
    return CasePlanItem(
        id=f"CP-{n:03d}",
        service_id=svc["id"],
        title=svc["title"].get(lang, svc["title"]["ru"]),
        description=svc["purpose"].get(lang, svc["purpose"]["ru"]),
        priority=Priority(svc["default_priority"]),
        responsible_role=svc["responsible_role"],
        due_in_days=svc["default_duration_days"],
        documents=[{"name": d, "status": "missing"} for d in svc.get("required_documents", [])],
        explanation=svc["purpose"].get(lang, svc["purpose"]["ru"]),
        depends_on=[],
        already_done=False,
    )


def _renumber(items: list) -> list:
    """
    Нумерует шаги подряд и заново выводит depends_on из справочника:
    после достройки цепочки ссылки модели уже не соответствуют плану.
    """
    for n, it in enumerate(items, 1):
        if hasattr(it, "id"):
            it.id = f"CP-{n:03d}"
        else:
            it["id"] = f"CP-{n:03d}"

    by_service = {(i.service_id if hasattr(i, "service_id") else i["service_id"]):
                  (i.id if hasattr(i, "id") else i["id"]) for i in items}

    for it in items:
        sid = it.service_id if hasattr(it, "service_id") else it["service_id"]
        prereqs = (catalog.by_id(sid) or {}).get("prerequisites") or []
        deps = [by_service[p] for p in prereqs if p in by_service]
        if hasattr(it, "depends_on"):
            it.depends_on = deps
        else:
            it["depends_on"] = deps
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
    has_diag = (a.get("DIAGNOSIS") == "YES" or "DOCTOR" in docs
                or stage not in ("SUSPECTED", "UNKNOWN", ""))

    cur = TrackStage.DIAGNOSTIC      # уточняется ниже через derive_stage

    pstate = a.get("PARENT_STATE", "")
    phase = {"EXHAUSTED": ParentPhase.DEPRESSION, "ALONE": ParentPhase.DEPRESSION,
             "HARD": ParentPhase.BARGAINING}.get(pstate, ParentPhase.UNKNOWN)
    if stage == "SUSPECTED":
        phase = ParentPhase.SHOCK

    doc_names = {"DOCTOR": "Заключение врача-психиатра", "FORM_031": "Форма №031/у", "PMPC": "Заключение ПМПК",
                 "DISABILITY": "Справка об инвалидности", "IPAR": "ИПАР",
                 "SCHOOL": "Характеристика из организации образования", "REHAB": "Документы о реабилитации"}

    try:
        age = float(str(a.get("CHILD_AGE", "5")).replace(",", ".").strip() or 5)
    except ValueError:
        age = 5.0

    st = CaseState(
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
    st.current_stage = derive_stage(st)
    return st


def _demo_plan(state: CaseState, lang: str) -> GeneratedCasePlan:
    """Планировщик по зависимостям каталога: берём то, что доступно и ещё не сделано."""
    eligible = catalog.eligible(state.region.value, state.child_age)
    have_docs = set(state.documents_available)
    done = completed_services(state)
    unknown = unverified_services(state)

    items: list[CasePlanItem] = []
    n = 0
    for s in eligible:
        if len(items) >= 8:
            break
        sid = s["id"]
        if sid in done and not s.get("recurring"):
            continue
        if sid in unknown:
            continue
        if s.get("conditional") == "only_if_medication" and not state.on_medication:
            continue
        if s.get("for_parent") and not state.parent_needs_support:
            continue
        # зависимости: включаем, только если предпосылка выполнена или тоже попала в план
        prereqs = s.get("prerequisites") or []
        planned = {i.service_id for i in items}
        if any(p not in done and p not in planned for p in prereqs):
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
