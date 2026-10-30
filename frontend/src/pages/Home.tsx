import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type Dashboard } from "../api";
import { Chevron } from "../components/Chevron";
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

  if (!data) return <p className="empty">טוען…</p>;

  const { current, year, clients } = data;
  const progress = current.clients ? current.charged_count / current.clients : 0;
  const topMax = Math.max(1, ...data.top_clients.map((t) => t.revenue));
  const hasRevenue = data.months.some((m) => m.revenue > 0);

  return (
    <div className="stack-lg">
      <div className="page-head">
        <div>
          <p className="eyebrow">{today}</p>
          <h1>{greeting()}</h1>
        </div>
      </div>

      <section className="nav-cards">
        <Link to="/billing" className="nav-card">
          <div className="nav-card-head">
            <span className="eyebrow">{monthLabel(current.month)}</span>
            <span className="nav-card-go">
              לחיובים <Chevron direction="left" />
            </span>
          </div>
          <h2>חיובים</h2>
          <p className="nav-card-big">
            {current.charged_count} מתוך {current.clients} חויבו
          </p>
          <div className="progress" aria-hidden>
            <span style={{ width: `${progress * 100}%` }} />
          </div>
          <ul className="nav-card-facts">
            <li>{current.pending_count} ממתינים לחיוב</li>
            {current.failed_count > 0 && <li className="tone-bad">{current.failed_count} נכשלו</li>}
            <li>{current.to_send_count} חשבוניות לשליחה</li>
          </ul>
        </Link>

        <Link to="/clients" className="nav-card">
          <div className="nav-card-head">
            <span className="eyebrow">לקוחות</span>
            <span className="nav-card-go">
              לגנים <Chevron direction="left" />
            </span>
          </div>
          <h2>גנים</h2>
          <p className="nav-card-big">{clients.active} גנים פעילים</p>
          <ul className="nav-card-facts">
            <li className={clients.without_card ? "tone-warn" : undefined}>
              {clients.without_card ? `${clients.without_card} בלי כרטיס שמור` : "לכל הגנים יש כרטיס שמור"}
            </li>
            {clients.inactive > 0 && <li>{clients.inactive} לא פעילים</li>}
          </ul>
        </Link>
      </section>

      <section className="stats">
        <Stat
          label={`הכנסות ${monthLabel(current.month)}`}
          value={formatMoneyWhole(current.charged_amount)}
          sub={`מתוך ${formatMoneyWhole(current.total_amount)} לחיוב`}
        />
        <Stat
          label={`הכנסות ${monthLabel(shiftMonth(current.month, -1))}`}
          value={formatMoneyWhole(current.previous_revenue)}
          sub="החודש הקודם"
        />
        <Stat label={`הכנסות ${year.year}`} value={formatMoneyWhole(year.revenue)} sub="מתחילת השנה" />
        <Stat label="ממוצע לחודש" value={formatMoneyWhole(year.average_month)} sub={`ב-${year.year}`} />
      </section>

      <section className="dash-grid">
        <div className="card chart-card">
          <div className="card-head">
            <div>
              <h2>הכנסות לפי חודש</h2>
              <p className="sub">חיובים שעברו בהצלחה</p>
            </div>
            <div className="chips">
              {RANGES.map((r) => (
                <button key={r} className={range === r ? "chip chip-on" : "chip"} onClick={() => setRange(r)}>
                  {r} חודשים
                </button>
              ))}
              <span className="chips-sep" />
              <button className={view === "chart" ? "chip chip-on" : "chip"} onClick={() => setView("chart")}>
                גרף
              </button>
              <button className={view === "table" ? "chip chip-on" : "chip"} onClick={() => setView("table")}>
                טבלה
              </button>
            </div>
          </div>
          {!hasRevenue ? (
            <p className="empty">עוד אין הכנסות להצגה</p>
          ) : view === "chart" ? (
            <RevenueChart data={data.months} />
          ) : (
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
                    <td>{m.charged_count}</td>
                    <td className="amount">{formatMoney(m.revenue)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        <div className="card top-card">
          <div className="card-head">
            <div>
              <h2>הגנים המובילים</h2>
              <p className="sub">הכנסות ב-{year.year}</p>
            </div>
          </div>
          {data.top_clients.length === 0 ? (
            <p className="empty">אין עדיין נתונים</p>
          ) : (
            <ol className="top-list">
              {data.top_clients.map((t) => (
                <li key={t.id}>
                  <div className="top-row">
                    <span className="name">{t.name}</span>
                    <span className="amount">{formatMoneyWhole(t.revenue)}</span>
                  </div>
                  <div className="top-bar" aria-hidden>
                    <span style={{ width: `${(t.revenue / topMax) * 100}%` }} />
                  </div>
                </li>
              ))}
            </ol>
          )}
        </div>
      </section>
    </div>
  );
}

function Stat({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <div className="stat">
      <span className="stat-label">{label}</span>
      <span className="stat-value">{value}</span>
      <span className="stat-sub">{sub}</span>
    </div>
  );
}
