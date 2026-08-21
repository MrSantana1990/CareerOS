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
});
