"""AqylRoute AI — FastAPI. Межведомственный маршрут семьи ребёнка с РАС."""
from __future__ import annotations

import json
import os
import secrets
from datetime import date, datetime
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import ai, catalog, db, deadline, phq9
from .schemas import CaseState

# .env читаем вручную — без лишней зависимости
_env = Path(__file__).resolve().parent.parent.parent / ".env"
if _env.exists():
    for line in _env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

app = FastAPI(title="AqylRoute AI", version="1.0")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    db.init()
    # мягкая миграция: колонка добавлена позже схемы
    with db.conn() as c:
        cols = {r["name"] for r in c.execute("PRAGMA table_info(cases)")}
        if "needs_clarification" not in cols:
            c.execute("ALTER TABLE cases ADD COLUMN needs_clarification TEXT DEFAULT '[]'")
    from .seed import ensure_seed
    ensure_seed()
    n = db.purge_abandoned()
    if n:
        print(f"[db] удалено брошенных пустых интервью: {n}")


# ─────────────────────────── авторизация ───────────────────────────

def current_user(authorization: Annotated[str | None, Header()] = None) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Требуется вход в систему")
    u = db.user_by_token(authorization[7:])
    if not u:
        raise HTTPException(401, "Сессия истекла, войдите заново")
    return u


def curator_only(u: Annotated[dict, Depends(current_user)]) -> dict:
    if u["role"] != "curator":
        raise HTTPException(403, "Действие доступно только куратору")
    return u


class LoginIn(BaseModel):
    login: str
    password: str


class RegisterIn(BaseModel):
    login: str
    password: str
    display_name: str
    region: str = "ASTANA"
    role: str = "parent"
    invite_code: str = ""


# Куратор видит кейсы всех семей, поэтому эта роль выдаётся по коду,
# а не свободной регистрацией. Код задаётся в .env, значение по умолчанию —
# только для демонстрации.
CURATOR_INVITE = os.getenv("CURATOR_INVITE_CODE", "KMU-2026")


@app.post("/api/auth/register")
def register(body: RegisterIn):
    login = body.login.strip().lower()

    if len(login) < 3 or not all(c.isalnum() or c in "._-" for c in login):
        raise HTTPException(400, "Логин: минимум 3 символа, латиница, цифры, точка, дефис или подчёркивание")
    if len(body.password) < 6:
        raise HTTPException(400, "Пароль должен быть не короче 6 символов")
    if not body.display_name.strip():
        raise HTTPException(400, "Укажите, как к вам обращаться")
    if body.region not in ("ASTANA", "KARAGANDA", "ALMATY"):
        raise HTTPException(400, "Выберите регион из списка")
    if body.role not in ("parent", "curator"):
        raise HTTPException(400, "Недопустимая роль")
    if body.role == "curator" and body.invite_code.strip() != CURATOR_INVITE:
        raise HTTPException(403, "Неверный код куратора. Роль куратора выдаётся организацией")

    try:
        db.create_user(login, body.password, body.role, body.display_name.strip(), body.region)
    except Exception as e:                                   # noqa: BLE001
        if "UNIQUE" in str(e).upper():
            raise HTTPException(409, "Такой логин уже занят, выберите другой") from e
        raise HTTPException(500, "Не удалось создать учётную запись") from e

    r = db.authenticate(login, body.password)
    if not r:
        raise HTTPException(500, "Учётная запись создана, но войти не удалось")
    return r


@app.post("/api/auth/login")
def login(body: LoginIn):
    r = db.authenticate(body.login, body.password)
    if not r:
        raise HTTPException(401, "Неверный логин или пароль")
    return r


@app.post("/api/auth/logout")
def do_logout(authorization: Annotated[str | None, Header()] = None):
    if authorization and authorization.startswith("Bearer "):
        db.logout(authorization[7:])
    return {"ok": True}


@app.get("/api/auth/me")
def me(u: Annotated[dict, Depends(current_user)]):
    return {"id": u["id"], "login": u["login"], "role": u["role"],
            "display_name": u["display_name"], "region": u["region"]}


# ─────────────────────────── справочники ───────────────────────────

@app.get("/api/catalog")
def get_catalog():
    c = catalog.catalog()
    return {"services": c["services"], "regions": c["regions"],
            "enums": catalog.enums(), "deadlines_are_provisional": True}


@app.get("/api/health")
def health():
    return {"ok": True, "ai_engine": "openai" if os.getenv("OPENAI_API_KEY") else "demo",
            "model": ai.MODEL, "services": len(catalog.service_ids())}


# ───────────────────────────── интервью ─────────────────────────────

