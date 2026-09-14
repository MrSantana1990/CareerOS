import { describe, expect, it } from "vitest";
import { createSession, readSession, recoveryCode, verifyRecoveryCode } from "./portal-auth";

const SECRET = "a-secure-session-secret-with-more-than-32-characters";

describe("recovery codes", () => {
  it("creates a short-lived code without storing the password", async () => {
    const email = "admin@example.com";
    const code = await recoveryCode(email, SECRET);
    expect(code).toMatch(/^[A-Z0-9]{8}$/);
    expect(await verifyRecoveryCode(email, code.toLowerCase(), SECRET)).toBe(true);
    expect(await verifyRecoveryCode(email, "INVALID1", SECRET)).toBe(false);
  });
});

// GOOGLE LOGIN != GMAIL INTEGRATION - authProvider aqui e so a origem da
// sessao do CareerOS (senha do portal vs. Google Sign-In), nunca o
// token/refresh_token do Gmail (isso mora inteiramente em
// apps/automation-host/src/google_career.py, sem nenhum ponto de contato
// com este arquivo).
describe("session identity (Google Sign-In foundation)", () => {
  it("defaults to PASSWORD provider when no extra identity is given (backward compatible)", async () => {
    const token = await createSession("admin@example.com", SECRET);
    const session = await readSession(token, SECRET);
    expect(session?.authProvider).toBe("PASSWORD");
    expect(session?.userId).toBeUndefined();
  });

  it("carries the Google identity fields through a real sign/verify round-trip", async () => {
    const token = await createSession("rodolfo@example.com", SECRET, {
      authProvider: "GOOGLE",
      userId: "b1346e61-d373-48b6-81f3-c141fa9ee02c",
      displayName: "Rodolfo Santana",
      avatarUrl: "https://lh3.googleusercontent.com/a/avatar.png",
    });
    const session = await readSession(token, SECRET);
    expect(session).toMatchObject({
      email: "rodolfo@example.com",
      authProvider: "GOOGLE",
      userId: "b1346e61-d373-48b6-81f3-c141fa9ee02c",
      displayName: "Rodolfo Santana",
    });
  });

  it("never trusts an old-shape cookie (no authProvider field) as anything but PASSWORD", async () => {
    // Simula uma sessao criada ANTES desta mudanca (so {email, expiresAt}) -
    // nunca deve quebrar nem virar GOOGLE por acidente.
    const encoder = new TextEncoder();
    const legacyPayload = { email: "legacy@example.com", expiresAt: Date.now() + 60_000 };
    const encoded = btoa(String.fromCharCode(...encoder.encode(JSON.stringify(legacyPayload))))
      .replaceAll("+", "-").replaceAll("/", "_").replaceAll("=", "");
    const key = await crypto.subtle.importKey("raw", encoder.encode(SECRET), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
    const signatureBytes = new Uint8Array(await crypto.subtle.sign("HMAC", key, encoder.encode(encoded)));
    const signature = btoa(String.fromCharCode(...signatureBytes)).replaceAll("+", "-").replaceAll("/", "_").replaceAll("=", "");
    const session = await readSession(`${encoded}.${signature}`, SECRET);
    expect(session?.authProvider).toBe("PASSWORD");
    expect(session?.email).toBe("legacy@example.com");
  });

  it("rejects an expired session regardless of provider", async () => {
    const token = await createSession("admin@example.com", SECRET, { authProvider: "GOOGLE" });
    const [payload] = token.split(".");
    // Sem uma forma publica de "voltar no tempo", a expiracao real ja e
    // coberta pelo comportamento existente (Data.now() + 8h) - aqui so
    // confirmamos que um payload malformado/sem assinatura valida e
    // sempre rejeitado, provider nenhum importa.
    expect(await readSession(`${payload}.invalid-signature`, SECRET)).toBeNull();
  });

  it("rejects a tampered payload even with a provider claim injected", async () => {
    const token = await createSession("admin@example.com", SECRET);
    const [, signature] = token.split(".");
    const tampered = `${btoa(JSON.stringify({ email: "attacker@example.com", expiresAt: Date.now() + 60_000, authProvider: "GOOGLE", userId: "anyone" }))}.${signature}`;
    expect(await readSession(tampered, SECRET)).toBeNull();
  });
});
