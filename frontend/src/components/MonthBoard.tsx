import type { CSSProperties, ReactNode } from "react";

/** Where a kindergarten stands this month, from not charged yet to invoice sent. */
export type StripStatus = "sent" | "charged" | "processing" | "failed" | "pending";

export const STRIP_ORDER: StripStatus[] = ["sent", "charged", "processing", "failed", "pending"];

export const STRIP_LABEL: Record<StripStatus, string> = {
  sent: "נשלחו",
  charged: "לשליחה",
  processing: "בחיוב",
  failed: "נכשלו",
  pending: "ממתינים",
};

export interface StripCell {
  key: string | number;
  status: StripStatus;
  name?: string;
}

/** Builds anonymous cells from counts (the dashboard knows totals, not names). */
export function cellsFromCounts(counts: Partial<Record<StripStatus, number>>): StripCell[] {
  return STRIP_ORDER.flatMap((status) =>
    Array.from({ length: Math.max(0, counts[status] ?? 0) }, (_, i) => ({ key: `${status}-${i}`, status })),
  );
}

function countCells(cells: StripCell[]): Record<StripStatus, number> {
  const counts = { sent: 0, charged: 0, processing: 0, failed: 0, pending: 0 };
  cells.forEach((c) => counts[c.status]++);
  return counts;
}

/** One cell per kindergarten, grouped by status: the month fills with green as it gets done. */
export function MonthStrip({ cells }: { cells: StripCell[] }) {
  const sorted = [...cells].sort((a, b) => STRIP_ORDER.indexOf(a.status) - STRIP_ORDER.indexOf(b.status));
  const counts = countCells(cells);
  const summary = STRIP_ORDER.filter((s) => counts[s])
    .map((s) => `${STRIP_LABEL[s]} ${counts[s]}`)
    .join(", ");
  return (
    // --n lets the gap shrink with the cell count, so 100+ kindergartens still fit a phone.
    <div className="strip" role="img" aria-label={summary} style={{ "--n": sorted.length } as CSSProperties}>
      {sorted.map((c) => (
        <span
          key={c.key}
          className={`strip-cell st-${c.status}`}
          title={c.name ? `${c.name} · ${STRIP_LABEL[c.status]}` : undefined}
        />
      ))}
    </div>
  );
}

export function StripLegend({ cells }: { cells: StripCell[] }) {
  const counts = countCells(cells);
  return (
    <ul className="legend">
      {STRIP_ORDER.filter((s) => counts[s] > 0).map((s) => (
        <li key={s}>
          <span className={`dot st-${s}`} aria-hidden />
          {STRIP_LABEL[s]}
          <span className="legend-count">{counts[s]}</span>
        </li>
      ))}
    </ul>
  );
}

export interface Figure {
  label: string;
  value: string;
  tone?: "bad" | "ok";
}

interface Props {
  title?: string;
  action?: ReactNode;
  /** Money collected this month, and the month's total to collect. */
  collected: string;
  total: string;
  figures: Figure[];
  cells: StripCell[];
  empty?: ReactNode;
}

export function MonthBoard({ title, action, collected, total, figures, cells, empty }: Props) {
  return (
    <section className="board" aria-label={title ?? "מצב החודש"}>
      {(title || action) && (
        <div className="board-head">
          {title && <h2>{title}</h2>}
          {action}
        </div>
      )}
      <div className="board-figures">
        <div className="figure figure-main">
          <span className="figure-label">נגבו</span>
          <span className="figure-value">{collected}</span>
          <span className="figure-sub">מתוך {total}</span>
        </div>
        {figures.map((f) => (
          <div key={f.label} className="figure">
            <span className="figure-label">{f.label}</span>
            <span className={f.tone ? `figure-value tone-${f.tone}` : "figure-value"}>{f.value}</span>
          </div>
        ))}
      </div>
      {cells.length === 0 ? (
        <div className="strip-empty">{empty ?? "אין גנים בחודש הזה"}</div>
      ) : (
        <>
          <MonthStrip cells={cells} />
          <StripLegend cells={cells} />
        </>
      )}
    </section>
  );
}
