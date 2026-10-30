import type { ChargeStatus } from "./api";

const currency = new Intl.NumberFormat("he-IL", { style: "currency", currency: "ILS", maximumFractionDigits: 2 });

const compactCurrency = new Intl.NumberFormat("he-IL", {
  style: "currency",
  currency: "ILS",
  notation: "compact",
  maximumFractionDigits: 1,
});
const wholeCurrency = new Intl.NumberFormat("he-IL", { style: "currency", currency: "ILS", maximumFractionDigits: 0 });

export const formatMoney = (n: number) => currency.format(n);
export const formatMoneyCompact = (n: number) => compactCurrency.format(n);
export const formatMoneyWhole = (n: number) => wholeCurrency.format(n);

/** "30.10 · 14:32" */
export function formatShortDateTime(iso: string): string {
  const d = new Date(iso);
  const date = d.toLocaleDateString("he-IL", { day: "2-digit", month: "2-digit" });
  const time = d.toLocaleTimeString("he-IL", { hour: "2-digit", minute: "2-digit" });
  return `${date} · ${time}`;
}

export function monthShort(month: string): string {
  const [y, m] = month.split("-").map(Number);
  return new Date(y, m - 1, 1).toLocaleDateString("he-IL", { month: "short" });
}

export function formatPhone(phone: string): string {
  return phone.length === 10 ? `${phone.slice(0, 3)}-${phone.slice(3)}` : phone;
}

/** 0501234567 → 972501234567, for wa.me links. */
export function whatsappNumber(phone: string): string {
  return `972${phone.replace(/^0/, "")}`;
}

export function currentMonth(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

export function shiftMonth(month: string, delta: number): string {
  const [y, m] = month.split("-").map(Number);
  const d = new Date(y, m - 1 + delta, 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

export function monthLabel(month: string): string {
  const [y, m] = month.split("-").map(Number);
  return new Date(y, m - 1, 1).toLocaleDateString("he-IL", { month: "long", year: "numeric" });
}

export const STATUS_LABEL: Record<ChargeStatus, string> = {
  pending: "ממתין",
  processing: "מחייב…",
  charged: "חויב",
  failed: "נכשל",
  sent: "נשלח",
};