class StartIn(BaseModel):
    child_name: str = ""
    lang: str = "ru"


@app.post("/api/cases/start")
def start_case(body: StartIn, u: Annotated[dict, Depends(current_user)]):
    cid = db.create_case(u["id"], u["region"] or "ASTANA", 0.0, body.child_name)
    step, engine = ai.next_question([], body.lang)
    db.add_event(cid, "case_created", u["display_name"], "Кейс создан, начато интервью")
    return {"case_id": cid, "step": step.model_dump(), "engine": engine}


class AnswerIn(BaseModel):
    case_id: str
    question_id: str
    question: str
    answer: str
    lang: str = "ru"


@app.post("/api/interview/answer")
def answer(body: AnswerIn, u: Annotated[dict, Depends(current_user)]):
    case = db.get_case(body.case_id)
    if not case:
        raise HTTPException(404, "Кейс не найден")

    # служебный запрос: вернуть текущий вопрос, ничего не записывая
    if body.question_id != "__resume__":
        db.add_answer(body.case_id, body.question_id, body.question, body.answer)

    # регион и возраст фиксируем сразу — от них зависит фильтрация каталога
    if body.question_id == "REGION" and body.answer in ("ASTANA", "KARAGANDA", "ALMATY"):
        db.update_case(body.case_id, region=body.answer)
    if body.question_id == "CHILD_AGE":
        try:
            db.update_case(body.case_id, child_age=float(str(body.answer).replace(",", ".")))
        except ValueError:
            pass

    history = db.get_answers(body.case_id)
    step, engine = ai.next_question(history, body.lang)
    return {"step": step.model_dump(), "engine": engine, "answered": len(history)}


@app.post("/api/interview/build-plan")
def build_plan(case_id: str, lang: str = "ru", u: dict = Depends(current_user)):
    case = db.get_case(case_id)
    if not case:
        raise HTTPException(404, "Кейс не найден")

    history = db.get_answers(case_id)
    if len(history) < 3:
        raise HTTPException(400, "Слишком мало ответов для построения плана")

    state, eng_state = ai.extract_state(history)
    plan, eng_plan, rejected = ai.build_plan(state, lang)

    db.save_plan(case_id, plan.items)
    db.update_case(
        case_id,
        region=state.region.value,
        child_age=state.child_age,
        case_status="pending_review",
        summary=plan.summary,
        parent_support_note=plan.parent_support_note,
        state_json=state.model_dump_json(),
        engine=f"{eng_state}/{eng_plan}",
    )
    db.add_event(case_id, "plan_generated", "AI",
                 f"Сформирован план из {len(plan.items)} шагов, ожидает проверки куратора")

    # Чего интервью не выяснило — куратор уточняет при проверке. Это честнее,
    # чем ставить шаг наугад: план не должен содержать того, о чём не спрашивали.
    clarify = [r for r in rejected if "не спрашивали" in r]
    db.update_case(case_id, needs_clarification=json.dumps(
        [{"service_id": r.split(":")[0],
          "title": (catalog.by_id(r.split(":")[0]) or {}).get("title", {}).get("ru", r.split(":")[0]),
          "reason": r.split(": ", 1)[1] if ": " in r else r}
         for r in clarify], ensure_ascii=False))

    if rejected:
        db.add_event(case_id, "items_rejected", "Система",
                     "Не включено в план: " + "; ".join(rejected))

    return {"case_id": case_id, "engine": f"{eng_state}/{eng_plan}",
            "rejected": rejected, "plan": plan.model_dump(), "state": state.model_dump()}


# ────────────────────────────── кейсы ──────────────────────────────

def _hydrate(case: dict) -> dict:
    """Собирает кейс целиком и пересчитывает просрочку на момент чтения."""
    items = [deadline.apply(i) for i in db.get_items(case["case_id"])]
    # Статусы OVERDUE и BLOCKED вычисляются здесь, а не хранятся, поэтому
    # пересортировываем после пересчёта: сначала горящее, потом порядок маршрута.
    rank = {"OVERDUE": 0, "BLOCKED": 1, "DONE": 3, "CANCELLED": 4}
    items.sort(key=lambda i: (rank.get(i["status"], 2), i["item_code"]))
    for it in items:
        s = catalog.by_id(it["service_id"]) or {}
        it["stage"] = s.get("stage", "")
        it["authority"] = s.get("authority", "")
        it["facilities"] = catalog.facility_for(case["region"], it["service_id"])
        it["portal"] = s.get("portal", "")
    case = dict(case)
    case["items"] = items
    case["stats"] = deadline.case_summary(items)
    case["state"] = json.loads(case["state_json"]) if case.get("state_json") else None
    case.pop("state_json", None)
    try:
        case["needs_clarification"] = json.loads(case.get("needs_clarification") or "[]")
    except (TypeError, ValueError):
        case["needs_clarification"] = []
    return case


