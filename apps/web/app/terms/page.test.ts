import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";

describe("terms of service page", () => {
  const source = readFileSync(join(process.cwd(), "app/terms/page.tsx"), "utf8");
  const middleware = readFileSync(join(process.cwd(), "middleware.ts"), "utf8");

  it("has the exact title required for Google OAuth branding", () => {
    expect(source).toContain("CareerOS — Termos de Uso");
  });

  it("shows the real product contact address", () => {
    expect(source).toContain("helpsystempro@gmail.com");
  });

  it("links back to the app and to the privacy page", () => {
    expect(source).toContain('href="/"');
    expect(source).toContain('href="/privacy"');
  });

  it("explicitly disclaims guaranteed employment instead of promising it", () => {
    // O texto MENCIONA contratacao/entrevista so para dizer que o CareerOS
    // NAO garante nenhuma delas - nunca promete resultado.
    expect(source).toMatch(/n[ãa]o garante (contrata[çc][ãa]o|entrevista)/i);
  });

  it("never promises unrestricted automatic mass applications", () => {
    // Regex tolera quebra de linha/indentacao do JSX entre palavras - o
    // texto renderizado no navegador junta tudo num paragrafo continuo.
    expect(source).toMatch(/candidaturas\s+em\s+massa\s+ou\s+totalmente\s+autom[áa]tico\s+n[ãa]o\s+ocorre\s+sem\s+configura[çc][ãa]o\s+e\s+autoriza[çc][ãa]o\s+expl[íi]citas/);
  });

  it("never promises 100% availability", () => {
    expect(source).not.toMatch(/disponibilidade (de )?100%|ininterrupt[ao] garantid[ao]/i);
    expect(source).toContain("melhor esforço");
  });

  it("disclaims affiliation with third-party platforms mentioned by name", () => {
    expect(source).toContain("não possui vínculo");
    for (const platform of ["Google", "LinkedIn", "InfoJobs", "Gupy"]) {
      expect(source).toContain(platform);
    }
  });

  it("is exempted from the authenticated-session middleware gate", () => {
    expect(middleware).toContain('request.nextUrl.pathname === "/terms"');
  });
});
