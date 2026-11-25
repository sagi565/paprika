import { useEffect, useSyncExternalStore } from "react";
import { api, type WhatsAppStatus } from "./api";
import { formatPhone } from "./format";

// One copy of the WhatsApp link status for the whole app: the top bar, the billing page
// and the send page all read it, and the connect dialog updates it.
let current: WhatsAppStatus | null = null;
let loading: Promise<WhatsAppStatus> | null = null;
const listeners = new Set<() => void>();

export function setWhatsApp(status: WhatsAppStatus) {
  current = status;
  listeners.forEach((l) => l());
}

export function refreshWhatsApp(): Promise<WhatsAppStatus> {
  loading ??= api
    .whatsapp()
    .then((s) => {
      setWhatsApp(s);
      return s;
    })
    .finally(() => {
      loading = null;
    });
  return loading;
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useWhatsApp(): WhatsAppStatus | null {
  const status = useSyncExternalStore(subscribe, () => current);
  useEffect(() => {
    if (current === null) refreshWhatsApp().catch(() => undefined);
  }, []);
  return status;
}

/** 972501234567 -> 050-1234567 */
export function localPhone(phone: string | null): string {
  if (!phone) return "";
  return formatPhone(phone.startsWith("972") ? `0${phone.slice(3)}` : phone);
}
