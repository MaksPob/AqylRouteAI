"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { api, type CaseDetail, type Item, type Status, token } from "@/lib/api";
import { BLOCKER_NAMES, formatDate, localName, REGION_NAMES, ROLE_NAMES, STAGE_NAMES, t } from "@/lib/i18n";
import { Banner, Header, Icon, PriorityMark, Spinner, StatusBadge, useLang } from "@/components/ui";

const STATUSES: Status[] = ["TODO", "IN_PROGRESS", "WAITING", "DONE", "BLOCKED"];
const BLOCKERS = ["MISSING_DOCUMENT", "WAITING_FOR_ORGANIZATION", "NO_APPOINTMENT", "PARENT_UNAVAILABLE", "SERVICE_UNAVAILABLE", "UNKNOWN"];

function CuratorItem({ item, lang, caseId, onChange, confirmed }: {
  item: Item; lang: "ru" | "kk" | "en"; caseId: string;
  onChange: (d: CaseDetail) => void; confirmed: boolean;
}) {
  const [edit, setEdit] = useState(false);
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState({
    title: item.title, priority: item.priority,
    responsible_role: item.responsible_role, due_date: item.due_date,
  });
  const [blockerOpen, setBlockerOpen] = useState(false);
  const [blocker, setBlocker] = useState({ type: "WAITING_FOR_ORGANIZATION", description: "" });

  const run = async (fn: () => Promise<CaseDetail>) => {
    setBusy(true);
    try { onChange(await fn()); setEdit(false); setBlockerOpen(false); }
    finally { setBusy(false); }
  };

  const unverified = item.parent_reported_status && !item.confirmed_by_curator;

  return (
    <article className="card p-4 sm:p-5" style={
      item.status === "OVERDUE" ? { borderColor: "var(--st-overdue)" }
      : item.status === "BLOCKED" ? { borderColor: "var(--st-blocked)" }
      : unverified ? { borderColor: "var(--st-waiting)" } : undefined}>

      <div className="mb-2.5 flex flex-wrap items-center gap-2">
        <span className="rounded px-1.5 py-0.5 font-mono text-[0.72rem]"
              style={{ background: "var(--surface-2)", color: "var(--ink-muted)" }}>{item.item_code}</span>
        <StatusBadge status={item.status} lang={lang} size="sm" />
        <PriorityMark priority={item.priority} lang={lang} />
        {item.days_overdue > 0 && (
          <span className="text-[0.8rem] font-semibold" style={{ color: "var(--st-overdue)" }}>
            +{item.days_overdue} {t("days", lang)}
          </span>
        )}
        {item.escalation_level !== "NONE" && item.escalation_action && (
          <span className="rounded-full px-2 py-0.5 text-[0.74rem] font-semibold"
                style={{ background: "var(--st-overdue-bg)", color: "var(--st-overdue)" }}>
            {item.escalation_action}
          </span>
        )}
      </div>

      {edit ? (
        <div className="grid gap-3">
          <input className="field" value={draft.title} onChange={(e) => setDraft({ ...draft, title: e.target.value })} />
          <div className="grid gap-3 sm:grid-cols-3">
            <label className="grid gap-1 text-[0.8rem] font-medium">Приоритет
              <select className="field" value={draft.priority}
                      onChange={(e) => setDraft({ ...draft, priority: e.target.value as Item["priority"] })}>
                <option value="HIGH">Высокий</option><option value="MEDIUM">Средний</option><option value="LOW">Низкий</option>
              </select>
            </label>
            <label className="grid gap-1 text-[0.8rem] font-medium">Ответственный
              <select className="field" value={draft.responsible_role}
                      onChange={(e) => setDraft({ ...draft, responsible_role: e.target.value })}>
                {Object.keys(ROLE_NAMES).map((r) => (
                  <option key={r} value={r}>{localName(ROLE_NAMES, r, lang)}</option>
                ))}
              </select>
            </label>
            <label className="grid gap-1 text-[0.8rem] font-medium">Срок
              <input className="field" type="date" value={draft.due_date}
                     onChange={(e) => setDraft({ ...draft, due_date: e.target.value })} />
            </label>
          </div>
          <div className="flex gap-2">
            <button className="btn btn-primary !py-2 !text-[0.87rem]" disabled={busy}
                    onClick={() => run(() => api.patchItem(caseId, item.item_code, draft))}>
              {t("save", lang)}
            </button>
            <button className="btn btn-quiet !text-[0.87rem]" onClick={() => setEdit(false)}>{t("cancel", lang)}</button>
          </div>
        </div>
      ) : (
        <>
          <h3 className="mb-1.5">{item.title}</h3>
          <div className="mb-3 flex flex-wrap gap-x-5 gap-y-1 text-[0.84rem]" style={{ color: "var(--ink-muted)" }}>
            <span>{t("due", lang)}: {formatDate(item.due_date, lang)}</span>
            <span>{localName(ROLE_NAMES, item.responsible_role, lang)}</span>
            {item.stage && <span>{localName(STAGE_NAMES, item.stage, lang)}</span>}
            {item.authority && <span>{item.authority}</span>}
          </div>

          {item.blocker && (
            <div className="mb-3">
              <Banner tone="warn">
                <strong>{localName(BLOCKER_NAMES, item.blocker.type, lang)}.</strong> {item.blocker.description}
              </Banner>
            </div>
          )}

          {unverified && (
            <div className="mb-3 flex flex-wrap items-center gap-2 rounded-[var(--radius-s)] px-3 py-2 text-[0.85rem]"
                 style={{ background: "var(--st-waiting-bg)", color: "var(--st-waiting)" }}>
              <Icon.user size={15} />
              <span>{t("parentReported", lang)}: {t(`st${item.parent_reported_status}` as never, lang)}</span>
              <button className="btn btn-quiet !py-1 !text-[0.82rem] !text-current underline" disabled={busy}
                      onClick={() => run(() => api.verify(caseId, item.item_code))}>
                {t("verifyStatus", lang)}
              </button>
            </div>
          )}

          <div className="flex flex-wrap items-center gap-2 border-t pt-3" style={{ borderColor: "var(--border)" }}>
            <select className="field !w-full !py-1.5 !text-[0.86rem] sm:!w-auto" value={item.status} disabled={busy}
                    onChange={(e) => run(() => api.setStatus(caseId, item.item_code, e.target.value as Status))}
                    aria-label="Статус шага">
              {STATUSES.map((s) => <option key={s} value={s}>{t(`st${s}` as never, lang)}</option>)}
            </select>
            <button className="btn btn-quiet !text-[0.84rem]" onClick={() => setEdit(true)}>
              <Icon.edit size={15} /> {t("editStep", lang)}
            </button>
            <button className="btn btn-quiet !text-[0.84rem]" onClick={() => setBlockerOpen((o) => !o)}>
              <Icon.blocked size={15} /> {t("setBlocker", lang)}
            </button>
            {!confirmed && (
              <button className="btn btn-quiet !text-[0.84rem]" style={{ color: "var(--st-overdue)" }} disabled={busy}
                      onClick={() => run(() => api.removeItem(caseId, item.item_code))}>
                {t("removeStep", lang)}
              </button>
            )}
          </div>

          {blockerOpen && (
            <div className="mt-3 grid gap-2 rounded-[var(--radius-s)] p-3" style={{ background: "var(--surface-2)" }}>
              <select className="field !py-2 !text-[0.87rem]" value={blocker.type}
                      onChange={(e) => setBlocker({ ...blocker, type: e.target.value })}>
                {BLOCKERS.map((b) => <option key={b} value={b}>{localName(BLOCKER_NAMES, b, lang)}</option>)}
              </select>
              <input className="field !py-2 !text-[0.87rem]" placeholder="Что именно произошло"
                     value={blocker.description} onChange={(e) => setBlocker({ ...blocker, description: e.target.value })} />
              <button className="btn btn-primary !py-2 !text-[0.87rem]" disabled={busy}
                      onClick={() => run(() => api.patchItem(caseId, item.item_code,
                        { blocker_type: blocker.type, blocker_description: blocker.description }))}>
                {t("save", lang)}
              </button>
            </div>
          )}
        </>
      )}
    </article>
  );
}