@app.get("/api/cases")
def cases(u: Annotated[dict, Depends(current_user)]):
    rows = db.list_cases() if u["role"] == "curator" else db.list_cases(owner_id=u["id"])
    out = []
    for r in rows:
        h = _hydrate(r)
        out.append({"case_id": h["case_id"], "region": h["region"], "child_age": h["child_age"],
                    "child_name": h["child_name"], "case_status": h["case_status"],
                    "created_at": h["created_at"], "stats": h["stats"],
                    "phq9_score": h.get("phq9_score"), "phq9_severity": h.get("phq9_severity", "")})
    return out


@app.get("/api/cases/{case_id}")
def case_detail(case_id: str, u: Annotated[dict, Depends(current_user)]):
    c = db.get_case(case_id)
    if not c:
        raise HTTPException(404, "Кейс не найден")
    if u["role"] == "parent" and c["owner_id"] != u["id"]:
        raise HTTPException(403, "Это не ваш кейс")

    h = _hydrate(c)
    # родитель не видит план, пока куратор его не подтвердил (п.9 ТЗ)
    if u["role"] == "parent" and c["case_status"] == "pending_review":
        h["items"] = []
        h["pending_notice"] = "Ваш план сформирован и сейчас проверяется куратором. Обычно это занимает немного времени."
    h["events"] = db.get_events(case_id, limit=50)
    h["documents"] = [{k: v for k, v in d.items() if k != "stored_name"} for d in db.get_documents(case_id)]
    h["phq9_history"] = db.get_phq9_history(case_id)
    return h


# ──────────────────────── работа куратора ────────────────────────

class ItemPatch(BaseModel):
    title: str | None = None
    priority: str | None = None
    responsible_role: str | None = None
    due_date: str | None = None
    status: str | None = None
    explanation: str | None = None
    blocker_type: str | None = None
    blocker_description: str | None = None


@app.patch("/api/cases/{case_id}/items/{item_code}")
def patch_item(case_id: str, item_code: str, body: ItemPatch, u: Annotated[dict, Depends(curator_only)]):
    fields: dict = {}
    for k in ("title", "priority", "responsible_role", "due_date", "status", "explanation"):
        v = getattr(body, k)
        if v is not None:
            fields[k] = v
    if body.blocker_type:
        fields["blocker"] = {"type": body.blocker_type, "description": body.blocker_description or ""}
        fields["status"] = "BLOCKED"
    if body.status and body.status != "BLOCKED":
        fields["blocker"] = None

    if not fields:
        raise HTTPException(400, "Нет полей для изменения")

    db.update_item(case_id, item_code, **fields)
    db.add_event(case_id, "item_updated", u["display_name"],
                 f"Куратор изменил шаг {item_code}: " + ", ".join(fields), item_code)
    return _hydrate(db.get_case(case_id))


@app.post("/api/cases/{case_id}/items/{item_code}/delete")
def delete_item(case_id: str, item_code: str, u: Annotated[dict, Depends(curator_only)]):
    db.update_item(case_id, item_code, status="CANCELLED")
    db.add_event(case_id, "item_cancelled", u["display_name"], f"Куратор убрал шаг {item_code} из плана", item_code)
    return _hydrate(db.get_case(case_id))


@app.post("/api/cases/{case_id}/confirm")
def confirm_plan(case_id: str, u: Annotated[dict, Depends(curator_only)]):
    c = db.get_case(case_id)
    if not c:
        raise HTTPException(404, "Кейс не найден")
    db.confirm_all_items(case_id)
    db.update_case(case_id, case_status="active", curator_id=u["id"], confirmed_at=datetime.now().isoformat())
    db.add_event(case_id, "plan_confirmed", u["display_name"], "Куратор подтвердил план, он доступен родителю")
    return _hydrate(db.get_case(case_id))


@app.post("/api/cases/{case_id}/reject")
def reject_plan(case_id: str, reason: str = "", u: dict = Depends(curator_only)):
    db.update_case(case_id, case_status="interview")
    db.add_event(case_id, "plan_rejected", u["display_name"],
                 f"Куратор вернул план на доработку. Причина: {reason or 'не указана'}")
    return {"ok": True}


# ──────────────────── статусы со стороны родителя ────────────────────

class StatusIn(BaseModel):
    status: str
    comment: str = ""


