"use client";

/** Общие элементы интерфейса. Статус всегда несёт иконку и подпись, а не только цвет. */

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import type { Status } from "@/lib/api";
import { api, token } from "@/lib/api";
import { LANGS, type Lang, t } from "@/lib/i18n";

// ─────────────────────────── иконки ───────────────────────────
// Линейные, одного веса. Никаких эмодзи в интерфейсе.

type IconProps = { size?: number; className?: string };
const svg = (d: React.ReactNode, { size = 18, className = "" }: IconProps) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
       strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
    {d}
  </svg>
);

export const Icon = {
  check:   (p: IconProps = {}) => svg(<polyline points="4 12.5 9.5 18 20 6.5" />, p),
  clock:   (p: IconProps = {}) => svg(<><circle cx="12" cy="12" r="9" /><polyline points="12 7 12 12 15.5 14" /></>, p),
  alert:   (p: IconProps = {}) => svg(<><path d="M12 3.6 1.9 20.4h20.2z" /><line x1="12" y1="9.5" x2="12" y2="14" /><circle cx="12" cy="17.2" r=".6" fill="currentColor" /></>, p),
  pause:   (p: IconProps = {}) => svg(<><rect x="7" y="5" width="3.4" height="14" rx="1.1" /><rect x="13.6" y="5" width="3.4" height="14" rx="1.1" /></>, p),
  play:    (p: IconProps = {}) => svg(<polygon points="7 4.5 19.5 12 7 19.5" />, p),
  blocked: (p: IconProps = {}) => svg(<><circle cx="12" cy="12" r="9" /><line x1="5.6" y1="5.6" x2="18.4" y2="18.4" /></>, p),
  minus:   (p: IconProps = {}) => svg(<line x1="6" y1="12" x2="18" y2="12" />, p),
  arrow:   (p: IconProps = {}) => svg(<><line x1="4.5" y1="12" x2="19" y2="12" /><polyline points="13 6 19 12 13 18" /></>, p),
  back:    (p: IconProps = {}) => svg(<><line x1="19.5" y1="12" x2="5" y2="12" /><polyline points="11 6 5 12 11 18" /></>, p),
  bell:    (p: IconProps = {}) => svg(<><path d="M18 9a6 6 0 0 0-12 0c0 6-2.4 7.5-2.4 7.5h16.8S18 15 18 9" /><path d="M13.7 20.4a2 2 0 0 1-3.4 0" /></>, p),
  doc:     (p: IconProps = {}) => svg(<><path d="M14 2.8H6.6A1.6 1.6 0 0 0 5 4.4v15.2a1.6 1.6 0 0 0 1.6 1.6h10.8a1.6 1.6 0 0 0 1.6-1.6V7.8z" /><polyline points="14 2.8 14 8 19 8" /></>, p),
  pin:     (p: IconProps = {}) => svg(<><path d="M20 10.2c0 6.1-8 12.2-8 12.2s-8-6.1-8-12.2a8 8 0 0 1 16 0z" /><circle cx="12" cy="10" r="2.8" /></>, p),
  user:    (p: IconProps = {}) => svg(<><path d="M20 21v-1.9a4.6 4.6 0 0 0-4.6-4.6H8.6A4.6 4.6 0 0 0 4 19.1V21" /><circle cx="12" cy="7.4" r="4" /></>, p),
  heart:   (p: IconProps = {}) => svg(<path d="M20.4 5.6a5.1 5.1 0 0 0-7.2 0L12 6.8l-1.2-1.2a5.1 5.1 0 0 0-7.2 7.2l1.2 1.2L12 21.2l7.2-7.2 1.2-1.2a5.1 5.1 0 0 0 0-7.2z" />, p),
  logout:  (p: IconProps = {}) => svg(<><path d="M9.5 21H5.4A1.4 1.4 0 0 1 4 19.6V4.4A1.4 1.4 0 0 1 5.4 3h4.1" /><polyline points="15.5 16.5 20 12 15.5 7.5" /><line x1="20" y1="12" x2="9.5" y2="12" /></>, p),
  edit:    (p: IconProps = {}) => svg(<><path d="M4 20h4.2L19.4 8.8a2 2 0 0 0 0-2.8l-1.4-1.4a2 2 0 0 0-2.8 0L4 15.8z" /><line x1="14.5" y1="6" x2="18" y2="9.5" /></>, p),
  shield:  (p: IconProps = {}) => svg(<><path d="M12 2.8 4.5 6v6c0 4.6 3.2 8.4 7.5 9.3 4.3-.9 7.5-4.7 7.5-9.3V6z" /><polyline points="8.8 12 11.2 14.4 15.4 10" /></>, p),
};

