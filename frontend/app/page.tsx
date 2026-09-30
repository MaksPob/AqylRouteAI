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
  const [mode, setMode] = useState<"login" | "register">("login");
  const [login, setLogin] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [region, setRegion] = useState("ASTANA");
  const [role, setRole] = useState<"parent" | "curator">("parent");
  const [invite, setInvite] = useState("");
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

  const signUp = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr("");
    setBusy(true);
    try {
      const r = await api.register({
        login, password, display_name: name, region, role,
        invite_code: role === "curator" ? invite : undefined,
      });
      token.set(r.token);
      router.push(r.user.role === "curator" ? "/curator" : "/plan");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Не удалось создать учётную запись");
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
            <h1 className="mb-5 max-w-xl text-balance">
              Маршрут помощи ребёнку — <span style={{ color: "var(--brand)" }}>в одном месте</span>
            </h1>
            <p className="mb-8 max-w-lg text-[1.06rem]" style={{ color: "var(--ink-2)" }}>
              Семьи детей с РАС теряются между здравоохранением, образованием и соцзащитой
              и собирают одни и те же документы по нескольку раз. AqylRoute собирает маршрут
              в один живой план: с ответственными, сроками и видимой точкой, где всё остановилось.
            </p>

            <div className="grid max-w-2xl gap-3 sm:grid-cols-3">
              {[
                { n: "8–12", l: "вопросов адаптивного интервью" },
                { n: "20", l: "услуг в справочнике, 5 этапов" },
                { n: "3", l: "ведомства в одном цифровом досье" },
              ].map((s) => (
                <div key={s.l} className="card px-4 py-4">
                  <div className="text-[1.6rem] font-bold leading-none tracking-tight" style={{ color: "var(--brand)" }}>{s.n}</div>
                  <div className="mt-2 text-[0.82rem] leading-snug text-balance" style={{ color: "var(--ink-muted)" }}>{s.l}</div>
                </div>
              ))}
            </div>
          </section>

          {/* Правая колонка — вход */}
          <section className="card p-5 sm:p-7">
            <div className="mb-5 inline-flex w-full rounded-[var(--radius-s)] p-1"
                 style={{ background: "var(--surface-2)", border: "1px solid var(--border)" }}>
              {(["login", "register"] as const).map((m) => (
                <button key={m} onClick={() => { setMode(m); setErr(""); }} aria-pressed={mode === m}
                        className="flex-1 rounded-[8px] px-3 py-2 text-[0.88rem] font-semibold transition-colors"
                        style={mode === m
                          ? { background: "var(--surface)", color: "var(--ink)", boxShadow: "var(--shadow)" }
                          : { color: "var(--ink-muted)" }}>
                  {t(m === "login" ? "login" : "register", lang)}
                </button>
              ))}
            </div>

            {mode === "register" ? (
              <form onSubmit={signUp} className="grid gap-3.5">
                <label className="grid gap-1.5 text-[0.85rem] font-medium">
                  {t("yourName", lang)}
                  <input className="field" value={name} onChange={(e) => setName(e.target.value)}
                         placeholder="Айгуль Сериковна" autoComplete="name" required />
                </label>

                <label className="grid gap-1.5 text-[0.85rem] font-medium">
                  {t("loginField", lang)}
                  <input className="field" value={login} onChange={(e) => setLogin(e.target.value)}
                         placeholder="aigul" autoComplete="username" required minLength={3} />
                  <span className="text-[0.78rem] font-normal" style={{ color: "var(--ink-muted)" }}>
                    {t("loginHint", lang)}
                  </span>
                </label>

                <label className="grid gap-1.5 text-[0.85rem] font-medium">
                  {t("password", lang)}
                  <input className="field" type="password" value={password}
                         onChange={(e) => setPassword(e.target.value)} autoComplete="new-password"
                         required minLength={6} />
                  <span className="text-[0.78rem] font-normal" style={{ color: "var(--ink-muted)" }}>
                    {t("passwordHint", lang)}
                  </span>
                </label>

                <label className="grid gap-1.5 text-[0.85rem] font-medium">
                  {t("yourRegion", lang)}
                  <select className="field" value={region} onChange={(e) => setRegion(e.target.value)}>
                    <option value="ASTANA">Астана</option>
                    <option value="KARAGANDA">Караганда и Карагандинская область</option>
                    <option value="ALMATY">Алматы</option>
                  </select>
                </label>

                <fieldset className="grid gap-1.5">
                  <legend className="mb-1.5 text-[0.85rem] font-medium">{t("whoAreYou", lang)}</legend>
                  <div className="grid grid-cols-2 gap-2">
                    {(["parent", "curator"] as const).map((r) => (
                      <button key={r} type="button" onClick={() => setRole(r)} aria-pressed={role === r}
                              className="rounded-[var(--radius-s)] border px-3 py-2.5 text-[0.88rem] font-medium transition-colors"
                              style={role === r
                                ? { borderColor: "var(--brand)", background: "var(--brand-soft)", color: "var(--brand-ink)" }
                                : { borderColor: "var(--border-strong)", color: "var(--ink-2)" }}>
                        {t(r === "parent" ? "parentRole" : "curatorRole", lang)}
                      </button>
                    ))}
                  </div>
                </fieldset>

                {role === "curator" && (
                  <label className="grid gap-1.5 text-[0.85rem] font-medium">
                    {t("inviteCode", lang)}
                    <input className="field" value={invite} onChange={(e) => setInvite(e.target.value)}
                           placeholder="KMU-2026" required />
                    <span className="text-[0.78rem] font-normal leading-snug" style={{ color: "var(--ink-muted)" }}>
                      {t("inviteHint", lang)}
                    </span>
                  </label>
                )}

                <button className="btn btn-primary mt-1" disabled={busy || !login || !password || !name}>
                  {t("createAccount", lang)}
                </button>
              </form>
            ) : (
            <>
            <p className="mb-5 text-[0.88rem]" style={{ color: "var(--ink-muted)" }}>
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
            </>
            )}

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