@app.post("/api/cases/{case_id}/items/{item_code}/status")
def set_status(case_id: str, item_code: str, body: StatusIn, u: Annotated[dict, Depends(current_user)]):
    c = db.get_case(case_id)
    if not c:
        raise HTTPException(404, "Кейс не найден")

    if u["role"] == "parent":
        if c["owner_id"] != u["id"]:
            raise HTTPException(403, "Это не ваш кейс")
        # статус применяется сразу, но помечается как «со слов родителя»
        db.update_item(case_id, item_code, status=body.status, parent_reported_status=body.status,
                       confirmed_by_curator=0)
        db.add_event(case_id, "parent_status", u["display_name"],
                     f"Родитель отметил шаг {item_code}: {body.status}" +
                     (f". Комментарий: {body.comment}" if body.comment else ""), item_code)
    else:
        db.update_item(case_id, item_code, status=body.status, parent_reported_status=None, confirmed_by_curator=1)
        db.add_event(case_id, "curator_status", u["display_name"],
                     f"Куратор установил статус шага {item_code}: {body.status}", item_code)

    return _hydrate(db.get_case(case_id))


@app.post("/api/cases/{case_id}/items/{item_code}/verify")
def verify_status(case_id: str, item_code: str, u: Annotated[dict, Depends(curator_only)]):
    db.update_item(case_id, item_code, confirmed_by_curator=1, parent_reported_status=None)
    db.add_event(case_id, "status_verified", u["display_name"], f"Куратор подтвердил статус шага {item_code}", item_code)
    return _hydrate(db.get_case(case_id))


# ───────────────────────────── документы ─────────────────────────────

UPLOADS = Path(__file__).resolve().parent.parent / "uploads"
MAX_UPLOAD = 10 * 1024 * 1024          # 10 МБ

# Разрешаем только то, чем реально бывают справки. Исполняемое и архивы
# не принимаем: файл потом открывает куратор, и это чужое устройство.
ALLOWED_MIME = {
    "application/pdf": ".pdf",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/heic": ".heic",
    "image/webp": ".webp",
}

DOC_TYPES = [
    {"value": "FORM_031", "label": "Форма №031/у (заключение ВКК)"},
    {"value": "DOCTOR", "label": "Заключение врача-психиатра"},
    {"value": "PMPC", "label": "Заключение ПМПК"},
    {"value": "DISABILITY", "label": "Справка об инвалидности"},
    {"value": "IPAR", "label": "ИПАР"},
    {"value": "REHAB", "label": "Документы о реабилитации"},
    {"value": "SCHOOL", "label": "Документы из детского сада или школы"},
    {"value": "OTHER", "label": "Другое"},
]


def _own_case_or_403(case_id: str, u: dict) -> dict:
    c = db.get_case(case_id)
    if not c:
        raise HTTPException(404, "Кейс не найден")
    if u["role"] == "parent" and c["owner_id"] != u["id"]:
        raise HTTPException(403, "Это не ваш кейс")
    return c


@app.get("/api/document-types")
def document_types():
    return DOC_TYPES


@app.get("/api/cases/{case_id}/documents")
def list_documents(case_id: str, u: Annotated[dict, Depends(current_user)]):
    _own_case_or_403(case_id, u)
    return [{k: v for k, v in d.items() if k != "stored_name"} for d in db.get_documents(case_id)]


@app.post("/api/cases/{case_id}/documents")
async def upload_document(
    case_id: str,
    file: Annotated[UploadFile, File()],
    doc_type: Annotated[str, Form()] = "OTHER",
    item_code: Annotated[str, Form()] = "",
    note: Annotated[str, Form()] = "",
    u: dict = Depends(current_user),
):
    _own_case_or_403(case_id, u)

    if file.content_type not in ALLOWED_MIME:
        raise HTTPException(400, "Можно загрузить PDF или фотографию документа (JPG, PNG, HEIC, WEBP)")

    data = await file.read()
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "Файл больше 10 МБ. Сфотографируйте документ с меньшим разрешением")
    if not data:
        raise HTTPException(400, "Файл пустой")

    folder = UPLOADS / case_id
    folder.mkdir(parents=True, exist_ok=True)
    stored = f"{datetime.now():%Y%m%d%H%M%S}-{secrets.token_hex(6)}{ALLOWED_MIME[file.content_type]}"
    (folder / stored).write_bytes(data)

    doc_id = db.add_document(
        case_id, doc_type, file.filename or "документ", stored,
        file.content_type, len(data), u["display_name"],
        item_code or None, note,
    )
    label = next((d["label"] for d in DOC_TYPES if d["value"] == doc_type), doc_type)
    db.add_event(case_id, "document_uploaded", u["display_name"],
                 f"Загружен документ: {label}", item_code or None)

    return {"id": doc_id, "doc_type": doc_type, "original_name": file.filename,
            "size": len(data), "mime": file.content_type}


