"use client";

/**
 * Отслеживание состояния родителя во времени.
 *
 * Разовый балл мало что даёт: важна динамика — стало легче или тяжелее.
 * Шкала PHQ-9 идёт от 0 до 27, поэтому столбики рисуем от общей базы,
 * а не от максимума в выборке, иначе два близких замера выглядят как обвал.
 */

import type { PhqPoint } from "@/lib/api";
import { Icon } from "./ui";

const MAX = 27;

const BANDS = [
  { upto: 4,  label: "Норма",            color: "var(--st-done)" },
  { upto: 9,  label: "Лёгкая",           color: "var(--st-todo)" },
  { upto: 14, label: "Умеренная",        color: "var(--st-blocked)" },
  { upto: 19, label: "Умеренно тяжёлая", color: "var(--st-overdue)" },
  { upto: 27, label: "Тяжёлая",          color: "var(--st-overdue)" },
];

const band = (score: number) => BANDS.find((b) => score <= b.upto) ?? BANDS[BANDS.length - 1];

export function WellbeingTrack({ history, compact = false }: { history: PhqPoint[]; compact?: boolean }) {
  if (!history?.length) {
    return (
      <p className="text-[0.86rem]" style={{ color: "var(--ink-muted)" }}>
        Опрос о самочувствии ещё не проходили.
      </p>
    );
  }

  const last = history[history.length - 1];
  const prev = history.length > 1 ? history[history.length - 2] : null;
  const delta = prev ? last.score - prev.score : null;
  const b = band(last.score);

  // Показываем не больше восьми последних замеров — дальше столбики нечитаемы
  const points = history.slice(-8);

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="text-[1.9rem] font-bold leading-none tracking-tight" style={{ color: b.color }}>
          {last.score}
        </span>
        <span className="text-[0.85rem]" style={{ color: "var(--ink-muted)" }}>из {MAX}</span>
        <span className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[0.78rem] font-semibold"
              style={{ background: "var(--surface-2)", color: b.color }}>
          {b.label}
        </span>
        {delta !== null && delta !== 0 && (
          <span className="inline-flex items-center gap-1 text-[0.82rem] font-medium"
                style={{ color: delta < 0 ? "var(--st-done)" : "var(--st-overdue)" }}>
            {delta < 0 ? "стало легче" : "стало тяжелее"} на {Math.abs(delta)}
          </span>
        )}
      </div>

      {points.length > 1 && (
        <>
          <div className="mb-1.5 flex items-end gap-1.5" style={{ height: compact ? 44 : 64 }}
               role="img" aria-label={`Динамика: ${points.map((p) => p.score).join(", ")} из ${MAX}`}>
            {points.map((p, i) => {
              const pb = band(p.score);
              const isLast = i === points.length - 1;
              return (
                <span key={p.created_at + i} className="flex-1"
                      title={`${p.score} из ${MAX} · ${new Date(p.created_at).toLocaleDateString("ru-RU")}`}
                      style={{
                        height: `${Math.max(6, (p.score / MAX) * 100)}%`,
                        background: isLast ? pb.color : `color-mix(in srgb, ${pb.color} 45%, transparent)`,
                        borderRadius: "4px 4px 2px 2px",
                        minWidth: 10,
                      }} />
              );
            })}
          </div>
          <div className="flex justify-between text-[0.73rem]" style={{ color: "var(--ink-muted)" }}>
            <span>{new Date(points[0].created_at).toLocaleDateString("ru-RU", { day: "numeric", month: "short" })}</span>
            <span>{new Date(last.created_at).toLocaleDateString("ru-RU", { day: "numeric", month: "short" })}</span>
          </div>
        </>
      )}

      {last.crisis_flag === 1 && (
        <p className="mt-3 rounded-[var(--radius-s)] px-3 py-2.5 text-[0.84rem]"
           style={{ background: "var(--st-overdue-bg)", color: "var(--st-overdue)" }}>
          <Icon.alert size={14} /> Отмечен пункт 9 — требуется внимание специалиста.
          Телефон доверия: 150, круглосуточно и бесплатно.
        </p>
      )}

      <p className="mt-3 text-[0.75rem]" style={{ color: "var(--ink-muted)" }}>
        PHQ-9 — скрининговый инструмент, не диагноз. Результат интерпретирует специалист.
      </p>
    </div>
  );
}