// ─────────────────────────── статусы ───────────────────────────

export const STATUS_META: Record<Status, { color: string; bg: string; icon: keyof typeof Icon }> = {
  DONE:        { color: "var(--st-done)",      bg: "var(--st-done-bg)",      icon: "check" },
  TODO:        { color: "var(--st-todo)",      bg: "var(--st-todo-bg)",      icon: "clock" },
  IN_PROGRESS: { color: "var(--st-progress)",  bg: "var(--st-progress-bg)",  icon: "play" },
  WAITING:     { color: "var(--st-waiting)",   bg: "var(--st-waiting-bg)",   icon: "pause" },
  OVERDUE:     { color: "var(--st-overdue)",   bg: "var(--st-overdue-bg)",   icon: "alert" },
  BLOCKED:     { color: "var(--st-blocked)",   bg: "var(--st-blocked-bg)",   icon: "blocked" },
  CANCELLED:   { color: "var(--st-cancelled)", bg: "var(--st-cancelled-bg)", icon: "minus" },
};

export function StatusBadge({ status, lang, size = "md" }: { status: Status; lang: Lang; size?: "sm" | "md" }) {
  const m = STATUS_META[status];
  const I = Icon[m.icon];
  const label = t(`st${status}` as never, lang);
  return (
    <span
      style={{ background: m.bg, color: m.color, borderColor: m.color }}
      className={`inline-flex items-center gap-1.5 rounded-full border font-semibold whitespace-nowrap ${
        size === "sm" ? "px-2.5 py-0.5 text-xs" : "px-3 py-1 text-[0.82rem]"
      }`}
    >
      <I size={size === "sm" ? 13 : 15} />
      {label}
    </span>
  );
}

export function PriorityMark({ priority, lang }: { priority: "HIGH" | "MEDIUM" | "LOW"; lang: Lang }) {
  const label = t(`pr${priority}` as never, lang);
  const bars = priority === "HIGH" ? 3 : priority === "MEDIUM" ? 2 : 1;
  const color = priority === "HIGH" ? "var(--st-overdue)" : priority === "MEDIUM" ? "var(--st-todo)" : "var(--ink-muted)";
  return (
    <span className="inline-flex items-center gap-1.5 text-[0.8rem]" style={{ color: "var(--ink-2)" }} title={label}>
      <span className="inline-flex items-end gap-[2px]" aria-hidden="true">
        {[0, 1, 2].map((i) => (
          <span key={i} style={{ height: 5 + i * 3.5, width: 3, borderRadius: 1.5,
            background: i < bars ? color : "var(--border-strong)" }} />
        ))}
      </span>
      {label}
    </span>
  );
}

// ─────────────────────── каркас страницы ───────────────────────

export function useLang(): [Lang, (l: Lang) => void] {
  const [lang, setLang] = useState<Lang>("ru");
  useEffect(() => {
    const saved = localStorage.getItem("aqyl_lang") as Lang | null;
    if (saved && LANGS.some((l) => l.code === saved)) setLang(saved);
  }, []);
  const set = (l: Lang) => { setLang(l); localStorage.setItem("aqyl_lang", l); };
  return [lang, set];
}