@app.get("/api/documents/{doc_id}/file")
def download_document(doc_id: int, u: Annotated[dict, Depends(current_user)]):
    d = db.get_document(doc_id)
    if not d:
        raise HTTPException(404, "Документ не найден")
    _own_case_or_403(d["case_id"], u)

    path = UPLOADS / d["case_id"] / d["stored_name"]
    if not path.exists():
        raise HTTPException(410, "Файл больше не доступен")
    return FileResponse(path, media_type=d["mime"], filename=d["original_name"])


@app.post("/api/documents/{doc_id}/delete")
def remove_document(doc_id: int, u: Annotated[dict, Depends(current_user)]):
    d = db.get_document(doc_id)
    if not d:
        raise HTTPException(404, "Документ не найден")
    _own_case_or_403(d["case_id"], u)

    path = UPLOADS / d["case_id"] / d["stored_name"]
    path.unlink(missing_ok=True)
    db.delete_document(doc_id)
    db.add_event(d["case_id"], "document_deleted", u["display_name"],
                 f"Удалён документ: {d['original_name']}")
    return {"ok": True}


# ───────────────────────── PHQ-9 и поддержка ─────────────────────────

@app.get("/api/phq9")
def phq9_form(lang: str = "ru"):
    return {"preamble": phq9.PREAMBLE.get(lang, phq9.PREAMBLE["ru"]),
            "questions": [{"id": q["id"], "text": q.get(lang, q["ru"]), "critical": q.get("critical", False)}
                          for q in phq9.QUESTIONS],
            "options": [{"value": o["value"], "label": o.get(lang, o["ru"])} for o in phq9.OPTIONS],
            "disclaimer": "PHQ-9 — скрининговый инструмент, не диагноз."}


class Phq9In(BaseModel):
    case_id: str
    answers: list[int]


@app.post("/api/phq9")
def phq9_submit(body: Phq9In, u: Annotated[dict, Depends(current_user)]):
    if len(body.answers) != 9:
        raise HTTPException(400, "Нужно ответить на все 9 вопросов")
    r = phq9.score(body.answers)
    db.update_case(body.case_id, phq9_score=r["score"], phq9_severity=r["severity"])
    db.add_phq9(body.case_id, r["score"], r["severity"], r["crisis_flag"])
    db.add_event(body.case_id, "phq9_completed", u["display_name"],
                 f"Пройден скрининг PHQ-9: {r['score']} из 27 ({r['severity']})")
    if r["crisis_flag"]:
        db.add_event(body.case_id, "crisis_flag", "Система",
                     "ВНИМАНИЕ: родитель отметил пункт 9 PHQ-9. Требуется связаться с родителем.")
    return r


# ──────────────────────────── уведомления ────────────────────────────

@app.get("/api/notifications")
def notifications(u: Annotated[dict, Depends(current_user)]):
    """Уведомления собираются из просрочки при каждом запросе — фоновых задач не требуется."""
    rows = db.list_cases() if u["role"] == "curator" else db.list_cases(owner_id=u["id"])
    out = []
    for c in rows:
        if c["case_status"] not in ("active", "pending_review"):
            continue
        h = _hydrate(c)
        for it in h["items"]:
            lvl = it.get("escalation_level", "NONE")
            if lvl == "NONE":
                continue
            visible = (u["role"] == "curator") or lvl in ("NOTIFY_PARENT", "NOTIFY_CURATOR", "ESCALATION", "HIGH_ESCALATION")
            if not visible:
                continue
            out.append({
                "case_id": c["case_id"], "item_code": it["item_code"], "title": it["title"],
                "days_overdue": it["days_overdue"], "level": lvl,
                "action": it.get("escalation_action", ""), "responsible_role": it["responsible_role"],
            })
        if u["role"] == "curator" and c["case_status"] == "pending_review":
            out.append({"case_id": c["case_id"], "item_code": None, "title": "План ожидает проверки",
                        "days_overdue": 0, "level": "REVIEW", "action": "Проверить и подтвердить план",
                        "responsible_role": "CURATOR"})
    out.sort(key=lambda x: -x["days_overdue"])
    return out


@app.get("/api/events")
def events(case_id: str | None = None, u: dict = Depends(current_user)):
    return db.get_events(case_id)
