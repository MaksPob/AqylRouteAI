"""
Хранилище на SQLite.

Весь доступ к данным собран в этом модуле, чтобы переезд на Supabase
затронул только его: снаружи используются функции, а не SQL.
"""
from __future__ import annotations

import json
import os
import secrets
import sqlite3
import hashlib
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path

DB_PATH = Path(os.getenv("DB_PATH", Path(__file__).resolve().parent.parent / "aqylroute.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  login TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  salt TEXT NOT NULL,
  role TEXT NOT NULL CHECK(role IN ('parent','curator')),
  display_name TEXT NOT NULL,
  region TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
  token TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id),
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cases (
  case_id TEXT PRIMARY KEY,
  owner_id INTEGER REFERENCES users(id),
  curator_id INTEGER REFERENCES users(id),
  region TEXT NOT NULL,
  child_age REAL NOT NULL,
  child_name TEXT DEFAULT '',
  case_status TEXT NOT NULL,
  summary TEXT DEFAULT '',
  parent_support_note TEXT DEFAULT '',
  state_json TEXT,
  engine TEXT DEFAULT '',
  phq9_score INTEGER,
  needs_clarification TEXT DEFAULT '[]',
  phq9_severity TEXT DEFAULT '',
  created_at TEXT NOT NULL,
  confirmed_at TEXT
);

CREATE TABLE IF NOT EXISTS interview_answers (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  case_id TEXT NOT NULL REFERENCES cases(case_id),
  question_id TEXT NOT NULL,
  question TEXT NOT NULL,
  answer TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS plan_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  case_id TEXT NOT NULL REFERENCES cases(case_id),
  item_code TEXT NOT NULL,
  service_id TEXT NOT NULL,
  title TEXT NOT NULL,
  description TEXT DEFAULT '',
  explanation TEXT DEFAULT '',
  priority TEXT NOT NULL,
  responsible_role TEXT NOT NULL,
  due_date TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'TODO',
  documents_json TEXT DEFAULT '[]',
  depends_on_json TEXT DEFAULT '[]',
  blocker_json TEXT,
  created_by TEXT DEFAULT 'ai',
  confirmed_by_curator INTEGER DEFAULT 0,
  parent_reported_status TEXT,
  already_done INTEGER DEFAULT 0,
  updated_at TEXT
);

CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  case_id TEXT NOT NULL,
  item_code TEXT,
  kind TEXT NOT NULL,
  actor TEXT NOT NULL,
  message TEXT NOT NULL,
  read_by_parent INTEGER DEFAULT 0,
  read_by_curator INTEGER DEFAULT 0,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS documents (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  case_id TEXT NOT NULL REFERENCES cases(case_id),
  item_code TEXT,
  doc_type TEXT NOT NULL,
  original_name TEXT NOT NULL,
  stored_name TEXT NOT NULL,
  mime TEXT NOT NULL,
  size INTEGER NOT NULL,
  uploaded_by TEXT NOT NULL,
  note TEXT DEFAULT '',
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS phq9_history (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  case_id TEXT NOT NULL REFERENCES cases(case_id),
  score INTEGER NOT NULL,
  severity TEXT NOT NULL,
  crisis_flag INTEGER DEFAULT 0,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS facilities (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  service_id TEXT NOT NULL,
  region TEXT NOT NULL,
  district TEXT DEFAULT '',
  address TEXT DEFAULT '',
  phone TEXT DEFAULT '',
  contact_person TEXT DEFAULT '',
  email TEXT DEFAULT '',
  portal TEXT DEFAULT '',
  hours TEXT DEFAULT '',
  note TEXT DEFAULT '',
  is_active INTEGER DEFAULT 1,
  created_by TEXT DEFAULT '',
  created_at TEXT NOT NULL,
  updated_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_fac_region ON facilities(region, service_id);
CREATE INDEX IF NOT EXISTS idx_docs_case ON documents(case_id);
CREATE INDEX IF NOT EXISTS idx_phq_case ON phq9_history(case_id);
CREATE INDEX IF NOT EXISTS idx_items_case ON plan_items(case_id);
CREATE INDEX IF NOT EXISTS idx_events_case ON events(case_id);
"""


@contextmanager
def conn():
    c = sqlite3.connect(DB_PATH, detect_types=0)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with conn() as c:
        c.executescript(SCHEMA)


# ─────────────────────────── пользователи ───────────────────────────

def _hash(password: str, salt: str) -> str:
    """PBKDF2. Для прототипа достаточно; для продакшена следует взять bcrypt или argon2."""
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000).hex()


def create_user(login: str, password: str, role: str, display_name: str, region: str | None = None) -> int:
    salt = secrets.token_hex(16)
    with conn() as c:
        cur = c.execute(
            "INSERT INTO users(login,password_hash,salt,role,display_name,region,created_at) VALUES(?,?,?,?,?,?,?)",
            (login, _hash(password, salt), salt, role, display_name, region, datetime.now().isoformat()),
        )
        return cur.lastrowid


def authenticate(login: str, password: str) -> dict | None:
    with conn() as c:
        u = c.execute("SELECT * FROM users WHERE login=?", (login,)).fetchone()
        if not u or _hash(password, u["salt"]) != u["password_hash"]:
            return None
        token = secrets.token_urlsafe(32)
        c.execute("INSERT INTO sessions(token,user_id,created_at) VALUES(?,?,?)",
                  (token, u["id"], datetime.now().isoformat()))
        return {"token": token, "user": {"id": u["id"], "login": u["login"], "role": u["role"],
                                         "display_name": u["display_name"], "region": u["region"]}}


def user_by_token(token: str) -> dict | None:
    with conn() as c:
        r = c.execute(
            "SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=?", (token,)
        ).fetchone()
        return dict(r) if r else None


def logout(token: str) -> None:
    with conn() as c:
        c.execute("DELETE FROM sessions WHERE token=?", (token,))


# ───────────────────────────── кейсы ─────────────────────────────

def new_case_id() -> str:
    with conn() as c:
        n = c.execute("SELECT COUNT(*) n FROM cases").fetchone()["n"]
    return f"CASE-{n + 1:06d}"


def create_case(owner_id: int | None, region: str, child_age: float, child_name: str = "") -> str:
    cid = new_case_id()
    with conn() as c:
        c.execute("INSERT INTO cases(case_id,owner_id,region,child_age,child_name,case_status,created_at) "
                  "VALUES(?,?,?,?,?,?,?)",
                  (cid, owner_id, region, child_age, child_name, "interview", datetime.now().isoformat()))
    return cid


def get_case(case_id: str) -> dict | None:
    with conn() as c:
        r = c.execute("SELECT * FROM cases WHERE case_id=?", (case_id,)).fetchone()
        return dict(r) if r else None


def update_case(case_id: str, **fields) -> None:
    if not fields:
        return
    sets = ",".join(f"{k}=?" for k in fields)
    with conn() as c:
        c.execute(f"UPDATE cases SET {sets} WHERE case_id=?", (*fields.values(), case_id))


def list_cases(owner_id: int | None = None, include_empty: bool = False) -> list[dict]:
    """
    Кейс, где интервью открыли и бросили на первом вопросе, ничего не значит
    ни для куратора, ни для родителя — по умолчанию такие не показываем.
    """
    q = "SELECT * FROM cases"
    where, args = [], []
    if owner_id is not None:
        where.append("owner_id=?")
        args.append(owner_id)
    if not include_empty:
        where.append(
            "(case_status != 'interview' "
            "OR (SELECT COUNT(*) FROM interview_answers a WHERE a.case_id = cases.case_id) > 0)"
        )
    if where:
        q += " WHERE " + " AND ".join(where)
    q += " ORDER BY created_at DESC"
    with conn() as c:
        return [dict(r) for r in c.execute(q, tuple(args)).fetchall()]


def purge_abandoned(older_than_hours: int = 6) -> int:
    """Удаляет давно брошенные пустые интервью. Вызывается при старте."""
    from datetime import datetime, timedelta
    cutoff = (datetime.now() - timedelta(hours=older_than_hours)).isoformat()
    with conn() as c:
        rows = c.execute(
            "SELECT case_id FROM cases WHERE case_status='interview' AND created_at < ? "
            "AND (SELECT COUNT(*) FROM interview_answers a WHERE a.case_id = cases.case_id) = 0",
            (cutoff,),
        ).fetchall()
        for r in rows:
            c.execute("DELETE FROM events WHERE case_id=?", (r["case_id"],))
            c.execute("DELETE FROM cases WHERE case_id=?", (r["case_id"],))
        return len(rows)


# ──────────────────────────── интервью ────────────────────────────

def add_answer(case_id: str, question_id: str, question: str, answer: str) -> None:
    with conn() as c:
        c.execute("INSERT INTO interview_answers(case_id,question_id,question,answer,created_at) VALUES(?,?,?,?,?)",
                  (case_id, question_id, question, answer, datetime.now().isoformat()))


def get_answers(case_id: str) -> list[dict]:
    with conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT question_id,question,answer FROM interview_answers WHERE case_id=? ORDER BY id", (case_id,))]


def reset_interview(case_id: str) -> None:
    with conn() as c:
        c.execute("DELETE FROM interview_answers WHERE case_id=?", (case_id,))


# ────────────────────────────── план ──────────────────────────────

def save_plan(case_id: str, items: list, base: date | None = None) -> None:
    base = base or date.today()
    with conn() as c:
        c.execute("DELETE FROM plan_items WHERE case_id=?", (case_id,))
        for it in items:
            d = it.model_dump() if hasattr(it, "model_dump") else it
            c.execute(
                "INSERT INTO plan_items(case_id,item_code,service_id,title,description,explanation,priority,"
                "responsible_role,due_date,status,documents_json,depends_on_json,created_by,already_done,updated_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (case_id, d["id"], d["service_id"], d["title"], d.get("description", ""), d.get("explanation", ""),
                 str(d["priority"].value if hasattr(d["priority"], "value") else d["priority"]),
                 str(d["responsible_role"].value if hasattr(d["responsible_role"], "value") else d["responsible_role"]),
                 (base + timedelta(days=int(d["due_in_days"]))).isoformat(),
                 "DONE" if d.get("already_done") else "TODO",
                 json.dumps([{k: (v.value if hasattr(v, "value") else v) for k, v in doc.items()}
                             for doc in d.get("documents", [])], ensure_ascii=False),
                 json.dumps(d.get("depends_on", []), ensure_ascii=False),
                 "ai", int(bool(d.get("already_done"))), datetime.now().isoformat()),
            )


def get_items(case_id: str) -> list[dict]:
    with conn() as c:
        # Порядок шагов: сначала то, что горит, затем логическая
        # последовательность маршрута (item_code проставлен по зависимостям).
        # Сортировать только по приоритету нельзя — тогда ВКК оказывается
        # выше консультации психиатра, без которой её не получить.
        rows = [dict(r) for r in c.execute(
            "SELECT * FROM plan_items WHERE case_id=? ORDER BY "
            "  CASE status WHEN 'OVERDUE' THEN 0 WHEN 'BLOCKED' THEN 1 "
            "              WHEN 'DONE' THEN 3 WHEN 'CANCELLED' THEN 4 ELSE 2 END, "
            "  item_code", (case_id,))]
    for r in rows:
        r["documents"] = json.loads(r.pop("documents_json") or "[]")
        r["depends_on"] = json.loads(r.pop("depends_on_json") or "[]")
        r["blocker"] = json.loads(r.pop("blocker_json") or "null")
        r["confirmed_by_curator"] = bool(r["confirmed_by_curator"])
        r["already_done"] = bool(r["already_done"])
    return rows


def update_item(case_id: str, item_code: str, **fields) -> None:
    if "blocker" in fields:
        fields["blocker_json"] = json.dumps(fields.pop("blocker"), ensure_ascii=False) if fields["blocker"] else None
    if "documents" in fields:
        fields["documents_json"] = json.dumps(fields.pop("documents"), ensure_ascii=False)
    fields["updated_at"] = datetime.now().isoformat()
    sets = ",".join(f"{k}=?" for k in fields)
    with conn() as c:
        c.execute(f"UPDATE plan_items SET {sets} WHERE case_id=? AND item_code=?",
                  (*fields.values(), case_id, item_code))


def confirm_all_items(case_id: str) -> None:
    with conn() as c:
        c.execute("UPDATE plan_items SET confirmed_by_curator=1 WHERE case_id=?", (case_id,))


# ───────────────────────── события и уведомления ─────────────────────

# ──────────────────────────── документы ────────────────────────────

def add_document(case_id: str, doc_type: str, original_name: str, stored_name: str,
                 mime: str, size: int, uploaded_by: str,
                 item_code: str | None = None, note: str = "") -> int:
    with conn() as c:
        cur = c.execute(
            "INSERT INTO documents(case_id,item_code,doc_type,original_name,stored_name,mime,size,"
            "uploaded_by,note,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (case_id, item_code, doc_type, original_name, stored_name, mime, size,
             uploaded_by, note, datetime.now().isoformat()),
        )
        return cur.lastrowid


def get_documents(case_id: str) -> list[dict]:
    with conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM documents WHERE case_id=? ORDER BY id DESC", (case_id,))]


def get_document(doc_id: int) -> dict | None:
    with conn() as c:
        r = c.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
        return dict(r) if r else None


def delete_document(doc_id: int) -> None:
    with conn() as c:
        c.execute("DELETE FROM documents WHERE id=?", (doc_id,))


# ─────────────────── справочник организаций ───────────────────
# Ведётся куратором: ПМПК, МСЭК и центры различаются по районам,
# и держать их в коде нельзя — адреса и телефоны меняются.

FACILITY_FIELDS = ("name", "service_id", "region", "district", "address", "phone",
                   "contact_person", "email", "portal", "hours", "note", "is_active")


def add_facility(data: dict, created_by: str = "") -> int:
    vals = {k: data.get(k, "") for k in FACILITY_FIELDS}
    vals["is_active"] = int(data.get("is_active", 1))
    with conn() as c:
        cur = c.execute(
            f"INSERT INTO facilities({','.join(FACILITY_FIELDS)},created_by,created_at) "
            f"VALUES({','.join('?' * len(FACILITY_FIELDS))},?,?)",
            (*[vals[k] for k in FACILITY_FIELDS], created_by, datetime.now().isoformat()),
        )
        return cur.lastrowid


def list_facilities(region: str | None = None, service_id: str | None = None,
                    only_active: bool = True) -> list[dict]:
    q = "SELECT * FROM facilities"
    where, args = [], []
    if region:
        where.append("region=?")
        args.append(region)
    if service_id:
        where.append("service_id=?")
        args.append(service_id)
    if only_active:
        where.append("is_active=1")
    if where:
        q += " WHERE " + " AND ".join(where)
    q += " ORDER BY region, service_id, district, name"
    with conn() as c:
        rows = [dict(r) for r in c.execute(q, tuple(args))]
    for r in rows:
        r["is_active"] = bool(r["is_active"])
    return rows


def get_facility(fid: int) -> dict | None:
    with conn() as c:
        r = c.execute("SELECT * FROM facilities WHERE id=?", (fid,)).fetchone()
        return dict(r) if r else None


def update_facility(fid: int, data: dict) -> None:
    fields = {k: v for k, v in data.items() if k in FACILITY_FIELDS and v is not None}
    if "is_active" in fields:
        fields["is_active"] = int(bool(fields["is_active"]))
    if not fields:
        return
    fields["updated_at"] = datetime.now().isoformat()
    sets = ",".join(f"{k}=?" for k in fields)
    with conn() as c:
        c.execute(f"UPDATE facilities SET {sets} WHERE id=?", (*fields.values(), fid))


def delete_facility(fid: int) -> None:
    with conn() as c:
        c.execute("DELETE FROM facilities WHERE id=?", (fid,))


# ───────────────── история психологического состояния ─────────────────

def add_phq9(case_id: str, score: int, severity: str, crisis: bool) -> None:
    with conn() as c:
        c.execute("INSERT INTO phq9_history(case_id,score,severity,crisis_flag,created_at) VALUES(?,?,?,?,?)",
                  (case_id, score, severity, int(crisis), datetime.now().isoformat()))


def get_phq9_history(case_id: str) -> list[dict]:
    with conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT score,severity,crisis_flag,created_at FROM phq9_history "
            "WHERE case_id=? ORDER BY id", (case_id,))]


def add_event(case_id: str, kind: str, actor: str, message: str, item_code: str | None = None) -> None:
    with conn() as c:
        c.execute("INSERT INTO events(case_id,item_code,kind,actor,message,created_at) VALUES(?,?,?,?,?,?)",
                  (case_id, item_code, kind, actor, message, datetime.now().isoformat()))


def get_events(case_id: str | None = None, limit: int = 100) -> list[dict]:
    q = "SELECT * FROM events"
    args: tuple = ()
    if case_id:
        q += " WHERE case_id=?"
        args = (case_id,)
    q += " ORDER BY id DESC LIMIT ?"
    with conn() as c:
        return [dict(r) for r in c.execute(q, (*args, limit))]


def mark_events_read(case_id: str, role: str) -> None:
    col = "read_by_parent" if role == "parent" else "read_by_curator"
    with conn() as c:
        c.execute(f"UPDATE events SET {col}=1 WHERE case_id=?", (case_id,))
