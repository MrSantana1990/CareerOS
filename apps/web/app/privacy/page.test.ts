import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";

describe("privacy policy page", () => {
  const source = readFileSync(join(process.cwd(), "app/privacy/page.tsx"), "utf8");
  const middleware = readFileSync(join(process.cwd(), "middleware.ts"), "utf8");

  it("has the exact title required for Google OAuth branding", () => {
    expect(source).toContain("CareerOS — Política de Privacidade");
  });

  it("shows the real product contact address", () => {
    expect(source).toContain("helpsystempro@gmail.com");
  });

  it("links back to the app and to the terms page", () => {
    expect(source).toContain('href="/"');
    expect(source).toContain('href="/terms"');
  });

  it("explicitly disclaims automatic deletion instead of promising it", () => {
    // O texto MENCIONA exclusao automatica so para dizer que NAO existe -
    // nunca a promete como recurso disponivel.
    expect(source).toMatch(/ainda n[ãa]o possui um mecanismo de exclus[ãa]o autom[áa]tica/i);
  });

  it("never claims certifications or legal compliance frameworks it does not have", () => {
    expect(source).not.toMatch(/certificad[ao]/i);
    expect(source).not.toMatch(/\bLGPD\b/i);
  });

  it("never claims data is sold to third parties", () => {
    expect(source.toLowerCase()).toContain("não vende dados");
  });

  it("is exempted from the authenticated-session middleware gate", () => {
    expect(middleware).toContain('request.nextUrl.pathname === "/privacy"');
    const guardStart = middleware.indexOf('pathname === "/privacy"');
    const guardEnd = middleware.indexOf("\n", guardStart);
    const guardLineArea = middleware.slice(Math.max(0, guardStart - 200), guardEnd + 80);
    expect(guardLineArea).toContain("NextResponse.next()");
  });
});
