"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { api, type Step, token } from "@/lib/api";
import { t } from "@/lib/i18n";
import { Banner, Header, Icon, Progress, Spinner, useLang } from "@/components/ui";

/** Родителю не нужен текст сетевой ошибки — ему нужно понятное объяснение. */
function friendly(e: unknown, fallback = "Не удалось связаться с сервером. Проверьте соединение."): string {
  const raw = e instanceof Error ? e.message : String(e);
  if (/failed to fetch|networkerror|load failed/i.test(raw)) return fallback;
  return raw;
}

function InterviewInner() {
  const [lang, setLang] = useLang();
  const router = useRouter();
  const params = useSearchParams();
  const caseId = params.get("case");

  const [step, setStep] = useState<Step | null>(null);
  const [answer, setAnswer] = useState<string>("");
  const [multi, setMulti] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [building, setBuilding] = useState(false);
  const [err, setErr] = useState("");
  const [engine, setEngine] = useState("");
  const [showClarify, setShowClarify] = useState(false);
  const liveRef = useRef<HTMLDivElement>(null);

  // Strict Mode в разработке монтирует компонент дважды; без этого замка
  // создаются два кейса, а отменённый запрос показывается родителю как ошибка
  const started = useRef(false);

  // Первый вопрос: либо продолжаем существующий кейс, либо создаём новый
  useEffect(() => {
    if (!token.get()) { router.replace("/"); return; }
    if (started.current) return;
    started.current = true;
    if (caseId) {
      api.answer({ case_id: caseId, question_id: "__resume__", question: "", answer: "", lang })
        .then((r) => { setStep(r.step); setEngine(r.engine); })
        .catch((e) => setErr(friendly(e)));
    } else {
      api.startCase("", lang)
        .then((r) => {
          setStep(r.step); setEngine(r.engine);
          router.replace(`/interview?case=${r.case_id}`);
        })
        .catch((e) => setErr(friendly(e)));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const q = step?.next_question ?? null;

  useEffect(() => { setAnswer(""); setMulti([]); setShowClarify(false); }, [q?.question_id]);

  const send = async (value: string) => {
    if (!caseId || !q) return;
    setBusy(true); setErr("");
    try {
      const r = await api.answer({ case_id: caseId, question_id: q.question_id, question: q.text, answer: value, lang });
      setStep(r.step); setEngine(r.engine);
      liveRef.current?.focus();
    } catch (e) {
      setErr(friendly(e, "Не удалось сохранить ответ. Попробуйте ещё раз."));
    } finally { setBusy(false); }
  };

  const build = async () => {
    if (!caseId) return;
    setBuilding(true); setErr("");
    try {
      await api.buildPlan(caseId, lang);
      router.push(`/plan?case=${caseId}`);
    } catch (e) {
      setErr(friendly(e, "Не удалось построить план. Попробуйте ещё раз."));
      setBuilding(false);
    }
  };

  if (err && !step) {
    return <main className="mx-auto max-w-2xl p-6"><Banner tone="warn">{err}</Banner></main>;
  }
  if (!step) return <Spinner label={t("loading", lang)} />;
  if (building) {
    return (
      <main className="grid min-h-screen place-items-center px-4">
        <div className="text-center">
          <div className="mx-auto mb-5 h-10 w-10 animate-spin rounded-full border-[2.5px] border-current border-t-transparent"
               style={{ color: "var(--brand)" }} aria-hidden="true" />
          <h2 className="mb-2">{t("building", lang)}</h2>
          <p style={{ color: "var(--ink-muted)" }}>Подбираем шаги из справочника услуг вашего региона</p>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen pb-16">
      <Header lang={lang} setLang={setLang} title={t("newCase", lang)}
              subtitle={engine.includes("demo") ? t("demoMode", lang) : "OpenAI structured outputs"}
              back={() => router.push("/plan")} />

      <div className="mx-auto max-w-2xl px-4 pt-5 sm:px-6 sm:pt-7">
        {/* прогресс */}
        <div className="mb-7">
          <div className="mb-2 flex items-baseline justify-between gap-2 text-[0.82rem]" style={{ color: "var(--ink-muted)" }}>
            <span className="truncate">{t("question", lang)} {step.progress_current} {t("of", lang)} {step.progress_total}</span>
            <span>{Math.round((step.progress_current / Math.max(1, step.progress_total)) * 100)}%</span>
          </div>
          <Progress value={step.progress_current} total={step.progress_total} label={t("question", lang)} />
        </div>

        {step.acknowledgement && (
          <p className="mb-6 text-[0.93rem] italic" style={{ color: "var(--ink-2)" }}>{step.acknowledgement}</p>
        )}

        <div ref={liveRef} tabIndex={-1} aria-live="polite" className="outline-none">
          {step.is_complete || !q ? (
            <section className="card p-6 text-center sm:p-8">
              <span className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full"
                    style={{ background: "var(--st-done-bg)", color: "var(--st-done)" }}>
                <Icon.check size={24} />
              </span>
              <h2 className="mb-2">{t("interviewDone", lang)}</h2>
              <p className="mx-auto mb-6 max-w-md" style={{ color: "var(--ink-2)" }}>
                Теперь соберём ваш маршрут. План проверит куратор, прежде чем он станет окончательным.
              </p>
              <button className="btn btn-primary" onClick={build}>
                {t("buildPlan", lang)} <Icon.arrow size={18} />
              </button>
            </section>
          ) : (
            <section className="card p-5 sm:p-7">
              <h2 className="mb-3 text-balance">{q.text}</h2>

              {q.why && (
                <p className="mb-6 flex gap-2 text-[0.87rem]" style={{ color: "var(--ink-muted)" }}>
                  <span className="mt-0.5 shrink-0 opacity-70"><Icon.doc size={15} /></span>
                  <span>{q.why}</span>
                </p>
              )}

              {/* одиночный выбор */}
              {q.input_type === "single_choice" && (
                <div className="grid gap-2">
                  {q.options.map((o) => (
                    <button key={o.value} disabled={busy} onClick={() => send(o.value)}
                            className="flex min-h-[52px] items-center justify-between gap-3 rounded-[var(--radius-s)] border px-4 py-3.5 text-left transition-colors active:bg-[var(--surface-2)] hover:bg-[var(--surface-2)] disabled:opacity-50"
                            style={{ borderColor: "var(--border-strong)" }}>
                      <span className="text-[0.97rem]">{o.label}</span>
                      <Icon.arrow size={17} className="shrink-0 opacity-30" />
                    </button>
                  ))}
                </div>
              )}

              {/* множественный выбор */}
              {q.input_type === "multi_choice" && (
                <>
                  <div className="grid gap-2">
                    {q.options.map((o) => {
                      const on = multi.includes(o.value);
                      return (
                        <label key={o.value}
                               className="flex cursor-pointer items-center gap-3 rounded-[var(--radius-s)] border px-4 py-3 transition-colors hover:bg-[var(--surface-2)]"
                               style={{ borderColor: on ? "var(--brand)" : "var(--border-strong)",
                                        background: on ? "var(--brand-soft)" : "transparent" }}>
                          <input type="checkbox" className="sr-only" checked={on}
                                 onChange={() => setMulti((m) => on ? m.filter((x) => x !== o.value) : [...m, o.value])} />
                          <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-[6px] border-[1.5px]"
                                style={{ borderColor: on ? "var(--brand)" : "var(--border-strong)",
                                         background: on ? "var(--brand)" : "transparent", color: "#fff" }}>
                            {on && <Icon.check size={13} />}
                          </span>
                          <span className="text-[0.97rem]">{o.label}</span>
                        </label>
                      );
                    })}
                  </div>
                  <div className="action-bar mt-5">
                  <button className="btn btn-primary w-full" disabled={busy || multi.length === 0}
                          onClick={() => send(multi.join(","))}>
                    {t("next", lang)} <Icon.arrow size={18} />
                  </button>
                  {multi.length === 0 && (
                    <p className="mt-2 text-center text-[0.8rem]" style={{ color: "var(--ink-muted)" }}>
                      {t("selectAtLeast", lang)}
                    </p>
                  )}
                  </div>
                </>
              )}

              {/* свободный ввод */}
              {["text", "number", "date"].includes(q.input_type) && (
                <form onSubmit={(e) => { e.preventDefault(); if (answer.trim()) send(answer.trim()); }}>
                  <input className="field" autoFocus value={answer} onChange={(e) => setAnswer(e.target.value)}
                         type={q.input_type === "number" ? "number" : q.input_type === "date" ? "date" : "text"}
                         inputMode={q.input_type === "number" ? "decimal" : undefined}
                         min={q.input_type === "number" ? 0 : undefined}
                         max={q.input_type === "number" ? 18 : undefined}
                         step={q.input_type === "number" ? "0.5" : undefined} />
                  <div className="action-bar mt-4">
                    <button className="btn btn-primary w-full" disabled={busy || !answer.trim()}>
                      {t("next", lang)} <Icon.arrow size={18} />
                    </button>
                  </div>
                </form>
              )}

              {/* «не знаю» — равноправный ответ, а не отговорка */}
              {q.allow_dont_know && (
                <div className="mt-5 border-t pt-4" style={{ borderColor: "var(--border)" }}>
                  <button className="btn btn-quiet w-full justify-center text-[0.88rem]" disabled={busy}
                          onClick={() => { if (q.clarification) setShowClarify(true); else send("UNKNOWN"); }}>
                    {t("dontKnow", lang)}
                  </button>
                  {showClarify && q.clarification && (
                    <div className="mt-3">
                      <Banner tone="info">{q.clarification}</Banner>
                      <button className="btn btn-ghost mt-3 w-full" disabled={busy} onClick={() => send("UNKNOWN")}>
                        Понятно, продолжим
                      </button>
                    </div>
                  )}
                </div>
              )}
            </section>
          )}
        </div>

        {err && <div className="mt-4"><Banner tone="warn">{err}</Banner></div>}

        <p className="mt-6 text-center text-[0.79rem] leading-relaxed" style={{ color: "var(--ink-muted)" }}>
          {t("notDiagnosis", lang)}
        </p>
      </div>
    </main>
  );
}

export default function InterviewPage() {
  return (
    <Suspense fallback={<Spinner label="…" />}>
      <InterviewInner />
    </Suspense>
  );
}
