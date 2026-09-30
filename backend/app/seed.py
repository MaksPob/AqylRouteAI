"""
Два синтетических кейса из ТЗ и демонстрационные пользователи.

Данные вымышленные. Кейсы подобраны контрастно: первый показывает
построение маршрута с нуля, второй — остановившийся маршрут
с просрочкой, блокером и эскалацией.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from . import ai, catalog, db

USERS = [
    ("parent",  "parent123",  "parent",  "Айгуль Сериковна",  "ASTANA"),
    ("parent2", "parent123",  "parent",  "Марат Жанболатович", "KARAGANDA"),
    ("curator", "curator123", "curator", "Динара Кайратовна",  "ASTANA"),
]

CASE_1 = [  # «Раннее начало»: 3 года, диагноз предположили, документов нет
    ("REGION", "В каком городе или области вы сейчас живёте?", "ASTANA"),
    ("CHILD_AGE", "Сколько лет ребёнку?", "3"),
    ("STAGE", "На каком этапе вы сейчас?", "SUSPECTED"),
    ("DIAGNOSIS", "Подтверждён ли диагноз врачом-психиатром?", "NO"),
    ("DOCUMENTS", "Какие документы у вас уже есть?", "NONE"),
    ("PMPC", "Проходили ли вы ПМПК?", "WHAT"),
    ("EDUCATION", "Где сейчас ребёнок получает образование?", "HOME"),
    ("CONTACTED", "Куда вы уже обращались?", "CLINIC"),
    ("PROBLEMS", "Есть ли незавершённое обращение или проблема?", "LOST"),
    ("PARENT_STATE", "А как вы сами сейчас справляетесь?", "HARD"),
]

CASE_2 = [  # «Застрявший маршрут»: 6 лет, инвалидность есть, ИПАР не исполняется
    ("REGION", "В каком городе или области вы сейчас живёте?", "KARAGANDA"),
    ("CHILD_AGE", "Сколько лет ребёнку?", "6"),
    ("STAGE", "На каком этапе вы сейчас?", "HAS_DISABILITY"),
    ("DIAGNOSIS", "Подтверждён ли диагноз врачом-психиатром?", "YES"),
    ("DOCUMENTS", "Какие документы у вас уже есть?", "DOCTOR,FORM_031,DISABILITY,IPAR"),
    ("EDUCATION", "Где сейчас ребёнок получает образование?", "KINDERGARTEN"),
    ("SERVICES", "Какие услуги ребёнок получает сейчас?", "NONE"),
    ("CONTACTED", "Куда вы уже обращались?", "CLINIC,SOCIAL,REHAB"),
    ("PROBLEMS", "Есть ли незавершённое обращение или проблема?", "SERVICE_NOT_PROVIDED,OVERDUE"),
    ("PARENT_STATE", "А как вы сами сейчас справляетесь?", "EXHAUSTED"),
]


def _build(owner_id: int, answers: list[tuple[str, str, str]], child_name: str) -> str:
    region = next(a for q, _, a in answers if q == "REGION")
    age = float(next(a for q, _, a in answers if q == "CHILD_AGE"))
    cid = db.create_case(owner_id, region, age, child_name)
    for qid, q, a in answers:
        db.add_answer(cid, qid, q, a)

    # Демонстрационные кейсы строятся фиксированным планировщиком, а не живой
    # моделью: на защите они должны выглядеть одинаково при каждом запуске.
    # Кейсы, которые создают пользователи, по-прежнему проходят через OpenAI.
    state = ai._demo_state(db.get_answers(cid))
    plan = ai._demo_plan(state, "ru")
    engine = "deterministic"
    db.save_plan(cid, plan.items)
    db.update_case(cid, region=state.region.value, child_age=state.child_age,
                   case_status="active", summary=plan.summary,
                   parent_support_note=plan.parent_support_note,
                   state_json=state.model_dump_json(), engine=engine)
    db.add_event(cid, "case_created", "Система", "Синтетический кейс создан для демонстрации")
    db.add_event(cid, "plan_generated", "AI", f"Сформирован план из {len(plan.items)} шагов")
    return cid


def seed_facilities() -> None:
    """
    Переносит площадки из статического справочника в редактируемую базу.
    Дальше их ведёт куратор: адреса и телефоны меняются, а ПМПК и МСЭК
    различаются по районам — держать это в коде нельзя.
    """
    if db.list_facilities(only_active=False):
        return

    regions = catalog.catalog()["regions"]
    n = 0
    for region, cfg in regions.items():
        for service_id, places in (cfg.get("facilities") or {}).items():
            for place in places:
                db.add_facility({
                    "name": place["name"],
                    "service_id": service_id,
                    "region": region,
                    "portal": place.get("portal", ""),
                    "note": place.get("note", ""),
                }, created_by="Справочник")
                n += 1
    if n:
        print(f"[seed] организаций перенесено в справочник: {n}")


def ensure_seed() -> None:
    seed_facilities()
    if db.list_cases():
        return

    ids: dict[str, int] = {}
    for login, pwd, role, name, region in USERS:
        try:
            ids[login] = db.create_user(login, pwd, role, name, region)
        except Exception:                                    # noqa: BLE001
            pass

    parent1 = ids.get("parent")
    parent2 = ids.get("parent2")
    curator = ids.get("curator")
    if not parent1:
        return

    # Кейс 1: семья уже работает по плану, но куратор его ещё не просматривал —
    # в панели куратора он помечен как непроверенный
    _build(parent1, CASE_1, "Алихан")

    # Кейс 2 подтверждён и уже «прожил» какое-то время: есть выполненное,
    # просроченное и заблокированное — именно на нём видна ценность продукта
    cid2 = _build(parent2, CASE_2, "Амина")
    db.confirm_all_items(cid2)
    db.update_case(cid2, case_status="active", curator_id=curator,
                   confirmed_at=datetime.now().isoformat())
    db.add_event(cid2, "plan_confirmed", "Динара Кайратовна", "Куратор подтвердил план")

    items = db.get_items(cid2)
    if items:
        # шаг выполнен
        db.update_item(cid2, items[0]["item_code"], status="DONE")
        db.add_event(cid2, "curator_status", "Динара Кайратовна",
                     f"Шаг {items[0]['item_code']} выполнен", items[0]["item_code"])

    # ПМПК просрочен на 12 дней — порог ESCALATION
    pmpc = next((i for i in items if i["service_id"] == "PMPC_APPLICATION"), None)
    if pmpc:
        db.update_item(cid2, pmpc["item_code"],
                       due_date=(date.today() - timedelta(days=12)).isoformat(), status="TODO")
        db.add_event(cid2, "overdue", "Система",
                     f"Шаг {pmpc['item_code']} просрочен: ребёнку скоро в школу, условия не определены",
                     pmpc["item_code"])

    # Услуга включена в ИПАР, но организация её не предоставляет — это и есть
    # главный сюжет кейса. Если планировщик такой шаг не выдал (например, он
    # зависит от ещё не пройденного ПМПК), добавляем его явно: родитель прямо
    # сказал, что услуга назначена и не оказывается.
    items = db.get_items(cid2)
    blocked = next((i for i in items if i["service_id"] in ("REHABILITATION_REFERRAL", "EDUCATIONAL_SUPPORT",
                                                            "PSYCHOLOGICAL_PEDAGOGICAL_SUPPORT")), None)
    if blocked is None:
        svc = catalog.by_id("PSYCHOLOGICAL_PEDAGOGICAL_SUPPORT")
        code = f"CP-{len(items) + 1:03d}"
        with db.conn() as c:
            c.execute(
                "INSERT INTO plan_items(case_id,item_code,service_id,title,description,explanation,"
                "priority,responsible_role,due_date,status,documents_json,depends_on_json,created_by,"
                "confirmed_by_curator,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (cid2, code, svc["id"], svc["title"]["ru"], svc["purpose"]["ru"],
                 "Услуга включена в ИПАР, поэтому организация обязана её предоставить.",
                 "HIGH", svc["responsible_role"],
                 (date.today() - timedelta(days=5)).isoformat(), "TODO", "[]", "[]", "curator", 1,
                 datetime.now().isoformat()),
            )
        items = db.get_items(cid2)
        blocked = next(i for i in items if i["item_code"] == code)

    if blocked:
        db.update_item(cid2, blocked["item_code"], status="BLOCKED",
                       due_date=(date.today() - timedelta(days=5)).isoformat(),
                       blocker={"type": "WAITING_FOR_ORGANIZATION",
                                "description": "Услуга включена в ИПАР, но организация не предоставляет её третий месяц"})
        db.add_event(cid2, "blocked", "Система",
                     f"Шаг {blocked['item_code']} заблокирован: ждём организацию", blocked["item_code"])
