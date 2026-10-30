import { useLayoutEffect, useRef, useState, type RefObject } from "react";
import type { MonthRevenue } from "../api";
import { formatMoney, formatMoneyCompact, monthLabel, monthShort } from "../format";

const HEIGHT = 280;
// "start" is the right edge in RTL: y-axis labels live there and time runs right→left.
const PAD = { top: 30, bottom: 44, start: 64, end: 8 };
const MAX_BAR = 40;
const RADIUS = 4;

function useWidth(ref: RefObject<HTMLElement>): number {
  const [width, setWidth] = useState(0);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width));
    observer.observe(el);
    return () => observer.disconnect();
  }, [ref]);
  return width;
}

function niceTicks(max: number, count = 4): number[] {
  if (max <= 0) return [0, 1000];
  const raw = max / count;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const norm = raw / mag;
  const step = (norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 2.5 ? 2.5 : norm <= 5 ? 5 : 10) * mag;
  const ticks = [0];
  while (ticks[ticks.length - 1] < max) ticks.push(ticks[ticks.length - 1] + step);
  return ticks;
}

/** Bar with rounded top corners, flat on the baseline. */
function barPath(x: number, yTop: number, w: number, base: number): string {
  const h = base - yTop;
  if (h <= 0) return "";
  const r = Math.min(RADIUS, h, w / 2);
  return `M${x},${base}V${yTop + r}Q${x},${yTop} ${x + r},${yTop}H${x + w - r}Q${x + w},${yTop} ${x + w},${yTop + r}V${base}Z`;
}

export function RevenueChart({ data }: { data: MonthRevenue[] }) {
  const ref = useRef<HTMLDivElement>(null);
  const width = useWidth(ref);
  const [hover, setHover] = useState<number | null>(null);

  const max = Math.max(0, ...data.map((d) => d.revenue));
  const ticks = niceTicks(max);
  const top = ticks[ticks.length - 1];
  const plotW = Math.max(0, width - PAD.start - PAD.end);
  const plotH = HEIGHT - PAD.top - PAD.bottom;
  const base = PAD.top + plotH;
  const slot = data.length ? plotW / data.length : 0;
  const barW = Math.min(MAX_BAR, slot * 0.6);
  const xCenter = (i: number) => width - PAD.start - slot * (i + 0.5);
  const y = (v: number) => PAD.top + plotH * (1 - v / top);

  const current = data.length - 1;
  // Narrow screens: label every other month (always including the current one).
  const labelEvery = slot < 34 ? 2 : 1;
  const closed = data.slice(0, -1).map((d) => d.revenue);
  const best = closed.length ? closed.indexOf(Math.max(...closed)) : -1;
  const labelled = new Set([best, current].filter((i) => i >= 0 && data[i]?.revenue > 0));
  const showLabel = (i: number) => hover === null && labelled.has(i);
  const hovered = hover !== null ? data[hover] : null;

  return (
    <div className="chart" ref={ref} onMouseLeave={() => setHover(null)}>
      {width > 0 && (
        // direction: ltr keeps textAnchor literal (in RTL "start" would mean the right edge).
        <svg width={width} height={HEIGHT} role="img" aria-label="הכנסות לפי חודש" style={{ direction: "ltr" }}>
          {ticks.map((t) => (
            <g key={t}>
              <line
                x1={PAD.end}
                x2={width - PAD.start}
                y1={y(t)}
                y2={y(t)}
                className={t === 0 ? "chart-baseline" : "chart-grid"}
              />
              <text x={width - PAD.start + 10} y={y(t)} className="chart-axis" textAnchor="start" dominantBaseline="middle">
                {t === 0 ? "0" : formatMoneyCompact(t)}
              </text>
            </g>
          ))}

          {data.map((d, i) => {
            const cx = xCenter(i);
            const [, mon] = d.month.split("-");
            const isCurrent = i === current;
            const dim = hover !== null && hover !== i;
            return (
              <g key={d.month}>
                <path
                  d={barPath(cx - barW / 2, y(d.revenue), barW, base)}
                  className={isCurrent ? "chart-bar chart-bar-current" : "chart-bar"}
                  opacity={dim ? 0.35 : 1}
                />
                {showLabel(i) && (
                  <text x={cx} y={y(d.revenue) - 8} className="chart-value" textAnchor="middle">
                    {formatMoneyCompact(d.revenue)}
                  </text>
                )}
                {(current - i) % labelEvery === 0 && (
                  <text x={cx} y={base + 18} className="chart-axis" textAnchor="middle">
                    {monthShort(d.month)}
                  </text>
                )}
                {(i === 0 || mon === "01") && (
                  <text x={cx} y={base + 34} className="chart-axis chart-year" textAnchor="middle">
                    {d.month.slice(0, 4)}
                  </text>
                )}
                {/* Hit target: the whole column, wider than the bar. */}
                <rect
                  x={cx - slot / 2}
                  y={PAD.top}
                  width={slot}
                  height={plotH}
                  fill="transparent"
                  onMouseEnter={() => setHover(i)}
                  onClick={() => setHover(i)}
                />
              </g>
            );
          })}
        </svg>
      )}

      {hovered && hover !== null && (
        <div
          className="chart-tip"
          style={{ left: xCenter(hover), top: Math.min(y(hovered.revenue), base - 4) - 10 }}
          role="status"
        >
          <strong>{monthLabel(hovered.month)}</strong>
          <span className="chart-tip-value">{formatMoney(hovered.revenue)}</span>
          <span className="sub">
            {hovered.charged_count} גנים חויבו{hover === current ? " · החודש עדיין פתוח" : ""}
          </span>
        </div>
      )}
    </div>
  );
}
