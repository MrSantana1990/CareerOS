import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";

describe("mobile login safeguards", () => {
  const source = readFileSync(join(process.cwd(), "app/login/page.tsx"), "utf8");

  it("requires essential-cookie consent and keeps recovery code controlled", () => {
    expect(source).toContain("Aceitar e continuar");
    expect(source).toContain('value={code}');
    expect(source).toContain('autoComplete="off"');
    expect(source).toContain("este campo começa vazio");
  });

  it("forces https before authentication", () => {
    expect(source).toContain('window.location.protocol === "http:"');
    expect(source).toContain("https://${window.location.host}");
  });

  it("does not expose the container hostname in redirects", () => {
    const middleware = readFileSync(join(process.cwd(), "middleware.ts"), "utf8");
    expect(middleware).toContain('request.headers.get("x-forwarded-host")');
    expect(middleware).toContain('`https://${publicHost}`');
  });
});

// GOOGLE LOGIN != GMAIL INTEGRATION - o botao aqui so inicia o fluxo de
// IDENTIDADE (openid/email/profile); a integracao de Gmail/Calendar
// continua totalmente separada e nunca e mencionada nesta tela.
describe("Google Sign-In entry point", () => {
  const source = readFileSync(join(process.cwd(), "app/login/page.tsx"), "utf8");

  it("offers Continuar com Google alongside the password form", () => {
    expect(source).toContain("Continuar com Google");
    expect(source).toContain("/api/auth/google/start?next=");
  });

  it("requires the same essential-cookie consent before starting Google login", () => {
    const start = source.indexOf("function continueWithGoogle");
    const end = source.indexOf("\n  ", start + 40);
    const body = source.slice(start, source.indexOf("}", end) + 1);
    expect(body).toContain("if (!cookiesAccepted)");
  });

  it("surfaces a friendly message for each known Google login failure without exposing internals", () => {
    expect(source).toContain("google_not_configured");
    expect(source).toContain("google_login_failed");
    expect(source).toContain("google_email_unverified");
  });
});
