export type ChargeStatus = "pending" | "processing" | "charged" | "failed" | "sent";

export interface Me {
  business_name: string;
  grow_mode: "mock" | "live";
}

export interface ClientInput {
  name: string;
  contact_name: string | null;
  phone: string;
  email: string | null;
  invoice_name: string | null;
  tax_id: string | null;
  address: string | null;
  notes: string | null;
  active: boolean;
}

export interface Client extends ClientInput {
  id: number;
  has_card_token: boolean;
  created_at: string;
}

export interface ClientBrief {
  id: number;
  name: string;
  contact_name: string | null;
  phone: string;
  active: boolean;
  has_card_token: boolean;
}

export interface Charge {
  id: number;
  month: string;
  amount: number | null;
  status: ChargeStatus;
  error: string | null;
  invoice_error: string | null;
  has_invoice: boolean;
  invoice_key: string | null;
  grow_transaction_id: string | null;
  charged_at: string | null;
  sent_at: string | null;
  updated_at: string;
  client: ClientBrief;
}

export interface ChargeDetail extends Charge {
  next_unsent_id: number | null;
}

export interface MonthSummary {
  clients: number;
  total_amount: number;
  pending_count: number;
  processing_count: number;
  charged_count: number;
  charged_amount: number;
  failed_count: number;
  sent_count: number;
}

export interface MonthData {
  month: string;
  rows: Charge[];
  summary: MonthSummary;
}

export interface MonthRevenue {
  month: string;
  revenue: number;
  charged_count: number;
}

export interface Dashboard {
  months: MonthRevenue[];
  current: {
    month: string;
    clients: number;
    total_amount: number;
    charged_amount: number;
    charged_count: number;
    pending_count: number;
    failed_count: number;
    to_send_count: number;
    previous_revenue: number;
  };
  year: { year: number; revenue: number; average_month: number };
  clients: { active: number; inactive: number; without_card: number };
  top_clients: { id: number; name: string; revenue: number }[];
}

export interface ImportResult {
  created: number;
  skipped: number;
  errors: string[];
}

export interface CardSaveResult {
  has_card_token: boolean;
  url: string | null;
}

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

export const UNAUTHORIZED_EVENT = "paprika:unauthorized";
/** Fired while waiting for a sleeping server (free hosting) to wake up. */
export const WAKING_EVENT = "paprika:waking";

// Free-tier hosting sleeps when idle; the proxy answers 502/503/504 until it is up.
const WAKE_STATUSES = new Set([502, 503, 504]);
const WAKE_RETRIES = 8;
const WAKE_DELAY_MS = 4000;
const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

function errorMessage(body: unknown, status: number): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail[0]?.msg) {
    return String(detail[0].msg).replace(/^Value error, /, "");
  }
  if (status === 502 || status === 503 || status === 504) return "השרת מתעורר. נסו שוב בעוד חצי דקה.";
  return status >= 500 ? "שגיאת שרת. נסו שוב." : "הבקשה נכשלה";
}

async function request<T>(path: string, init: RequestInit = {}, attempt = 0): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  // Only reads are retried automatically; a POST (e.g. a charge) must never run twice.
  const retryable = (init.method ?? "GET") === "GET" && attempt < WAKE_RETRIES;
  let res: Response;
  try {
    res = await fetch(`/api${path}`, { ...init, headers, credentials: "same-origin" });
  } catch {
    if (!retryable) throw new ApiError("אין חיבור לשרת. בדקו את האינטרנט ונסו שוב.", 0);
    res = new Response(null, { status: 503 });
  }
  if (WAKE_STATUSES.has(res.status) && retryable) {
    window.dispatchEvent(new Event(WAKING_EVENT));
    await sleep(WAKE_DELAY_MS);
    return request<T>(path, init, attempt + 1);
  }
  if (res.status === 401 && !path.startsWith("/auth/login")) {
    window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
  }
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new ApiError(errorMessage(body, res.status), res.status);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

const json = (method: string, body?: unknown): RequestInit => ({
  method,
  body: body === undefined ? undefined : JSON.stringify(body),
});

export const api = {
  me: () => request<Me>("/auth/me"),
  login: (password: string) => request<Me>("/auth/login", json("POST", { password })),
  logout: () => request<void>("/auth/logout", json("POST")),

  dashboard: (months: number) => request<Dashboard>(`/dashboard?months=${months}`),
  month: (month: string) => request<MonthData>(`/months/${month}/charges`),
  chargeAll: (month: string) => request<{ started: number }>(`/months/${month}/charge-all`, json("POST")),
  charge: (id: number) => request<ChargeDetail>(`/charges/${id}`),
  updateAmount: (id: number, amount: number | null) => request<Charge>(`/charges/${id}`, json("PATCH", { amount })),
  chargeOne: (id: number) => request<Charge>(`/charges/${id}/charge`, json("POST")),
  refreshInvoice: (id: number) => request<Charge>(`/charges/${id}/invoice/refresh`, json("POST")),
  markSent: (id: number, sent: boolean) => request<Charge>(`/charges/${id}/sent`, json("POST", { sent })),
  invoiceUrl: (id: number, key?: string | null) => `/api/charges/${id}/invoice.png${key ? `?v=${key}` : ""}`,
  invoiceThumbUrl: (id: number, key?: string | null) =>
    `/api/charges/${id}/invoice-thumb.png${key ? `?v=${key}` : ""}`,

  clients: (q: string, includeInactive: boolean) =>
    request<Client[]>(`/clients?${new URLSearchParams({ q, include_inactive: String(includeInactive) })}`),
  client: (id: number) => request<Client>(`/clients/${id}`),
  createClient: (data: ClientInput) => request<Client>("/clients", json("POST", data)),
  updateClient: (id: number, data: ClientInput) => request<Client>(`/clients/${id}`, json("PUT", data)),
  deleteClient: (id: number) => request<void>(`/clients/${id}`, json("DELETE")),
  importClients: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<ImportResult>("/clients/import", { method: "POST", body: form });
  },
  saveCard: (id: number) => request<CardSaveResult>(`/clients/${id}/card`, json("POST")),
  removeCard: (id: number) => request<CardSaveResult>(`/clients/${id}/card`, json("DELETE")),
};
