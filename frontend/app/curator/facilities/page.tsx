"use client";

/**
 * Справочник организаций: ПМПК, МСЭК, центры и их контакты.
 *
 * Ведёт куратор. Адреса и телефоны меняются, а ПМПК и МСЭК различаются
 * по районам — держать это в коде нельзя, иначе родитель придёт не туда.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { api, type Facility, token } from "@/lib/api";
import { localName, REGION_NAMES, t } from "@/lib/i18n";
import { Banner, Header, Icon, Spinner, useLang } from "@/components/ui";

const REGIONS = ["ASTANA", "KARAGANDA", "ALMATY"] as const;

const EMPTY: Partial<Facility> = {
  name: "", service_id: "", region: "ASTANA", district: "", address: "",
  phone: "", contact_person: "", email: "", portal: "", hours: "", note: "", is_active: true,
};

export default function FacilitiesPage() {
  const [lang, setLang] = useLang();
  const router = useRouter();
  const [rows, setRows] = useState<Facility[] | null>(null);
  const [services, setServices] = useState<{ id: string; title: Record<string, string>; stage: string }[]>([]);
  const [region, setRegion] = useState<string>("");
  const [draft, setDraft] = useState<Partial<Facility> | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const load = useCallback(async () => {
    setRows(await api.facilities({ include_inactive: true }));
  }, []);

  useEffect(() => {
    if (!token.get()) { router.replace("/"); return; }
    api.me().then((u) => {
      if (u.role !== "curator") { router.replace("/plan"); return; }
      load();
      api.catalog().then((c) => setServices(c.services));
    }).catch(() => router.replace("/"));
  }, [load, router]);

  const serviceName = (id: string) =>
    services.find((s) => s.id === id)?.title?.[lang] ?? services.find((s) => s.id === id)?.title?.ru ?? id;

  const shown = useMemo(
    () => (rows ?? []).filter((r) => !region || r.region === region),
    [rows, region]);

  const grouped = useMemo(() => {
    const m = new Map<string, Facility[]>();
    for (const f of shown) {
      const k = `${f.region}|${f.service_id}`;
      m.set(k, [...(m.get(k) ?? []), f]);
    }
    return [...m.entries()].sort((a, b) => a[0].localeCompare(b[0]));
  }, [shown]);

  const save = async () => {
    if (!draft) return;
    setBusy(true); setErr("");
    try {
      if (draft.id) await api.updateFacility(draft.id, draft);
      else await api.createFacility(draft);
      setDraft(null);
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Не удалось сохранить");
    } finally { setBusy(false); }
  };

  const remove = async (f: Facility) => {
    setBusy(true);
    try { await api.deleteFacility(f.id); await load(); }
    catch (e) { setErr(e instanceof Error ? e.message : "Не удалось удалить"); }
    finally { setBusy(false); }
  };

  if (!rows) return <Spinner label={t("loading", lang)} />;

  const field = (key: keyof Facility, label: string, placeholder = "", wide = false) => (
    <label className={`grid gap-1.5 text-[0.84rem] font-medium ${wide ? "sm:col-span-2" : ""}`}>
      {label}
      <input className="field !py-2 !text-[0.92rem]" placeholder={placeholder}
             value={(draft?.[key] as string) ?? ""}
             onChange={(e) => setDraft((d) => ({ ...d!, [key]: e.target.value }))} />
    </label>
  );

  return (
    <main className="min-h-screen pb-16">
      <Header lang={lang} setLang={setLang} title="Справочник организаций"
              subtitle={`${rows.length} записей · ПМПК, МСЭК, центры`}
              back={() => router.push("/curator")} />

      <div className="mx-auto max-w-5xl px-4 pt-5 sm:px-6 sm:pt-7">
        <div className="mb-5 flex flex-wrap items-center gap-2">
          <button className="btn btn-primary" onClick={() => setDraft({ ...EMPTY })}>
            <Icon.pin size={16} /> Добавить организацию
          </button>
          <div className="flex-1" />
          <select className="field !w-auto !py-2 !text-[0.88rem]" value={region}
                  onChange={(e) => setRegion(e.target.value)} aria-label="Регион">
            <option value="">Все регионы</option>
            {REGIONS.map((r) => <option key={r} value={r}>{localName(REGION_NAMES, r, lang)}</option>)}
          </select>
        </div>

        {err && <div className="mb-4"><Banner tone="warn">{err}</Banner></div>}

        {/* форма */}
        {draft && (
          <section className="card mb-6 p-5" style={{ borderColor: "var(--brand)" }}>
            <h3 className="mb-4">{draft.id ? "Изменить организацию" : "Новая организация"}</h3>
            <div className="grid gap-3 sm:grid-cols-2">
              {field("name", "Название", "ПМПК №2 Октябрьского района", true)}

              <label className="grid gap-1.5 text-[0.84rem] font-medium">
                Для какой услуги
                <select className="field !py-2 !text-[0.92rem]" value={draft.service_id ?? ""}
                        onChange={(e) => setDraft({ ...draft, service_id: e.target.value })}>
                  <option value="">— выберите —</option>
                  {services.map((s) => (
                    <option key={s.id} value={s.id}>{s.title?.[lang] ?? s.title?.ru ?? s.id}</option>
                  ))}
                </select>
              </label>

              <label className="grid gap-1.5 text-[0.84rem] font-medium">
                Регион
                <select className="field !py-2 !text-[0.92rem]" value={draft.region ?? "ASTANA"}
                        onChange={(e) => setDraft({ ...draft, region: e.target.value })}>
                  {REGIONS.map((r) => <option key={r} value={r}>{localName(REGION_NAMES, r, lang)}</option>)}
                </select>
              </label>

              {field("district", "Район", "Октябрьский район")}
              {field("phone", "Телефон", "+7 7212 41-25-60")}
              {field("address", "Адрес", "ул. Ерубаева, 42", true)}
              {field("contact_person", "Контактное лицо", "Сауле Мукановна, секретарь")}
              {field("email", "Электронная почта", "pmpk2@example.kz")}
              {field("portal", "Сайт или портал", "birge.astana.kz")}
              {field("hours", "Часы приёма", "Пн–Пт 09:00–17:00")}
              {field("note", "Примечание для родителя", "Запись за 2 недели", true)}

              <label className="flex items-center gap-2.5 text-[0.88rem] sm:col-span-2">
                <input type="checkbox" className="h-4 w-4" checked={draft.is_active ?? true}
                       onChange={(e) => setDraft({ ...draft, is_active: e.target.checked })} />
                Организация работает и показывается родителям
              </label>
            </div>

            <div className="mt-4 flex flex-wrap gap-2">
              <button className="btn btn-primary" disabled={busy || !draft.name || !draft.service_id}
                      onClick={save}>{t("save", lang)}</button>
              <button className="btn btn-quiet" onClick={() => { setDraft(null); setErr(""); }}>
                {t("cancel", lang)}
              </button>
            </div>
          </section>
        )}

        {/* список */}
        {grouped.length === 0 ? (
          <div className="card p-10 text-center" style={{ color: "var(--ink-muted)" }}>
            Организаций пока нет. Добавьте ПМПК, МСЭК и центры вашего региона —
            родители увидят их адреса и телефоны прямо в плане.
          </div>
        ) : (
          <div className="grid gap-5">
            {grouped.map(([key, list]) => {
              const [reg, sid] = key.split("|");
              return (
                <section key={key}>
                  <h3 className="mb-2 text-[0.95rem]">
                    {serviceName(sid)}
                    <span className="ml-2 text-[0.82rem] font-normal" style={{ color: "var(--ink-muted)" }}>
                      {localName(REGION_NAMES, reg, lang)}
                    </span>
                  </h3>
                  <ul className="grid gap-2">
                    {list.map((f) => (
                      <li key={f.id} className="card p-4" style={f.is_active ? undefined : { opacity: 0.55 }}>
                        <div className="flex flex-wrap items-start gap-3">
                          <div className="min-w-0 flex-1">
                            <div className="mb-1 flex flex-wrap items-center gap-2">
                              <span className="font-semibold">{f.name}</span>
                              {f.district && (
                                <span className="rounded-full px-2 py-0.5 text-[0.75rem]"
                                      style={{ background: "var(--surface-2)", color: "var(--ink-2)" }}>
                                  {f.district}
                                </span>
                              )}
                              {!f.is_active && (
                                <span className="rounded-full px-2 py-0.5 text-[0.75rem]"
                                      style={{ background: "var(--st-cancelled-bg)", color: "var(--st-cancelled)" }}>
                                  не показывается
                                </span>
                              )}
                            </div>
                            <div className="grid gap-0.5 text-[0.85rem]" style={{ color: "var(--ink-2)" }}>
                              {f.address && <span>{f.address}</span>}
                              {f.phone && <span>{f.phone}{f.contact_person && ` · ${f.contact_person}`}</span>}
                              {f.hours && <span style={{ color: "var(--ink-muted)" }}>{f.hours}</span>}
                              {f.portal && <span style={{ color: "var(--brand)" }}>{f.portal}</span>}
                              {f.note && <span style={{ color: "var(--ink-muted)" }}>{f.note}</span>}
                            </div>
                          </div>
                          <div className="flex shrink-0 gap-1">
                            <button className="btn btn-quiet !px-2.5" title={t("editStep", lang)}
                                    onClick={() => setDraft({ ...f })}>
                              <Icon.edit size={16} />
                            </button>
                            <button className="btn btn-quiet !px-2.5" title="Удалить" disabled={busy}
                                    style={{ color: "var(--st-overdue)" }} onClick={() => remove(f)}>
                              <Icon.minus size={16} />
                            </button>
                          </div>
                        </div>
                      </li>
                    ))}
                  </ul>
                </section>
              );
            })}
          </div>
        )}
      </div>
    </main>
  );
}
