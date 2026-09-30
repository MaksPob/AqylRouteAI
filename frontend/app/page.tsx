"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, token } from "@/lib/api";
import { t } from "@/lib/i18n";
import { Icon, LangSwitch, useLang } from "@/components/ui";

const DEMO = [
  { login: "parent",  password: "parent123",  roleKey: "parentRole" as const,  name: "Айгуль Сериковна",   note: "Астана · кейс на проверке" },
  { login: "parent2", password: "parent123",  roleKey: "parentRole" as const,  name: "Марат Жанболатович", note: "Караганда · есть просрочка" },
  { login: "curator", password: "curator123", roleKey: "curatorRole" as const, name: "Динара Кайратовна",  note: "Видит все кейсы" },
];

export default function LoginPage() {
  const [lang, setLang] = useLang();
  const [login, setLogin] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [engine, setEngine] = useState<string>("");
  const router = useRouter();

  useEffect(() => {
    api.health().then((h) => setEngine(h.ai_engine)).catch(() => setEngine("offline"));
    if (token.get()) {
      api.me()
        .then((u) => router.replace(u.role === "curator" ? "/curator" : "/plan"))
        .catch(() => token.clear());
    }
  }, [router]);

  const submit = async (e?: React.FormEvent, preset?: { login: string; password: string }) => {
    e?.preventDefault();
    setErr("");
    setBusy(true);
    try {
      const r = await api.login(preset?.login ?? login, preset?.password ?? password);
      token.set(r.token);
      router.push(r.user.role === "curator" ? "/curator" : "/plan");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Не удалось войти");
      setBusy(false);
    }
  };

  return (
    <main className="min-h-screen">
      <div className="mx-auto flex min-h-screen max-w-6xl flex-col px-4 sm:px-6">
        <div className="flex items-center justify-between py-5">
          <div className="flex items-center gap-2.5">
            <span className="flex h-9 w-9 items-center justify-center rounded-[11px] font-black text-white"
                  style={{ background: "var(--brand)" }} aria-hidden="true">A</span>
            <span className="text-[1.05rem] font-bold tracking-tight">AqylRoute</span>
          </div>
          <LangSwitch lang={lang} onChange={setLang} />
        </div>

        <div className="grid flex-1 items-center gap-10 py-8 lg:grid-cols-[1.05fr_minmax(340px,.95fr)] lg:gap-16">
          {/* Левая колонка — о продукте */}
          <section>
            <p className="mb-4 inline-flex items-center gap-2 rounded-full px-3 py-1 text-[0.78rem] font-semibold"
               style={{ background: "var(--brand-soft)", color: "var(--brand-ink)" }}>
              <Icon.shield size={14} /> Карагандинский медицинский университет
            </p>
            <h1 className="mb-5 max-w-xl text-balance">
              Маршрут помощи ребёнку — <span style={{ color: "var(--brand)" }}>в одном месте</span>
            </h1>
            <p className="mb-8 max-w-lg text-[1.06rem]" style={{ color: "var(--ink-2)" }}>
              Семьи детей с РАС теряются между здравоохранением, образованием и соцзащитой
              и собирают одни и те же документы по нескольку раз. AqylRoute собирает маршрут
              в один живой план: с ответственными, сроками и видимой точкой, где всё остановилось.
            </p>

            <div className="grid max-w-lg gap-3 sm:grid-cols-3">
              {[
                { n: "8–12", l: "вопросов адаптивного интервью" },
                { n: "20", l: "услуг в справочнике, 5 этапов" },
                { n: "0", l: "выдуманных AI действий" },
              ].map((s) => (
                <div key={s.l} className="card px-4 py-3.5">
                  <div className="text-[1.5rem] font-bold leading-none tracking-tight" style={{ color: "var(--brand)" }}>{s.n}</div>
                  <div className="mt-1.5 text-[0.8rem] leading-snug" style={{ color: "var(--ink-muted)" }}>{s.l}</div>
                </div>
              ))}
            </div>
          </section>

          {/* Правая колонка — вход */}
          <section className="card p-6 sm:p-7">
            <h2 className="mb-1">{t("login", lang)}</h2>
            <p className="mb-6 text-[0.88rem]" style={{ color: "var(--ink-muted)" }}>
              Выберите учётную запись ниже или введите данные вручную
            </p>

            <div className="mb-6 grid gap-2">
              {DEMO.map((d) => (
                <button key={d.login} onClick={() => submit(undefined, d)} disabled={busy}
                        className="flex items-center gap-3 rounded-[var(--radius-s)] border px-3.5 py-3 text-left transition-colors hover:bg-[var(--surface-2)] disabled:opacity-50"
                        style={{ borderColor: "var(--border)" }}>
                  <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full"
                        style={{ background: d.roleKey === "curatorRole" ? "var(--brand-soft)" : "var(--surface-2)",
                                 color: d.roleKey === "curatorRole" ? "var(--brand)" : "var(--ink-2)" }}>
                    {d.roleKey === "curatorRole" ? <Icon.shield size={17} /> : <Icon.user size={17} />}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[0.92rem] font-semibold">{d.name}</span>
                    <span className="block truncate text-[0.78rem]" style={{ color: "var(--ink-muted)" }}>
                      {t(d.roleKey, lang)} · {d.note}
                    </span>
                  </span>
                  <Icon.arrow size={17} className="shrink-0 opacity-40" />
                </button>
              ))}
            </div>

            <details>
              <summary className="cursor-pointer text-[0.85rem] font-medium" style={{ color: "var(--ink-muted)" }}>
                Ввести логин и пароль вручную
              </summary>
              <form onSubmit={submit} className="mt-4 grid gap-3">
                <label className="grid gap-1.5 text-[0.85rem] font-medium">
                  {t("loginField", lang)}
                  <input className="field" value={login} onChange={(e) => setLogin(e.target.value)} autoComplete="username" />
                </label>
                <label className="grid gap-1.5 text-[0.85rem] font-medium">
                  {t("password", lang)}
                  <input className="field" type="password" value={password}
                         onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" />
                </label>
                <button className="btn btn-primary mt-1" disabled={busy || !login}>{t("signIn", lang)}</button>
              </form>
            </details>

            {err && (
              <p className="mt-4 rounded-[var(--radius-s)] px-3 py-2 text-[0.86rem]"
                 style={{ background: "var(--st-overdue-bg)", color: "var(--st-overdue)" }} role="alert">{err}</p>
            )}
          </section>
        </div>

        <footer className="flex flex-wrap items-center justify-between gap-3 border-t py-5 text-[0.8rem]"
                style={{ borderColor: "var(--border)", color: "var(--ink-muted)" }}>
          <span>{t("notDiagnosis", lang)}</span>
          {engine && (
            <span className="inline-flex items-center gap-1.5 whitespace-nowrap">
              <span className="h-1.5 w-1.5 rounded-full"
                    style={{ background: engine === "openai" ? "var(--st-done)" : engine === "offline" ? "var(--st-overdue)" : "var(--st-todo)" }} />
              {engine === "openai" ? "OpenAI structured outputs" : engine === "offline" ? "Сервер недоступен" : t("demoMode", lang)}
            </span>
          )}
        </footer>
      </div>
    </main>
  );
}
