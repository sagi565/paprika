import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type Dashboard } from "../api";
import { Chevron } from "../components/Chevron";
import { CardIcon, CheckIcon } from "../components/icons";
import { cellsFromCounts, MonthBoard } from "../components/MonthBoard";
import { RevenueChart } from "../components/RevenueChart";
import { toastError } from "../components/toast";
import { formatMoney, formatMoneyWhole, monthLabel, shiftMonth } from "../format";

const RANGES = [6, 12, 24];

function greeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) return "בוקר טוב";
  if (hour < 17) return "צהריים טובים";
  return "ערב טוב";
}

export function Home() {
  const [range, setRange] = useState(12);
  const [view, setView] = useState<"chart" | "table">("chart");
  const [data, setData] = useState<Dashboard | null>(null);

  useEffect(() => {
    api.dashboard(range).then(setData, toastError);
  }, [range]);

  const today = new Date().toLocaleDateString("he-IL", { weekday: "long", day: "numeric", month: "long" });

  if (!data) return <HomeSkeleton />;

  const { current, year, clients } = data;
  const sent = Math.max(0, current.charged_count - current.to_send_count);
  const cells = cellsFromCounts({
    sent,
    charged: current.to_send_count,
    failed: current.failed_count,
    pending: current.pending_count,
  });
  const topMax = Math.max(1, ...data.top_clients.map((t) => t.revenue));
  const hasRevenue = data.months.some((m) => m.revenue > 0);

  return (
    <div className="stack">
      <div className="page-head">
        <div className="page-title">
          <h1>{greeting()}</h1>
          <p className="page-sub">{today}</p>
        </div>
      </div>

      <div className="home-top">
        <MonthBoard
          title={monthLabel(current.month)}
          action={
            <Link to="/billing" className="btn btn-primary">
              לחיובים
              <Chevron direction="left" />
            </Link>
          }
          collected={formatMoneyWhole(current.charged_amount)}
          total={formatMoneyWhole(current.total_amount)}
          figures={[
            { label: "לשליחה", value: String(current.to_send_count) },
            { label: "נכשלו", value: String(current.failed_count), tone: current.failed_count ? "bad" : undefined },
          ]}
          cells={cells}
          empty={
            <>
              עוד אין גנים לחיוב. <Link to="/clients">הוספת גנים</Link>
            </>
          }
        />

        <section className="panel clients-panel" aria-label="גנים">
          <h2>גנים</h2>
          {clients.without_card ? (
            <>
              <div className="clients-todo">
                <span className="clients-todo-icon">
                  <CardIcon size={20} />
                </span>
                <div>
                  <strong>
                    {clients.without_card === 1 ? "גן אחד בלי כרטיס שמור" : `${clients.without_card} גנים בלי כרטיס שמור`}
                  </strong>
                  <p>בלי כרטיס שמור אי אפשר לחייב אוטומטית.</p>
                </div>
              </div>
              <Link to="/clients?nocard=1" className="btn">
                מילוי כרטיס
                <Chevron direction="left" />
              </Link>
            </>
          ) : (
            <>
              <div className="clients-todo clients-todo-ok">
                <span className="clients-todo-icon">
                  <CheckIcon size={20} />
                </span>
                <div>
                  <strong>לכל הגנים יש כרטיס שמור</strong>
                  <p>אפשר לחייב את כולם בלחיצה.</p>
                </div>
              </div>
              <Link to="/clients" className="btn">
                לרשימת הגנים
                <Chevron direction="left" />
              </Link>
            </>
          )}
          <p className="clients-meta">
            {clients.active} פעילים{clients.inactive > 0 && ` · ${clients.inactive} לא פעילים`}
          </p>
        </section>
      </div>

      <div className="dash-grid">
        <section className="panel chart-card">
          <div className="panel-head">
            <h2>הכנסות לפי חודש</h2>
            <div className="seg-group">
              <div className="seg" role="group" aria-label="טווח">
                {RANGES.map((r) => (
                  <button key={r} className={range === r ? "seg-on" : undefined} aria-pressed={range === r} onClick={() => setRange(r)}>
                    {r} חודשים
                  </button>
                ))}
              </div>
              <div className="seg" role="group" aria-label="תצוגה">
                <button className={view === "chart" ? "seg-on" : undefined} aria-pressed={view === "chart"} onClick={() => setView("chart")}>
                  גרף
                </button>
                <button className={view === "table" ? "seg-on" : undefined} aria-pressed={view === "table"} onClick={() => setView("table")}>
                  טבלה
                </button>
              </div>
            </div>
          </div>

          <dl className="figures-row">
            <div>
              <dt>{monthLabel(shiftMonth(current.month, -1))}</dt>
              <dd>{formatMoneyWhole(current.previous_revenue)}</dd>
            </div>
            <div>
              <dt>מתחילת {year.year}</dt>
              <dd>{formatMoneyWhole(year.revenue)}</dd>
            </div>
            <div>
              <dt>ממוצע לחודש</dt>
              <dd>{formatMoneyWhole(year.average_month)}</dd>
            </div>
          </dl>

          {!hasRevenue ? (
            <p className="empty">כשהחיובים הראשונים יעברו, ההכנסות של כל חודש יופיעו כאן.</p>
          ) : view === "chart" ? (
            <RevenueChart data={data.months} />
          ) : (
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>חודש</th>
                    <th>גנים שחויבו</th>
                    <th>הכנסות</th>
                  </tr>
                </thead>
                <tbody>
                  {[...data.months].reverse().map((m) => (
                    <tr key={m.month}>
                      <td>{monthLabel(m.month)}</td>
                      <td className="num">{m.charged_count}</td>
                      <td className="num strong">{formatMoney(m.revenue)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <section className="panel top-card">
          <div className="panel-head">
            <h2>הגנים המובילים</h2>
            <span className="panel-meta">{year.year}</span>
          </div>
          {data.top_clients.length === 0 ? (
            <p className="empty">אחרי החיובים הראשונים יופיעו כאן הגנים עם ההכנסות הגבוהות בשנה.</p>
          ) : (
            <ol className="top-list">
              {data.top_clients.map((t, i) => (
                <li key={t.id}>
                  <span className="top-rank">{i + 1}</span>
                  <div className="top-body">
                    <div className="top-row">
                      <span className="top-name">{t.name}</span>
                      <span className="num strong">{formatMoneyWhole(t.revenue)}</span>
                    </div>
                    <div className="top-bar" aria-hidden>
                      <span style={{ width: `${(t.revenue / topMax) * 100}%` }} />
                    </div>
                  </div>
                </li>
              ))}
            </ol>
          )}
        </section>
      </div>
    </div>
  );
}

function HomeSkeleton() {
  return (
    <div className="stack" aria-busy="true" aria-label="טוען">
      <div className="sk sk-title" />
      <div className="home-top">
        <div className="sk sk-board" />
        <div className="sk sk-board" />
      </div>
      <div className="sk sk-chart" />
    </div>
  );
}
