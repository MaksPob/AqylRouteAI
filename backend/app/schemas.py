"""
Pydantic-модели домена.

Ключевая идея: те же модели, что валидируют данные в базе, передаются
в OpenAI как JSON Schema (structured outputs). Поэтому AI физически
не может вернуть service_id, которого нет в каталоге, или приоритет
вне списка HIGH/MEDIUM/LOW — это ограничение декодера, а не просьба в промпте.
"""
from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


# ─────────────────────────── перечисления ───────────────────────────

class ItemStatus(str, Enum):
    TODO = "TODO"
    IN_PROGRESS = "IN_PROGRESS"
    WAITING = "WAITING"
    DONE = "DONE"
    OVERDUE = "OVERDUE"
    BLOCKED = "BLOCKED"
    CANCELLED = "CANCELLED"


class Priority(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class ResponsibleRole(str, Enum):
    PARENT = "PARENT"
    CLINIC = "CLINIC"
    PSYCHIATRIST = "PSYCHIATRIST"
    VKK = "VKK"
    MSE = "MSE"
    PMPC = "PMPC"
    EDUCATIONAL_ORGANIZATION = "EDUCATIONAL_ORGANIZATION"
    REHABILITATION_CENTER = "REHABILITATION_CENTER"
    SOCIAL_SERVICE = "SOCIAL_SERVICE"
    CURATOR = "CURATOR"


class BlockerType(str, Enum):
    MISSING_DOCUMENT = "MISSING_DOCUMENT"
    WAITING_FOR_ORGANIZATION = "WAITING_FOR_ORGANIZATION"
    NO_APPOINTMENT = "NO_APPOINTMENT"
    PARENT_UNAVAILABLE = "PARENT_UNAVAILABLE"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    UNKNOWN = "UNKNOWN"


class DocumentStatus(str, Enum):
    available = "available"
    missing = "missing"
    in_progress = "in_progress"
    unknown = "unknown"


class TrackStage(str, Enum):
    DIAGNOSTIC = "DIAGNOSTIC"
    SOCIAL_LEGAL = "SOCIAL_LEGAL"
    EDUCATIONAL = "EDUCATIONAL"
    REHABILITATION = "REHABILITATION"
    VOCATIONAL = "VOCATIONAL"


class ParentPhase(str, Enum):
    SHOCK = "SHOCK"
    DENIAL = "DENIAL"
    ANGER = "ANGER"
    BARGAINING = "BARGAINING"
    DEPRESSION = "DEPRESSION"
    ACCEPTANCE = "ACCEPTANCE"
    UNKNOWN = "UNKNOWN"


class Region(str, Enum):
    ASTANA = "ASTANA"
    KARAGANDA = "KARAGANDA"
    ALMATY = "ALMATY"


class CaseStatus(str, Enum):
    interview = "interview"          # родитель проходит интервью
    pending_review = "pending_review"  # AI сформировал план, ждёт куратора
    active = "active"                # куратор подтвердил, план у родителя
    closed = "closed"


class Lang(str, Enum):
    ru = "ru"
    kk = "kk"
    en = "en"


# ─────────────────────── интервью (AI ↔ родитель) ───────────────────

class AnswerOption(BaseModel):
    """Вариант ответа. AI обязан предложить готовые варианты, а не свободный текст."""
    value: str = Field(description="Короткий машинный код варианта, латиницей")
    label: str = Field(description="Текст варианта для родителя на языке интервью")


class InterviewQuestion(BaseModel):
    """
    Один адаптивный вопрос. AI не задаёт вопрос, ответ на который уже известен
    из предыдущих реплик — это требование adaptive interview из ТЗ.
    """
    question_id: str = Field(description="Стабильный код вопроса, например REGION, CHILD_AGE, STAGE")
    text: str = Field(description="Текст вопроса, обращённый к родителю")
    why: str = Field(description="Одно предложение: зачем этот вопрос нужен. Показывается родителю")
    input_type: Literal["single_choice", "multi_choice", "text", "number", "date"]
    options: list[AnswerOption] = Field(default_factory=list, description="Варианты для single_choice и multi_choice; пустой список для остальных типов")
    allow_dont_know: bool = Field(default=True, description="«Не знаю» — всегда допустимый ответ")
    clarification: str = Field(default="", description="Пояснение, если родитель ответил «не знаю, что это». Пустая строка, если не требуется")


class InterviewStep(BaseModel):
    """Ответ AI на очередном шаге интервью."""
    is_complete: bool = Field(description="true, когда собрано достаточно данных для построения плана")
    progress_current: int = Field(description="Номер текущего вопроса, начиная с 1")
    progress_total: int = Field(description="Ожидаемое общее число вопросов, от 8 до 12")
    next_question: InterviewQuestion | None = Field(default=None, description="Следующий вопрос; null, когда is_complete = true")
    acknowledgement: str = Field(default="", description="Короткая человечная реакция на предыдущий ответ. Без медицинских оценок и без диагнозов")


# ───────────────────────── состояние кейса ──────────────────────────

class CaseState(BaseModel):
    """
    Структурированный портрет ситуации семьи, извлечённый из интервью.
    Промежуточный объект между интервью и планом.
    """
    region: Region
    child_age: float = Field(ge=0, le=18, description="Возраст ребёнка в годах")
    current_stage: TrackStage = Field(description="Этап межведомственного трека, на котором семья находится сейчас")
    has_diagnosis: bool
    has_disability: bool
    has_ipar: bool
    has_pmpc_conclusion: bool
    documents_available: list[str] = Field(default_factory=list, description="Названия документов, которые есть у семьи на руках")
    services_receiving: list[str] = Field(default_factory=list, description="service_id услуг, которые ребёнок уже получает")
    organizations_contacted: list[str] = Field(default_factory=list, description="Куда семья уже обращалась — чтобы не отправлять туда повторно")
    open_problems: list[str] = Field(default_factory=list, description="Незавершённые обращения и проблемы со слов родителя")
    parent_phase: ParentPhase = Field(default=ParentPhase.UNKNOWN, description="Психологическая фаза родителя — влияет только на тон объяснений")
    parent_needs_support: bool = Field(default=False, description="true, если родитель сообщил о сильной усталости, выгорании или отсутствии поддержки")
    education_setting: str = Field(default="", description="Где ребёнок получает образование сейчас")
    on_medication: bool = Field(default=False, description="Назначена ли симптоматическая фармакотерапия")
    missing_data: list[str] = Field(default_factory=list, description="Чего не хватает, чтобы план был полным")


# ───────────────────────────── Case Plan ────────────────────────────

class PlanDocument(BaseModel):
    name: str
    status: DocumentStatus


class Blocker(BaseModel):
    type: BlockerType
    description: str


class CasePlanItem(BaseModel):
    """
    Шаг плана. service_id ограничен каталогом на уровне JSON Schema —
    именно здесь отсекаются выдуманные действия.
    """
    id: str = Field(description="Код шага вида CP-001")
    service_id: str = Field(description="ОБЯЗАТЕЛЬНО один из service_id справочника услуг. Выдумывать запрещено")
    title: str = Field(description="Название шага человеческим языком, на языке интервью")
    description: str = Field(description="Что конкретно нужно сделать, одно-два предложения")
    priority: Priority
    responsible_role: ResponsibleRole
    due_in_days: int = Field(ge=1, le=365, description="Через сколько дней от сегодня шаг должен быть выполнен. Срок ориентировочный, куратор его уточняет")
    documents: list[PlanDocument] = Field(default_factory=list)
    explanation: str = Field(description="Объяснение для родителя: зачем этот шаг нужен именно их ребёнку. Без диагнозов и медицинских оценок")
    depends_on: list[str] = Field(default_factory=list, description="id шагов этого же плана, которые нужно выполнить раньше")
    already_done: bool = Field(default=False, description="true, если из интервью следует, что шаг уже выполнен")


class GeneratedCasePlan(BaseModel):
    """Ровно то, что возвращает модель. Валидируется дополнительно на сервере."""
    summary: str = Field(description="Два-три предложения для родителя: где семья сейчас и что происходит дальше. Тон подбирается под психологическую фазу")
    items: list[CasePlanItem] = Field(min_length=1, max_length=15)
    parent_support_note: str = Field(default="", description="Обращение к родителю о его собственном состоянии, если parent_needs_support = true. Иначе пустая строка")


# ───────────────────── то, что хранится и отдаётся ──────────────────

class CasePlanItemOut(CasePlanItem):
    """Шаг после сохранения: добавлены живые поля, которых AI не касается."""
    status: ItemStatus = ItemStatus.TODO
    due_date: date
    blocker: Blocker | None = None
    created_by: Literal["ai", "curator"] = "ai"
    confirmed_by_curator: bool = False
    days_overdue: int = 0
    escalation_level: str = "NONE"
    parent_reported_status: ItemStatus | None = Field(default=None, description="Статус со слов родителя, ожидающий подтверждения куратором")
    updated_at: datetime | None = None


class CaseOut(BaseModel):
    case_id: str
    region: Region
    child_age: float
    child_name: str = ""
    case_status: CaseStatus
    created_at: datetime
    summary: str = ""
    parent_support_note: str = ""
    state: CaseState | None = None
    items: list[CasePlanItemOut] = Field(default_factory=list)
    phq9_score: int | None = None
    phq9_severity: str = ""