export function LangSwitch({ lang, onChange }: { lang: Lang; onChange: (l: Lang) => void }) {
  return (
    <div role="group" aria-label="Язык интерфейса"
         className="inline-flex rounded-full p-0.5" style={{ background: "var(--surface-2)", border: "1px solid var(--border)" }}>
      {LANGS.map((l) => (
        <button key={l.code} onClick={() => onChange(l.code)} aria-pressed={lang === l.code}
          className="rounded-full px-2.5 py-1 text-[0.78rem] font-semibold transition-colors"
          style={lang === l.code
            ? { background: "var(--surface)", color: "var(--ink)", boxShadow: "var(--shadow)" }
            : { color: "var(--ink-muted)" }}>
          {l.label}
        </button>
      ))}
    </div>
  );
}

export function Header({ lang, setLang, title, subtitle, right, back }:
  { lang: Lang; setLang: (l: Lang) => void; title: string; subtitle?: string;
    right?: React.ReactNode; back?: () => void }) {
  const router = useRouter();
  const signOut = async () => {
    try { await api.logout(); } catch { /* сессия уже недействительна */ }
    token.clear();
    router.push("/");
  };
  return (
    <header className="sticky top-0 z-30 border-b backdrop-blur"
            style={{ background: "color-mix(in srgb, var(--surface) 88%, transparent)", borderColor: "var(--border)" }}>
      <div className="mx-auto flex max-w-6xl items-center gap-2 px-3 py-2.5 sm:gap-3 sm:px-6 sm:py-3">
        {back && (
          <button onClick={back} className="btn btn-quiet -ml-2" aria-label={t("back", lang)}>
            <Icon.back size={20} />
          </button>
        )}
        <div className="min-w-0 flex-1">
          <div className="truncate text-[0.97rem] font-bold tracking-tight sm:text-[1.02rem]">{title}</div>
          {subtitle && (
            <div className="truncate text-[0.78rem] sm:text-[0.83rem]" style={{ color: "var(--ink-muted)" }}>
              {subtitle}
            </div>
          )}
        </div>
        {right}
        <LangSwitch lang={lang} onChange={setLang} />
        <button onClick={signOut} className="btn btn-quiet" title={t("signOut", lang)} aria-label={t("signOut", lang)}>
          <Icon.logout size={18} />
        </button>
      </div>
    </header>
  );
}

export function Banner({ tone = "info", children }: { tone?: "info" | "warn" | "soft"; children: React.ReactNode }) {
  const styles = {
    info: { bg: "var(--brand-soft)", border: "var(--brand)", ink: "var(--brand-ink)" },
    warn: { bg: "var(--st-overdue-bg)", border: "var(--st-overdue)", ink: "var(--st-overdue)" },
    soft: { bg: "var(--surface-2)", border: "var(--border-strong)", ink: "var(--ink-2)" },
  }[tone];
  return (
    <div className="rounded-[var(--radius-s)] border-l-[3px] px-4 py-3 text-[0.9rem]"
         style={{ background: styles.bg, borderColor: styles.border, color: styles.ink }}>
      {children}
    </div>
  );
}

export function Spinner({ label }: { label: string }) {
  return (
    <div className="flex items-center justify-center gap-3 py-16" style={{ color: "var(--ink-muted)" }}>
      <span className="inline-block h-5 w-5 animate-spin rounded-full border-2 border-current border-t-transparent" aria-hidden="true" />
      <span>{label}</span>
    </div>
  );
}

export function Progress({ value, total, label }: { value: number; total: number; label?: string }) {
  const pct = total > 0 ? Math.min(100, Math.round((value / total) * 100)) : 0;
  return (
    <div>
      <div className="h-1.5 w-full overflow-hidden rounded-full" style={{ background: "var(--surface-2)" }}
           role="progressbar" aria-valuenow={value} aria-valuemin={0} aria-valuemax={total} aria-label={label}>
        <div className="h-full rounded-full transition-[width] duration-500"
             style={{ width: `${pct}%`, background: "var(--brand)" }} />
      </div>
    </div>
  );
}
