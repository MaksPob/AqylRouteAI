"use client";

/** Загрузка и хранение документов семьи: одно место вместо папки с бумагами. */

import { useEffect, useRef, useState } from "react";
import { api, type DocRow } from "@/lib/api";
import { type Lang } from "@/lib/i18n";
import { Banner, Icon } from "./ui";

const SIZE = (b: number) => (b < 1024 * 1024 ? `${Math.round(b / 1024)} КБ` : `${(b / 1024 / 1024).toFixed(1)} МБ`);

export function Documents({ caseId, lang, canUpload = true, compact = false }:
  { caseId: string; lang: Lang; canUpload?: boolean; compact?: boolean }) {
  const [docs, setDocs] = useState<DocRow[] | null>(null);
  const [types, setTypes] = useState<{ value: string; label: string }[]>([]);
  const [docType, setDocType] = useState("FORM_031");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [drag, setDrag] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api.documents(caseId).then(setDocs).catch(() => setDocs([]));
    api.docTypes().then(setTypes).catch(() => setTypes([]));
  }, [caseId]);

  const send = async (files: FileList | null) => {
    if (!files?.length) return;
    setBusy(true); setErr("");
    try {
      for (const f of Array.from(files)) await api.uploadDocument(caseId, f, docType);
      setDocs(await api.documents(caseId));
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Не удалось загрузить файл");
    } finally {
      setBusy(false);
      if (input.current) input.current.value = "";
    }
  };

  const remove = async (id: number) => {
    setBusy(true);
    try { await api.deleteDocument(id); setDocs(await api.documents(caseId)); }
    catch (e) { setErr(e instanceof Error ? e.message : "Не удалось удалить"); }
    finally { setBusy(false); }
  };

  const label = (v: string) => types.find((t) => t.value === v)?.label ?? v;

  return (
    <div>
      {canUpload && (
        <>
          <label className="mb-2 grid gap-1.5 text-[0.84rem] font-medium">
            Что за документ
            <select className="field !py-2" value={docType} onChange={(e) => setDocType(e.target.value)}>
              {types.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
            </select>
          </label>

          <div
            onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
            onDragLeave={() => setDrag(false)}
            onDrop={(e) => { e.preventDefault(); setDrag(false); send(e.dataTransfer.files); }}
            className="mb-3 rounded-[var(--radius-s)] border-2 border-dashed px-4 py-6 text-center transition-colors"
            style={{ borderColor: drag ? "var(--brand)" : "var(--border-strong)",
                     background: drag ? "var(--brand-soft)" : "transparent" }}>
            <span className="mx-auto mb-2 flex h-10 w-10 items-center justify-center rounded-full"
                  style={{ background: "var(--surface-2)", color: "var(--ink-2)" }}>
              <Icon.doc size={19} />
            </span>
            <p className="mb-3 text-[0.88rem]" style={{ color: "var(--ink-2)" }}>
              Сфотографируйте документ или выберите файл
            </p>
            <input ref={input} type="file" className="sr-only" id={`up-${caseId}`} disabled={busy}
                   accept="application/pdf,image/jpeg,image/png,image/heic,image/webp"
                   multiple onChange={(e) => send(e.target.files)} />
            <label htmlFor={`up-${caseId}`} className="btn btn-ghost cursor-pointer !py-2 !text-[0.88rem]">
              {busy ? "Загружаем…" : "Выбрать файл"}
            </label>
            <p className="mt-2.5 text-[0.76rem]" style={{ color: "var(--ink-muted)" }}>
              PDF или фотография, до 10 МБ
            </p>
          </div>
        </>
      )}

      {err && <div className="mb-3"><Banner tone="warn">{err}</Banner></div>}

      {docs === null ? (
        <p className="text-[0.86rem]" style={{ color: "var(--ink-muted)" }}>Загрузка…</p>
      ) : docs.length === 0 ? (
        <p className="text-[0.86rem]" style={{ color: "var(--ink-muted)" }}>
          {canUpload ? "Пока ничего не загружено. Документы здесь не потеряются и не придётся собирать их заново."
                     : "Семья пока не загрузила документы."}
        </p>
      ) : (
        <ul className="grid gap-2">
          {docs.map((d) => (
            <li key={d.id} className="flex items-center gap-3 rounded-[var(--radius-s)] border px-3 py-2.5"
                style={{ borderColor: "var(--border)" }}>
              <span className="shrink-0" style={{ color: "var(--st-done)" }}><Icon.check size={16} /></span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[0.89rem] font-medium">{label(d.doc_type)}</span>
                <span className="block truncate text-[0.77rem]" style={{ color: "var(--ink-muted)" }}>
                  {d.original_name} · {SIZE(d.size)}
                  {!compact && ` · ${new Date(d.created_at).toLocaleDateString("ru-RU")}`}
                  {!canUpload && ` · ${d.uploaded_by}`}
                </span>
              </span>
              <a href={api.fileUrl(d.id)} target="_blank" rel="noreferrer"
                 className="btn btn-quiet !px-2 !text-[0.8rem]" title="Открыть">
                <Icon.arrow size={15} />
              </a>
              {canUpload && (
                <button onClick={() => remove(d.id)} disabled={busy}
                        className="btn btn-quiet !px-2" title="Удалить"
                        style={{ color: "var(--st-overdue)" }}>
                  <Icon.minus size={15} />
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
