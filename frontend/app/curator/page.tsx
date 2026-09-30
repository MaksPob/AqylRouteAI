"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, type CaseSummary, type Notification, token } from "@/lib/api";
import { BLOCKER_NAMES, localName, REGION_NAMES, t } from "@/lib/i18n";
import { Header, Icon, Spinner, useLang } from "@/components/ui";

/** Плитка сводки. Число крупное, подпись и иконка рядом — цвет не единственный носитель смысла. */
function Tile({ n, label, color, bg, icon: I, onClick, active }: {
  n: number; label: string; color: string; bg: string;
  icon: (p: { size?: number }) => React.ReactNode; onClick?: () => void; active?: boolean;
}) {
  const Wrap = onClick ? "button" : "div";
  return (
    <Wrap onClick={onClick}
          className={`card flex items-center gap-3.5 p-4 text-left transition-shadow ${onClick ? "hover:shadow-[var(--shadow-l)]" : ""}`}
          style={active ? { borderColor: color, borderWidth: 1.5 } : undefined}
          aria-pressed={onClick ? !!active : undefined}>
      <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[11px]"
            style={{ background: bg, color }}>
        <I size={19} />
      </span>
      <span className="min-w-0">
        <span className="block text-[1.65rem] font-bold leading-none tracking-tight" style={{ color }}>{n}</span>
        <span className="mt-1 block text-[0.8rem] leading-snug" style={{ color: "var(--ink-muted)" }}>{label}</span>
      </span>
    </Wrap>
  );
}

