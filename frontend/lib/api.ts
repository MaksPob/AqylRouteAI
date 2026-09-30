/** Клиент API. Токен живёт в localStorage — для прототипа достаточно. */

export const API = process.env.NEXT_PUBLIC_API ?? "http://127.0.0.1:8000";

export type Role = "parent" | "curator";
export type Status = "TODO" | "IN_PROGRESS" | "WAITING" | "DONE" | "OVERDUE" | "BLOCKED" | "CANCELLED";

export interface User { id: number; login: string; role: Role; display_name: string; region: string }

export interface AnswerOption { value: string; label: string }

export interface Question {
  question_id: string;
  text: string;
  why: string;
  input_type: "single_choice" | "multi_choice" | "text" | "number" | "date";
  options: AnswerOption[];
  allow_dont_know: boolean;
  clarification: string;
}

export interface Step {
  is_complete: boolean;
  progress_current: number;
  progress_total: number;
  next_question: Question | null;
  acknowledgement: string;
}

export interface PlanDoc { name: string; status: "available" | "missing" | "in_progress" | "unknown" }
export interface Blocker { type: string; description: string }

export interface Item {
  item_code: string;
  service_id: string;
  title: string;
  description: string;
  explanation: string;
  priority: "HIGH" | "MEDIUM" | "LOW";
  responsible_role: string;
  due_date: string;
  status: Status;
  documents: PlanDoc[];
  depends_on: string[];
  blocker: Blocker | null;
  confirmed_by_curator: boolean;
  parent_reported_status: Status | null;
  days_overdue: number;
  escalation_level: string;
  escalation_action: string;
  stage: string;
  authority: string;
  portal?: string;
  facilities: { name: string; portal?: string; note?: string }[];
}

export interface Stats {
  overdue: number; active: number; done: number; blocked: number;
  by_blocker: Record<string, number>;
  max_escalation: string; max_days_overdue: number;
}

export interface CaseSummary {
  case_id: string; region: string; child_age: number; child_name: string;
  case_status: string; created_at: string; stats: Stats;
  reviewed: boolean;
  phq9_score: number | null; phq9_severity: string;
}

export interface CaseDetail extends CaseSummary {
  summary: string; parent_support_note: string; engine: string;
  items: Item[]; events: EventRow[]; state: Record<string, unknown> | null;
  documents: DocRow[]; phq9_history: PhqPoint[];
  needs_clarification: { service_id: string; title: string; reason: string }[];
  pending_notice?: string;
}

export interface EventRow {
  id: number; case_id: string; item_code: string | null;
  kind: string; actor: string; message: string; created_at: string;
}

export interface DocRow {
  id: number; case_id: string; item_code: string | null; doc_type: string;
  original_name: string; mime: string; size: number; uploaded_by: string;
  note: string; created_at: string;
}

export interface PhqPoint { score: number; severity: string; crisis_flag: number; created_at: string }

export interface Notification {
  case_id: string; item_code: string | null; title: string;
  days_overdue: number; level: string; action: string; responsible_role: string;
}

const TOKEN_KEY = "aqyl_token";

