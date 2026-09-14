const encoder = new TextEncoder();

export const SESSION_COOKIE = "helpsystem_career_session";

function base64Url(bytes: Uint8Array): string {
  let value = "";
  for (const byte of bytes) value += String.fromCharCode(byte);
  return btoa(value).replaceAll("+", "-").replaceAll("/", "_").replaceAll("=", "");
}

function decodeBase64Url(value: string): ArrayBuffer {
  const normalized = value.replaceAll("-", "+").replaceAll("_", "/");
  const decoded = atob(normalized.padEnd(Math.ceil(normalized.length / 4) * 4, "="));
  return Uint8Array.from(decoded, (character) => character.charCodeAt(0)).buffer as ArrayBuffer;
}

async function hmac(value: string, secret: string): Promise<string> {
  const key = await crypto.subtle.importKey("raw", encoder.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  return base64Url(new Uint8Array(await crypto.subtle.sign("HMAC", key, encoder.encode(value))));
}

export interface SessionPayload {
  email: string;
  expiresAt: number;
  // GOOGLE LOGIN != GMAIL INTEGRATION: authProvider aqui descreve so COMO a
  // sessao do CareerOS foi criada (senha do portal vs. Google Sign-In) -
  // nunca tem qualquer relacao com o token/refresh_token do Gmail
  // (google_career.py), que continua 100% separado.
  authProvider: "PASSWORD" | "GOOGLE";
  userId?: string;
  displayName?: string;
  avatarUrl?: string;
}

export interface SessionExtra {
  authProvider?: "PASSWORD" | "GOOGLE";
  userId?: string;
  displayName?: string;
  avatarUrl?: string;
}

export async function createSession(email: string, secret: string, extra?: SessionExtra): Promise<string> {
  const payload: SessionPayload = {
    email,
    expiresAt: Date.now() + 8 * 60 * 60 * 1000,
    authProvider: extra?.authProvider ?? "PASSWORD",
    ...(extra?.userId ? { userId: extra.userId } : {}),
    ...(extra?.displayName ? { displayName: extra.displayName } : {}),
    ...(extra?.avatarUrl ? { avatarUrl: extra.avatarUrl } : {}),
  };
  const encoded = base64Url(encoder.encode(JSON.stringify(payload)));
  return `${encoded}.${await hmac(encoded, secret)}`;
}

export async function recoveryCode(email: string, secret: string, bucket = Math.floor(Date.now() / 300_000)): Promise<string> {
  const signature = await hmac(`${email}:${bucket}:recovery`, secret);
  return signature.replaceAll("-", "A").replaceAll("_", "B").slice(0, 8).toUpperCase();
}

export async function verifyRecoveryCode(email: string, code: string, secret: string): Promise<boolean> {
  const normalized = code.trim().toUpperCase();
  const bucket = Math.floor(Date.now() / 300_000);
  return normalized === await recoveryCode(email, secret, bucket)
    || normalized === await recoveryCode(email, secret, bucket - 1);
}

export async function readSession(value: string | undefined, secret: string): Promise<SessionPayload | null> {
  if (!value || !secret) return null;
  const [payload, signature, extra] = value.split(".");
  if (!payload || !signature || extra || signature !== await hmac(payload, secret)) return null;
  try {
    const data = JSON.parse(new TextDecoder().decode(decodeBase64Url(payload))) as Partial<SessionPayload>;
    if (typeof data.expiresAt !== "number" || data.expiresAt <= Date.now()) return null;
    if (typeof data.email !== "string") return null;
    return { ...data, email: data.email, expiresAt: data.expiresAt, authProvider: data.authProvider ?? "PASSWORD" };
  } catch {
    return null;
  }
}

export async function validSession(value: string | undefined, secret: string): Promise<boolean> {
  return (await readSession(value, secret)) !== null;
}

export async function verifyPassword(password: string, encodedHash: string): Promise<boolean> {
  const [algorithm, iterationsText, saltText, expectedText] = encodedHash.split("$");
  const iterations = Number(iterationsText);
  if (algorithm !== "pbkdf2-sha256" || !Number.isSafeInteger(iterations) || iterations < 210_000) return false;
  const key = await crypto.subtle.importKey("raw", encoder.encode(password), "PBKDF2", false, ["deriveBits"]);
  const derived = new Uint8Array(await crypto.subtle.deriveBits(
    { name: "PBKDF2", hash: "SHA-256", salt: decodeBase64Url(saltText), iterations }, key, 256,
  ));
  const expected = new Uint8Array(decodeBase64Url(expectedText));
  if (derived.length !== expected.length) return false;
  let difference = 0;
  for (let index = 0; index < derived.length; index += 1) difference |= derived[index] ^ expected[index];
  return difference === 0;
}