export default function CuratorDashboard() {
  const [lang, setLang] = useLang();
  const router = useRouter();
  const [cases, setCases] = useState<CaseSummary[] | null>(null);
  const [notes, setNotes] = useState<Notification[]>([]);
  const [filter, setFilter] = useState<"all" | "review" | "overdue" | "blocked">("all");

  const load = useCallback(async () => {
    const [c, n] = await Promise.all([api.cases(), api.notifications()]);
    setCases(c); setNotes(n);
  }, []);

  useEffect(() => {
    if (!token.get()) { router.replace("/"); return; }
    api.me().then((u) => { if (u.role !== "curator") router.replace("/plan"); else load(); })
      .catch(() => router.replace("/"));
  }, [load, router]);

  if (!cases) return <Spinner label={t("loading", lang)} />;

  const totals = cases.reduce((a, c) => ({
    overdue: a.overdue + c.stats.overdue,
    blocked: a.blocked + c.stats.blocked,
    active: a.active + c.stats.active,
    done: a.done + c.stats.done,
    review: a.review + (!c.reviewed && c.case_status === "active" ? 1 : 0),
  }), { overdue: 0, blocked: 0, active: 0, done: 0, review: 0 });

  // Управленческая аналитика: не «17 просрочено», а по причинам остановки
  const blockers: Record<string, number> = {};
  for (const c of cases) for (const [k, v] of Object.entries(c.stats.by_blocker)) blockers[k] = (blockers[k] ?? 0) + v;
  const blockerTotal = Object.values(blockers).reduce((a, b) => a + b, 0);

  const shown = cases.filter((c) =>
    filter === "all" ? true
    : filter === "review" ? !c.reviewed && c.case_status === "active"
    : filter === "overdue" ? c.stats.overdue > 0
    : c.stats.blocked > 0);

  return (
    <main className="min-h-screen pb-16">
      <Header lang={lang} setLang={setLang} title={t("dashboard", lang)}
              subtitle={`${cases.length} ${cases.length === 1 ? "кейс" : "кейсов"}`}
              right={notes.length > 0 ? (
                <span className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[0.8rem] font-semibold"
                      style={{ background: "var(--st-overdue-bg)", color: "var(--st-overdue)" }}>
                  <Icon.bell size={14} /> {notes.length}
                </span>
              ) : undefined} />

      <div className="mx-auto max-w-6xl px-4 pt-5 sm:px-6 sm:pt-7">
        {/* сводка */}
        <div className="scroll-row mb-7">
          <Tile n={totals.review} label="Не проверено" color="var(--st-waiting)" bg="var(--st-waiting-bg)"
                icon={Icon.clock} onClick={() => setFilter(filter === "review" ? "all" : "review")} active={filter === "review"} />
          <Tile n={totals.overdue} label={t("stOVERDUE", lang)} color="var(--st-overdue)" bg="var(--st-overdue-bg)"
                icon={Icon.alert} onClick={() => setFilter(filter === "overdue" ? "all" : "overdue")} active={filter === "overdue"} />
          <Tile n={totals.blocked} label={t("stBLOCKED", lang)} color="var(--st-blocked)" bg="var(--st-blocked-bg)"
                icon={Icon.blocked} onClick={() => setFilter(filter === "blocked" ? "all" : "blocked")} active={filter === "blocked"} />
          <Tile n={totals.done} label={t("stDONE", lang)} color="var(--st-done)" bg="var(--st-done-bg)" icon={Icon.check} />
        </div>

        <div className="grid gap-6 lg:grid-cols-[1.55fr_1fr]">
          {/* кейсы */}
          <section>
            <div className="mb-3 flex items-center justify-between">
              <h2>{filter === "all" ? t("allCases", lang) : `${shown.length} из ${cases.length}`}</h2>
              {filter !== "all" && (
                <button className="btn btn-quiet !text-[0.84rem]" onClick={() => setFilter("all")}>Показать все</button>
              )}
            </div>

            <ul className="grid gap-3">
              {shown.map((c) => {
                const urgent = c.stats.overdue > 0 || c.stats.blocked > 0;
                return (
                  <li key={c.case_id}>
                    <button onClick={() => router.push(`/curator/case?id=${c.case_id}`)}
                            className="card w-full p-4 text-left transition-shadow hover:shadow-[var(--shadow-l)] sm:p-5"
                            style={urgent ? { borderColor: "var(--st-overdue)" } : undefined}>
                      <div className="mb-2 flex flex-wrap items-center gap-2">
                        <span className="font-semibold">{c.child_name || "Без имени"}</span>
                        <span className="text-[0.82rem]" style={{ color: "var(--ink-muted)" }}>
                          {c.case_id} · {c.child_age > 0 && `${c.child_age} лет · `}{localName(REGION_NAMES, c.region, lang)}
                        </span>
                        {!c.reviewed && c.case_status === "active" && (
                          <span className="rounded-full px-2.5 py-0.5 text-[0.75rem] font-semibold"
                                style={{ background: "var(--st-waiting-bg)", color: "var(--st-waiting)" }}>
                            не проверен
                          </span>
                        )}
                      </div>

                      <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-[0.84rem]">
                        {c.stats.overdue > 0 && (
                          <span className="inline-flex items-center gap-1.5 font-semibold" style={{ color: "var(--st-overdue)" }}>
                            <Icon.alert size={14} /> {c.stats.overdue} {t("stOVERDUE", lang).toLowerCase()}
                          </span>
                        )}
                        {c.stats.blocked > 0 && (
                          <span className="inline-flex items-center gap-1.5 font-semibold" style={{ color: "var(--st-blocked)" }}>
                            <Icon.blocked size={14} /> {c.stats.blocked} {t("stBLOCKED", lang).toLowerCase()}
                          </span>
                        )}
                        <span style={{ color: "var(--ink-muted)" }}>
                          {c.stats.active} в работе · {c.stats.done} выполнено
                        </span>
                        {c.stats.max_days_overdue > 0 && (
                          <span className="rounded-full px-2 py-0.5 text-[0.76rem] font-semibold"
                                style={{ background: "var(--st-overdue-bg)", color: "var(--st-overdue)" }}>
                            {t("escalation", lang)}: {c.stats.max_days_overdue} {t("days", lang)}
                          </span>
                        )}
                        {c.phq9_score !== null && c.phq9_score >= 10 && (
                          <span className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[0.76rem]"
                                style={{ background: "var(--surface-2)", color: "var(--ink-2)" }}>
                            <Icon.heart size={12} /> PHQ-9: {c.phq9_score}
                          </span>
                        )}
                      </div>
                    </button>
                  </li>
                );
              })}
            </ul>
          </section>

          {/* правая колонка */}
          <aside className="grid gap-6 content-start">
            {blockerTotal > 0 && (
              <section className="card p-5">
                <h3 className="mb-1">Почему маршруты стоят</h3>
                <p className="mb-4 text-[0.82rem]" style={{ color: "var(--ink-muted)" }}>
                  {blockerTotal} шагов заблокировано
                </p>
                <ul className="grid gap-2.5">
                  {Object.entries(blockers).sort((a, b) => b[1] - a[1]).map(([k, v]) => (
                    <li key={k}>
                      <div className="mb-1 flex items-baseline justify-between gap-2 text-[0.87rem]">
                        <span>{localName(BLOCKER_NAMES, k, lang)}</span>
                        <span className="font-semibold tabular-nums">{v}</span>
                      </div>
                      <div className="h-1.5 overflow-hidden rounded-full" style={{ background: "var(--surface-2)" }}>
                        <div className="h-full rounded-full"
                             style={{ width: `${(v / blockerTotal) * 100}%`, background: "var(--st-blocked)" }} />
                      </div>
                    </li>
                  ))}
                </ul>
              </section>
            )}

            <section className="card p-5">
              <h3 className="mb-3 inline-flex items-center gap-2"><Icon.bell size={17} /> {t("notifications", lang)}</h3>
              {notes.length === 0 ? (
                <p className="text-[0.88rem]" style={{ color: "var(--ink-muted)" }}>{t("noNotifications", lang)}</p>
              ) : (
                <ul className="grid gap-2.5">
                  {notes.slice(0, 8).map((n, i) => (
                    <li key={`${n.case_id}-${n.item_code}-${i}`}>
                      <button onClick={() => router.push(`/curator/case?id=${n.case_id}`)}
                              className="w-full rounded-[var(--radius-s)] border px-3 py-2.5 text-left transition-colors hover:bg-[var(--surface-2)]"
                              style={{ borderColor: "var(--border)" }}>
                        <div className="mb-0.5 flex items-center gap-2">
                          <span className="h-1.5 w-1.5 shrink-0 rounded-full" style={{
                            background: n.level === "HIGH_ESCALATION" || n.level === "ESCALATION" ? "var(--st-overdue)"
                              : n.level === "REVIEW" ? "var(--st-waiting)" : "var(--st-todo)" }} />
                          <span className="truncate text-[0.87rem] font-medium">{n.title}</span>
                        </div>
                        <div className="text-[0.79rem]" style={{ color: "var(--ink-muted)" }}>
                          {n.case_id}{n.days_overdue > 0 && ` · ${n.days_overdue} ${t("days", lang)}`}
                          {n.action && ` · ${n.action}`}
                        </div>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </aside>
        </div>
      </div>
    </main>
  );
}