function CaseInner() {
  const [lang, setLang] = useLang();
  const router = useRouter();
  const caseId = useSearchParams().get("id");
  const [d, setD] = useState<CaseDetail | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const load = useCallback(async () => {
    if (!caseId) return;
    try { setD(await api.case(caseId)); } catch (e) { setErr(e instanceof Error ? e.message : "Ошибка"); }
  }, [caseId]);

  useEffect(() => {
    if (!token.get()) { router.replace("/"); return; }
    load();
  }, [load, router]);

  if (!caseId) return <main className="p-6">Кейс не указан</main>;
  if (!d) return <Spinner label={t("loading", lang)} />;

  const items = d.items.filter((i) => i.status !== "CANCELLED");
  const pending = d.case_status === "pending_review";

  const confirm = async () => {
    setBusy(true);
    try { setD(await api.confirm(caseId)); } finally { setBusy(false); }
  };

  return (
    <main className="min-h-screen pb-16">
      <Header lang={lang} setLang={setLang}
              title={`${d.child_name || "Кейс"} · ${d.case_id}`}
              subtitle={`${d.child_age} лет · ${localName(REGION_NAMES, d.region, lang)} · ${
                pending ? t("pendingReview", lang) : t("activeCase", lang)}`}
              back={() => router.push("/curator")} />

      <div className="mx-auto max-w-5xl px-4 pt-5 sm:px-6 sm:pt-7">
        {pending && (
          <section className="card mb-6 flex flex-wrap items-center justify-between gap-4 p-5 max-sm:sticky max-sm:top-[60px] max-sm:z-20"
                   style={{ borderColor: "var(--brand)" }}>
            <div className="min-w-0">
              <h3 className="mb-1">План готов к проверке</h3>
              <p className="text-[0.88rem]" style={{ color: "var(--ink-2)" }}>
                Проверьте маршрут, услуги, сроки и документы. {t("confirmHint", lang)}
              </p>
            </div>
            <button className="btn btn-primary w-full shrink-0 sm:w-auto" onClick={confirm} disabled={busy}>
              <Icon.check size={17} /> {t("confirmPlan", lang)}
            </button>
          </section>
        )}

        <div className="grid gap-6 lg:grid-cols-[1.6fr_1fr]">
          <section>
            {d.summary && (
              <div className="card mb-4 p-5">
                <p className="text-[0.95rem]">{d.summary}</p>
                {d.engine && (
                  <p className="mt-3 text-[0.76rem]" style={{ color: "var(--ink-muted)" }}>
                    Сформировано: {d.engine.includes("demo") ? "демонстрационный планировщик" : "OpenAI structured outputs"}
                  </p>
                )}
              </div>
            )}

            <div className="grid gap-3">
              {items.map((i) => (
                <CuratorItem key={i.item_code} item={i} lang={lang} caseId={caseId}
                             onChange={setD} confirmed={!pending} />
              ))}
            </div>
          </section>

          <aside className="grid content-start gap-5">
            {d.phq9_score !== null && (
              <section className="card p-5">
                <h3 className="mb-2 inline-flex items-center gap-2"><Icon.heart size={17} /> Состояние родителя</h3>
                <div className="flex items-baseline gap-2">
                  <span className="text-[1.6rem] font-bold leading-none"
                        style={{ color: d.phq9_score >= 15 ? "var(--st-overdue)" : d.phq9_score >= 10 ? "var(--st-blocked)" : "var(--st-done)" }}>
                    {d.phq9_score}
                  </span>
                  <span className="text-[0.85rem]" style={{ color: "var(--ink-muted)" }}>из 27 · PHQ-9</span>
                </div>
                <p className="mt-2 text-[0.8rem]" style={{ color: "var(--ink-muted)" }}>
                  Скрининг, не диагноз. Интерпретирует специалист.
                </p>
              </section>
            )}

            {d.state && (
              <section className="card p-5">
                <h3 className="mb-3">Состояние кейса</h3>
                <dl className="grid gap-1.5 text-[0.85rem]">
                  {([
                    ["Этап", localName(STAGE_NAMES, String(d.state.current_stage ?? ""), lang)],
                    ["Диагноз подтверждён", d.state.has_diagnosis ? "да" : "нет"],
                    ["Инвалидность", d.state.has_disability ? "оформлена" : "нет"],
                    ["ИПАР", d.state.has_ipar ? "есть" : "нет"],
                    ["Заключение ПМПК", d.state.has_pmpc_conclusion ? "есть" : "нет"],
                  ] as [string, string][]).map(([k, v]) => (
                    <div key={k} className="flex justify-between gap-3">
                      <dt style={{ color: "var(--ink-muted)" }}>{k}</dt>
                      <dd className="text-right font-medium">{v}</dd>
                    </div>
                  ))}
                </dl>
                {Array.isArray(d.state.open_problems) && (d.state.open_problems as string[]).length > 0 && (
                  <p className="mt-3 border-t pt-3 text-[0.82rem]" style={{ borderColor: "var(--border)", color: "var(--ink-2)" }}>
                    Проблемы со слов родителя: {(d.state.open_problems as string[]).join(", ")}
                  </p>
                )}
              </section>
            )}

            <section className="card p-5">
              <h3 className="mb-3">{t("history", lang)}</h3>
              <ul className="grid gap-2.5 text-[0.83rem]">
                {d.events.slice(0, 12).map((e) => (
                  <li key={e.id} className="border-l-2 pl-3" style={{ borderColor: "var(--border-strong)" }}>
                    <div style={{ color: "var(--ink-2)" }}>{e.message}</div>
                    <div className="text-[0.76rem]" style={{ color: "var(--ink-muted)" }}>
                      {e.actor} · {new Date(e.created_at).toLocaleString(lang === "en" ? "en-GB" : "ru-RU",
                        { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}
                    </div>
                  </li>
                ))}
              </ul>
            </section>
          </aside>
        </div>

        {err && <div className="mt-4"><Banner tone="warn">{err}</Banner></div>}
      </div>
    </main>
  );
}

export default function CuratorCasePage() {
  return <Suspense fallback={<Spinner label="…" />}><CaseInner /></Suspense>;
}