export const token = {
  get: () => (typeof window === "undefined" ? null : localStorage.getItem(TOKEN_KEY)),
  set: (t: string) => localStorage.setItem(TOKEN_KEY, t),
  clear: () => localStorage.removeItem(TOKEN_KEY),
};

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  const t = token.get();
  const res = await fetch(`${API}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(t ? { Authorization: `Bearer ${t}` } : {}),
      ...(init.headers ?? {}),
    },
  });
  if (!res.ok) {
    let detail = `Ошибка ${res.status}`;
    try { detail = (await res.json()).detail ?? detail; } catch { /* тело не JSON */ }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export const api = {
  login: (login: string, password: string) =>
    call<{ token: string; user: User }>("/api/auth/login", { method: "POST", body: JSON.stringify({ login, password }) }),
  register: (body: { login: string; password: string; display_name: string; region: string; role: string; invite_code?: string }) =>
    call<{ token: string; user: User }>("/api/auth/register", { method: "POST", body: JSON.stringify(body) }),
  me: () => call<User>("/api/auth/me"),
  logout: () => call<{ ok: boolean }>("/api/auth/logout", { method: "POST" }),

  health: () => call<{ ok: boolean; ai_engine: string; model: string; services: number }>("/api/health"),

  startCase: (child_name: string, lang: string) =>
    call<{ case_id: string; step: Step; engine: string }>("/api/cases/start", { method: "POST", body: JSON.stringify({ child_name, lang }) }),

  answer: (p: { case_id: string; question_id: string; question: string; answer: string; lang: string }) =>
    call<{ step: Step; engine: string; answered: number }>("/api/interview/answer", { method: "POST", body: JSON.stringify(p) }),

  buildPlan: (case_id: string, lang: string) =>
    call<{ case_id: string; engine: string; rejected: string[] }>(`/api/interview/build-plan?case_id=${case_id}&lang=${lang}`, { method: "POST" }),

  cases: () => call<CaseSummary[]>("/api/cases"),
  case: (id: string) => call<CaseDetail>(`/api/cases/${id}`),

  patchItem: (caseId: string, code: string, body: Record<string, unknown>) =>
    call<CaseDetail>(`/api/cases/${caseId}/items/${code}`, { method: "PATCH", body: JSON.stringify(body) }),
  setStatus: (caseId: string, code: string, status: Status, comment = "") =>
    call<CaseDetail>(`/api/cases/${caseId}/items/${code}/status`, { method: "POST", body: JSON.stringify({ status, comment }) }),
  verify: (caseId: string, code: string) =>
    call<CaseDetail>(`/api/cases/${caseId}/items/${code}/verify`, { method: "POST" }),
  removeItem: (caseId: string, code: string) =>
    call<CaseDetail>(`/api/cases/${caseId}/items/${code}/delete`, { method: "POST" }),
  confirm: (caseId: string) => call<CaseDetail>(`/api/cases/${caseId}/confirm`, { method: "POST" }),

  notifications: () => call<Notification[]>("/api/notifications"),

  docTypes: () => call<{ value: string; label: string }[]>("/api/document-types"),
  documents: (caseId: string) => call<DocRow[]>(`/api/cases/${caseId}/documents`),
  deleteDocument: (id: number) => call<{ ok: boolean }>(`/api/documents/${id}/delete`, { method: "POST" }),
  fileUrl: (id: number) => `${API}/api/documents/${id}/file`,

  uploadDocument: async (caseId: string, file: File, docType: string, itemCode = "", note = "") => {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("doc_type", docType);
    if (itemCode) fd.append("item_code", itemCode);
    if (note) fd.append("note", note);
    const t = token.get();
    const res = await fetch(`${API}/api/cases/${caseId}/documents`, {
      method: "POST",
      headers: t ? { Authorization: `Bearer ${t}` } : {},   // Content-Type ставит сам браузер вместе с boundary
      body: fd,
    });
    if (!res.ok) {
      let detail = `Ошибка ${res.status}`;
      try { detail = (await res.json()).detail ?? detail; } catch { /* не JSON */ }
      throw new Error(detail);
    }
    return res.json() as Promise<DocRow>;
  },

  phq9form: (lang: string) =>
    call<{ preamble: string; questions: { id: number; text: string; critical: boolean }[]; options: { value: number; label: string }[]; disclaimer: string }>(`/api/phq9?lang=${lang}`),
  phq9submit: (case_id: string, answers: number[]) =>
    call<{ score: number; max_score: number; severity: string; note: string; needs_support: boolean; crisis_flag: boolean; crisis_message: string; disclaimer: string }>("/api/phq9", { method: "POST", body: JSON.stringify({ case_id, answers }) }),
};
