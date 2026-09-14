import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";

describe("google callback route - same-origin redirect regression", () => {
  const source = readFileSync(join(process.cwd(), "app/api/auth/google/callback/route.ts"), "utf8");

  it("never builds a same-origin redirect from request.url directly (real production bug: resolves to 0.0.0.0:3000)", () => {
    expect(source).not.toMatch(/new URL\([^,]+,\s*request\.url\)/);
  });

  it("uses the trusted publicUrl() helper for every same-origin redirect target", () => {
    expect(source).toContain('import { publicUrl } from "../../../../../lib/public-url"');
    expect(source).toContain('publicUrl("/login", request)');
    expect(source).toContain("publicUrl(attempt.next, request)");
  });
});
