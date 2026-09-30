"use client";

/** Скрининг PHQ-9. Инструмент открытый; результат — не диагноз, а повод предложить поддержку. */

import { useState } from "react";
import { api } from "@/lib/api";
import { type Lang, t } from "@/lib/i18n";
import { Banner, Icon } from "./ui";

type Form = Awaited<ReturnType<typeof api.phq9form>>;
type Result = Awaited<ReturnType<typeof api.phq9submit>>;

const SEVERITY_COLOR: Record<string, string> = {
  minimal: "var(--st-done)",
  mild: "var(--st-todo)",
  moderate: "var(--st-blocked)",
  moderately_severe: "var(--st-overdue)",
  severe: "var(--st-overdue)",
};

export function PhqCard({ caseId, lang, initialScore }:
  { caseId: string; lang: Lang; initialScore: number | null }) {
  const [form, setForm] = useState<Form | null>(null);
  const [answers, setAnswers] = useState<number[]>(Array(9).fill(-1));
  const [result, setResult] = useState<Result | null>(null);
  const [busy, setBusy] = useState(false);

  const open = async () => {
    setBusy(true);
    try { setForm(await api.phq9form(lang)); } finally { setBusy(false); }
  };

  const submit = async () => {
    setBusy(true);
    try { setResult(await api.phq9submit(caseId, answers)); }
    finally { setBusy(false); }
  };

  if (result) {
    return (
      <div>
        <div className="mb-3 flex items-baseline gap-2">
          <span className="text-[2rem] font-bold leading-none tracking-tight"
                style={{ color: SEVERITY_COLOR[result.severity] ?? "var(--ink)" }}>
            {result.score}
          </span>
          <span style={{ color: "var(--ink-muted)" }}>{t("outOf", lang)} {result.max_score}</span>
        </div>
        <p className="mb-3 text-[0.95rem]">{result.note}</p>
        {result.crisis_flag && <div className="mb-3"><Banner tone="warn">{result.crisis_message}</Banner></div>}
        <p className="text-[0.78rem]" style={{ color: "var(--ink-muted)" }}>{result.disclaimer}</p>
      </div>
    );
  }

  if (!form) {
    return (
      <div>
        {initialScore !== null && (
          <p className="mb-3 text-[0.88rem]" style={{ color: "var(--ink-muted)" }}>
            Прошлый результат: {initialScore} из 27
          </p>
        )}
        <button className="btn btn-ghost" onClick={open} disabled={busy}>
          <Icon.heart size={16} /> {t("phq9Start", lang)}
        </button>
      </div>
    );
  }

  const ready = answers.every((a) => a >= 0);

  return (
    <div>
      <p className="mb-5 text-[0.92rem]" style={{ color: "var(--ink-2)" }}>{form.preamble}</p>
      <ol className="mb-5 grid gap-4">
        {form.questions.map((q, i) => (
          <li key={q.id}>
            <p className="mb-2 text-[0.93rem]">{i + 1}. {q.text}</p>
            <div className="flex flex-wrap gap-1.5" role="group" aria-label={q.text}>
              {form.options.map((o) => {
                const on = answers[i] === o.value;
                return (
                  <button key={o.value} onClick={() => setAnswers((a) => a.map((v, j) => (j === i ? o.value : v)))}
                          aria-pressed={on}
                          className="rounded-full border px-3 py-1.5 text-[0.82rem] transition-colors"
                          style={on
                            ? { background: "var(--brand)", borderColor: "var(--brand)", color: "#fff", fontWeight: 600 }
                            : { borderColor: "var(--border-strong)", color: "var(--ink-2)" }}>
                    {o.label}
                  </button>
                );
              })}
            </div>
          </li>
        ))}
      </ol>
      <button className="btn btn-primary" disabled={!ready || busy} onClick={submit}>
        {t("phq9Submit", lang)}
      </button>
      <p className="mt-3 text-[0.78rem]" style={{ color: "var(--ink-muted)" }}>{form.disclaimer}</p>
    </div>
  );
}
