"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { api, type CaseDetail, type CaseSummary, type Item, type Status, token } from "@/lib/api";
import { BLOCKER_NAMES, formatDate, localName, REGION_NAMES, ROLE_NAMES, STAGE_NAMES, t } from "@/lib/i18n";
import { Banner, Header, Icon, PriorityMark, Spinner, StatusBadge, useLang } from "@/components/ui";
import { PhqCard } from "@/components/phq";
import { Documents } from "@/components/documents";
import { WellbeingTrack } from "@/components/wellbeing";

/* ─────────────────────── карточка шага ─────────────────────── */

function StepCard({ item, lang, onStatus, busy }: {
  item: Item; lang: "ru" | "kk" | "en";
  onStatus: (code: string, s: Status) => void; busy: boolean;
}) {
  const [open, setOpen] = useState(false);
  const urgent = item.status === "OVERDUE" || item.status === "BLOCKED";

  return (
    <article className="card overflow-hidden transition-shadow hover:shadow-[var(--shadow-l)]"
             style={urgent ? { borderColor: item.status === "OVERDUE" ? "var(--st-overdue)" : "var(--st-blocked)" } : undefined}>
      {/* полоска статуса слева читается раньше текста */}
      <div className="flex">
        <div className="w-1 shrink-0" style={{
          background: item.status === "DONE" ? "var(--st-done)"
            : item.status === "OVERDUE" ? "var(--st-overdue)"
            : item.status === "BLOCKED" ? "var(--st-blocked)"
            : item.priority === "HIGH" ? "var(--st-todo)" : "var(--border-strong)" }} />

        <div className="min-w-0 flex-1 p-4 sm:p-5">
          <div className="mb-2.5 flex flex-wrap items-center gap-2">
            <StatusBadge status={item.status} lang={lang} size="sm" />
            <PriorityMark priority={item.priority} lang={lang} />
            {item.days_overdue > 0 && (
              <span className="text-[0.8rem] font-semibold" style={{ color: "var(--st-overdue)" }}>
                {t("overdueBy", lang)} {item.days_overdue} {t("days", lang)}
              </span>
            )}
            {item.parent_reported_status && !item.confirmed_by_curator && (
              <span className="text-[0.76rem]" style={{ color: "var(--ink-muted)" }}>· {t("parentReported", lang)}</span>
            )}
          </div>

          <h3 className="mb-1.5 text-balance">{item.title}</h3>
          <p className="mb-3 text-[0.92rem]" style={{ color: "var(--ink-2)" }}>{item.description}</p>

          <div className="mb-3 flex flex-wrap gap-x-5 gap-y-1.5 text-[0.85rem]" style={{ color: "var(--ink-muted)" }}>
            <span className="inline-flex items-center gap-1.5">
              <Icon.clock size={14} /> {t("due", lang)}: {formatDate(item.due_date, lang)}
            </span>
            <span className="inline-flex items-center gap-1.5">
              <Icon.user size={14} /> {t("who", lang)}: {localName(ROLE_NAMES, item.responsible_role, lang)}
            </span>
            {item.stage && (
              <span className="inline-flex items-center gap-1.5">
                <Icon.doc size={14} /> {localName(STAGE_NAMES, item.stage, lang)}
              </span>
            )}
          </div>

          {item.blocker && (
            <div className="mb-3">
              <Banner tone="warn">
                <strong>{localName(BLOCKER_NAMES, item.blocker.type, lang)}.</strong>{" "}
                {item.blocker.description}
              </Banner>
            </div>
          )}

          <button onClick={() => setOpen((o) => !o)}
                  className="mb-1 inline-flex items-center gap-1.5 text-[0.87rem] font-medium"
                  style={{ color: "var(--brand)" }} aria-expanded={open}>
            {open ? "Свернуть" : t("whyStep", lang)}
            <span className="transition-transform" style={{ transform: open ? "rotate(90deg)" : "none" }}>
              <Icon.arrow size={15} />
            </span>
          </button>

          {open && (
            <div className="mt-3 grid gap-4 border-t pt-4 text-[0.9rem]" style={{ borderColor: "var(--border)" }}>
              <p style={{ color: "var(--ink-2)" }}>{item.explanation}</p>

              {item.documents.length > 0 && (
                <div>
                  <div className="mb-2 text-[0.82rem] font-semibold" style={{ color: "var(--ink-muted)" }}>
                    {t("needDocs", lang)}
                  </div>
                  <ul className="grid gap-1.5">
                    {item.documents.map((d) => (
                      <li key={d.name} className="flex items-start gap-2">
                        <span className="mt-[3px] shrink-0"
                              style={{ color: d.status === "available" ? "var(--st-done)" : "var(--ink-muted)" }}>
                          {d.status === "available" ? <Icon.check size={14} /> : <Icon.minus size={14} />}
                        </span>
                        <span>
                          {d.name}
                          <span className="ml-1.5 text-[0.8rem]" style={{ color: "var(--ink-muted)" }}>
                            — {d.status === "available" ? t("haveDoc", lang) : t("needDoc", lang)}
                          </span>
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {item.facilities?.length > 0 && (
                <div>
                  <div className="mb-2 text-[0.82rem] font-semibold" style={{ color: "var(--ink-muted)" }}>
                    {t("whereToGo", lang)}
                  </div>
                  <ul className="grid gap-1.5">
                    {item.facilities.map((f) => (
                      <li key={f.name} className="flex items-start gap-2">
                        <span className="mt-[3px] shrink-0" style={{ color: "var(--brand)" }}><Icon.pin size={14} /></span>
                        <span>
                          {f.name}
                          {f.portal && <span className="ml-1.5" style={{ color: "var(--brand)" }}>{f.portal}</span>}
                          {f.note && <span className="ml-1.5 text-[0.8rem]" style={{ color: "var(--ink-muted)" }}>— {f.note}</span>}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {item.depends_on.length > 0 && (
                <p className="text-[0.84rem]" style={{ color: "var(--ink-muted)" }}>
                  {t("dependsOn", lang)}: {item.depends_on.join(", ")}
                </p>
              )}
            </div>
          )}

          {/* родитель ведёт статус сам, куратор потом подтверждает */}
          {item.status !== "DONE" && item.status !== "CANCELLED" && (
            <div className="mt-4 grid gap-2 border-t pt-4 sm:flex sm:flex-wrap" style={{ borderColor: "var(--border)" }}>
              <button className="btn btn-ghost !text-[0.88rem]" disabled={busy}
                      onClick={() => onStatus(item.item_code, "DONE")}>
                <Icon.check size={15} /> {t("markDone", lang)}
              </button>
              {item.status !== "IN_PROGRESS" && (
                <button className="btn btn-quiet !text-[0.88rem]" disabled={busy}
                        onClick={() => onStatus(item.item_code, "IN_PROGRESS")}>
                  {t("markProgress", lang)}
                </button>
              )}
              {item.status !== "WAITING" && (
                <button className="btn btn-quiet !text-[0.88rem]" disabled={busy}
                        onClick={() => onStatus(item.item_code, "WAITING")}>
                  {t("markWaiting", lang)}
                </button>
              )}
            </div>
          )}
        </div>
      </div>
    </article>
  );
}

/* ─────────────────────── страница ─────────────────────── */

function PlanInner() {
  const [lang, setLang] = useLang();
  const router = useRouter();
  const caseId = useSearchParams().get("case");

  const [list, setList] = useState<CaseSummary[] | null>(null);
  const [detail, setDetail] = useState<CaseDetail | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [showAll, setShowAll] = useState(false);

  const load = useCallback(async () => {
    try {
      if (caseId) setDetail(await api.case(caseId));
      else setList(await api.cases());
    } catch (e) { setErr(e instanceof Error ? e.message : "Ошибка загрузки"); }
  }, [caseId]);

  useEffect(() => {
    if (!token.get()) { router.replace("/"); return; }
    load();
  }, [load, router]);

  const setStatus = async (code: string, s: Status) => {
    if (!caseId) return;
    setBusy(true);
    try { setDetail(await api.setStatus(caseId, code, s)); }
    catch (e) { setErr(e instanceof Error ? e.message : "Не удалось обновить статус"); }
    finally { setBusy(false); }
  };

  // ── список обращений родителя ──
  if (!caseId) {
    if (!list) return <Spinner label={t("loading", lang)} />;
    return (
      <main className="min-h-screen pb-16">
        <Header lang={lang} setLang={setLang} title={t("myCases", lang)} />
        <div className="mx-auto max-w-3xl px-4 pt-5 sm:px-6 sm:pt-7">
          <button className="btn btn-primary mb-6 w-full sm:w-auto" onClick={() => router.push("/interview")}>
            <Icon.play size={17} /> {t("newCase", lang)}
          </button>

          {list.length === 0 ? (
            <div className="card p-10 text-center" style={{ color: "var(--ink-muted)" }}>
              <p className="mb-1 font-medium">{t("nothingYet", lang)}</p>
              <p className="text-[0.88rem]">Начните с интервью — это 8–12 коротких вопросов.</p>
            </div>
          ) : (
            <ul className="grid gap-3">
              {list.map((c) => (
                <li key={c.case_id}>
                  <button onClick={() => router.push(`/plan?case=${c.case_id}`)}
                          className="card flex w-full items-center gap-4 p-5 text-left transition-shadow hover:shadow-[var(--shadow-l)]">
                    <div className="min-w-0 flex-1">
                      <div className="mb-1 flex flex-wrap items-center gap-2">
                        <span className="font-semibold">{c.child_name || c.case_id}</span>
                        <span className="text-[0.82rem]" style={{ color: "var(--ink-muted)" }}>
                          {c.child_age > 0 && `${c.child_age} лет · `}{localName(REGION_NAMES, c.region, lang)}
                        </span>
                      </div>
                      <div className="text-[0.85rem]" style={{ color: "var(--ink-muted)" }}>
                        {c.case_status === "interview" ? t("interviewing", lang)
                          : `${c.stats.done + c.stats.active + c.stats.overdue + c.stats.blocked} ${t("stepsTotal", lang)}`}
                      </div>
                    </div>
                    {c.stats.overdue > 0 && (
                      <span className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[0.8rem] font-semibold"
                            style={{ background: "var(--st-overdue-bg)", color: "var(--st-overdue)" }}>
                        <Icon.alert size={14} /> {c.stats.overdue}
                      </span>
                    )}
                    <Icon.arrow size={18} className="shrink-0 opacity-30" />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </main>
    );
  }

  // ── конкретный план ──
  if (!detail) return <Spinner label={t("loading", lang)} />;

  const visible = detail.items.filter((i) => i.status !== "CANCELLED");
  const todo = visible.filter((i) => i.status !== "DONE");
  const done = visible.filter((i) => i.status === "DONE");
  const urgentCount = visible.filter((i) => i.status === "OVERDUE" || i.status === "BLOCKED").length;

  // ТЗ: «Сейчас нужно сделать 3 вещи». Родителю в стрессе список из десяти
  // пунктов читается как «всё сразу и невозможно», поэтому показываем
  // первые три (они уже отсортированы по приоритету и сроку), остальное — по запросу.
  // Куратор мог ещё не дойти до кейса: план работает, но честно помечен как предварительный
  const reviewed = visible.length > 0 && visible.every((i) => i.confirmed_by_curator);

  const FOCUS = 3;
  const focus = showAll ? todo : todo.slice(0, FOCUS);
  const rest = todo.length - focus.length;

  return (
    <main className="min-h-screen pb-20">
      <Header lang={lang} setLang={setLang}
              title={detail.child_name ? `${t("myPlan", lang)} — ${detail.child_name}` : t("myPlan", lang)}
              subtitle={`${localName(REGION_NAMES, detail.region, lang)} · ${detail.case_id}`}
              back={() => router.push("/plan")} />

      <div className="mx-auto max-w-3xl px-4 pt-5 sm:px-6 sm:pt-7">
        {(
          <>
            {detail.summary && (
              <section className="card mb-6 p-5 sm:p-6">
                <p className="text-[1.01rem] leading-relaxed sm:text-[1.03rem]">{detail.summary}</p>
                <p className="mt-4 inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-[0.84rem] font-medium"
                   style={reviewed
                     ? { background: "var(--st-done-bg)", color: "var(--st-done)" }
                     : { background: "var(--surface-2)", color: "var(--ink-2)" }}>
                  {reviewed ? <Icon.shield size={15} /> : <Icon.clock size={15} />}
                  {reviewed
                    ? "План проверен куратором"
                    : "План предварительный — куратор скоро его просмотрит"}
                </p>
                {urgentCount > 0 && (
                  <p className="mt-4 inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-[0.86rem] font-semibold"
                     style={{ background: "var(--st-overdue-bg)", color: "var(--st-overdue)" }}>
                    <Icon.alert size={15} />
                    Требует внимания: {urgentCount}
                  </p>
                )}
              </section>
            )}

            {detail.parent_support_note && (
              <section className="card mb-6 p-5 sm:p-6" style={{ borderColor: "var(--brand)" }}>
                <h3 className="mb-2 inline-flex items-center gap-2" style={{ color: "var(--brand-ink)" }}>
                  <Icon.heart size={18} /> {t("supportTitle", lang)}
                </h3>
                <p className="mb-4 text-[0.95rem]" style={{ color: "var(--ink-2)" }}>{detail.parent_support_note}</p>
                {detail.phq9_history?.length > 0 && (
                  <div className="mb-4 rounded-[var(--radius-s)] p-4" style={{ background: "var(--surface-2)" }}>
                    <h4 className="mb-2 text-[0.88rem] font-semibold">Как меняется ваше состояние</h4>
                    <WellbeingTrack history={detail.phq9_history} />
                  </div>
                )}
                <PhqCard caseId={detail.case_id} lang={lang} initialScore={detail.phq9_score} />
              </section>
            )}

            {todo.length > 0 && (
              <>
                <h2 className="mb-1 mt-2">
                  {todo.length <= FOCUS || showAll
                    ? "Сейчас нужно сделать"
                    : `Сейчас нужно сделать ${FOCUS} вещи`}
                </h2>
                {!showAll && rest > 0 && (
                  <p className="mb-3 text-[0.88rem]" style={{ color: "var(--ink-muted)" }}>
                    Остальное подождёт — эти шаги идут первыми по срокам и важности.
                  </p>
                )}
                <div className="mb-4 grid gap-3">
                  {focus.map((i) => (
                    <StepCard key={i.item_code} item={i} lang={lang} onStatus={setStatus} busy={busy} />
                  ))}
                </div>
                {rest > 0 && (
                  <button className="btn btn-ghost mb-8 w-full" onClick={() => setShowAll(true)}>
                    Показать остальные шаги — {rest}
                  </button>
                )}
                {showAll && todo.length > FOCUS && (
                  <button className="btn btn-quiet mb-8 w-full" onClick={() => setShowAll(false)}>
                    Свернуть до главного
                  </button>
                )}
              </>
            )}

            {done.length > 0 && (
              <details className="mb-6">
                <summary className="mb-3 cursor-pointer font-semibold" style={{ color: "var(--ink-2)" }}>
                  {t("stDONE", lang)} — {done.length}
                </summary>
                <div className="grid gap-3">
                  {done.map((i) => (
                    <StepCard key={i.item_code} item={i} lang={lang} onStatus={setStatus} busy={busy} />
                  ))}
                </div>
              </details>
            )}

            <section className="card mb-6 p-5 sm:p-6">
              <h2 className="mb-1">Ваши документы</h2>
              <p className="mb-4 text-[0.9rem]" style={{ color: "var(--ink-2)" }}>
                Загрузите справки и заключения — они будут в одном месте, и их не придётся
                собирать заново при обращении в следующее ведомство. Документы видит куратор вашего кейса.
              </p>
              <Documents caseId={detail.case_id} lang={lang} />
            </section>

            {!detail.parent_support_note && (
              <section className="card mb-6 p-5 sm:p-6">
                <h3 className="mb-2 inline-flex items-center gap-2"><Icon.heart size={18} /> {t("supportTitle", lang)}</h3>
                <p className="mb-4 text-[0.93rem]" style={{ color: "var(--ink-2)" }}>
                  Маршрут ребёнка зависит и от вашего состояния. Если чувствуете, что сил меньше — это важно заметить вовремя.
                </p>
                {detail.phq9_history?.length > 0 && (
                  <div className="mb-4 rounded-[var(--radius-s)] p-4" style={{ background: "var(--surface-2)" }}>
                    <h4 className="mb-2 text-[0.88rem] font-semibold">Как меняется ваше состояние</h4>
                    <WellbeingTrack history={detail.phq9_history} />
                  </div>
                )}
                <PhqCard caseId={detail.case_id} lang={lang} initialScore={detail.phq9_score} />
              </section>
            )}

            <p className="text-center text-[0.79rem]" style={{ color: "var(--ink-muted)" }}>
              {t("provisional", lang)} {t("notDiagnosis", lang)}
            </p>
          </>
        )}

        {err && <div className="mt-4"><Banner tone="warn">{err}</Banner></div>}
      </div>
    </main>
  );
}

export default function PlanPage() {
  return <Suspense fallback={<Spinner label="…" />}><PlanInner /></Suspense>;
}
