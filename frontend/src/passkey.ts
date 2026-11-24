// Log in with the device's fingerprint or face check (WebAuthn passkeys).
// The server sends options as JSON with base64url strings; the browser API wants bytes, and the
// credential it returns goes back as JSON. Both conversions happen here.
import { api, ApiError, type Me, type Passkey } from "./api";

type Json = Record<string, any>;

const DEVICE_KEY = "paprika:passkey"; // credential id of this device's passkey
const DECLINED_KEY = "paprika:passkey-declined"; // "not now" on the offer after a password login

function readStorage(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeStorage(key: string, value: string | null) {
  try {
    if (value === null) localStorage.removeItem(key);
    else localStorage.setItem(key, value);
  } catch {
    // Private mode or blocked storage: the login page just starts with the password.
  }
}

export const thisDevicePasskey = () => readStorage(DEVICE_KEY);
export const forgetThisDevice = () => writeStorage(DEVICE_KEY, null);
export const declineOffer = () => writeStorage(DECLINED_KEY, "1");

export function passkeysSupported(): boolean {
  return window.isSecureContext && typeof window.PublicKeyCredential === "function" && !!navigator.credentials;
}

/** True when the device has its own fingerprint, face or screen-lock check (phones, Windows Hello, Touch ID). */
export async function hasBuiltInCheck(): Promise<boolean> {
  if (!passkeysSupported()) return false;
  try {
    return await PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable();
  } catch {
    return false;
  }
}

/** After a password login: offer the fingerprint, unless this device has it or said "not now". */
export async function shouldOfferPasskey(): Promise<boolean> {
  return !thisDevicePasskey() && readStorage(DECLINED_KEY) !== "1" && (await hasBuiltInCheck());
}

function toBytes(base64url: string): Uint8Array {
  const binary = atob(base64url.replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from(binary, (c) => c.charCodeAt(0));
}

function toBase64url(buffer: ArrayBuffer): string {
  let binary = "";
  new Uint8Array(buffer).forEach((b) => (binary += String.fromCharCode(b)));
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

const descriptors = (list: Json[] | undefined): PublicKeyCredentialDescriptor[] =>
  (list ?? []).map((d) => ({ type: "public-key", transports: d.transports, id: toBytes(d.id) }));

function credentialJson(credential: PublicKeyCredential, response: Json): Json {
  return {
    id: credential.id,
    rawId: toBase64url(credential.rawId),
    type: credential.type,
    response,
    clientExtensionResults: credential.getClientExtensionResults(),
    authenticatorAttachment: credential.authenticatorAttachment ?? undefined,
  };
}

async function createCredential(options: Json): Promise<Json> {
  const publicKey: PublicKeyCredentialCreationOptions = {
    ...(options as PublicKeyCredentialCreationOptions),
    challenge: toBytes(options.challenge),
    user: { ...options.user, id: toBytes(options.user.id) },
    excludeCredentials: descriptors(options.excludeCredentials),
  };
  const credential = (await navigator.credentials.create({ publicKey })) as PublicKeyCredential;
  const response = credential.response as AuthenticatorAttestationResponse;
  return credentialJson(credential, {
    clientDataJSON: toBase64url(response.clientDataJSON),
    attestationObject: toBase64url(response.attestationObject),
    transports: response.getTransports?.() ?? [],
  });
}

async function getCredential(options: Json): Promise<Json> {
  const publicKey: PublicKeyCredentialRequestOptions = {
    ...(options as PublicKeyCredentialRequestOptions),
    challenge: toBytes(options.challenge),
    allowCredentials: descriptors(options.allowCredentials),
  };
  const credential = (await navigator.credentials.get({ publicKey })) as PublicKeyCredential;
  const response = credential.response as AuthenticatorAssertionResponse;
  return credentialJson(credential, {
    clientDataJSON: toBase64url(response.clientDataJSON),
    authenticatorData: toBase64url(response.authenticatorData),
    signature: toBase64url(response.signature),
    userHandle: response.userHandle ? toBase64url(response.userHandle) : undefined,
  });
}

/** Asks the device for the fingerprint and logs in. */
export async function loginWithPasskey(): Promise<Me> {
  const credential = await getCredential((await api.passkeyLoginOptions()) as Json);
  try {
    const me = await api.passkeyLogin(credential);
    writeStorage(DEVICE_KEY, credential.rawId);
    return me;
  } catch (err) {
    // Removed from the site (or not accepted): this device goes back to the password.
    if (err instanceof ApiError && err.status === 401) forgetThisDevice();
    throw err;
  }
}

/** Registers this device's fingerprint / face check. Needs a logged-in session. */
export async function addThisDevice(): Promise<Passkey> {
  const credential = await createCredential((await api.passkeyRegisterOptions()) as Json);
  const passkey = await api.passkeyRegister(credential);
  writeStorage(DEVICE_KEY, passkey.credential_id);
  return passkey;
}

/** A message for the user, or null when they cancelled the device's prompt themselves. */
export function passkeyErrorMessage(err: unknown, registering = false): string | null {
  if (err instanceof DOMException) {
    // Cancelled, timed out, or no passkey on this device; the device already said so.
    if (err.name === "NotAllowedError" || err.name === "AbortError") return null;
    if (err.name === "InvalidStateError" && registering) return "המכשיר הזה כבר מוגדר לכניסה עם טביעת אצבע.";
    return "המכשיר לא הצליח לבדוק את טביעת האצבע. נסו שוב.";
  }
  return err instanceof Error ? err.message : "משהו השתבש";
}
