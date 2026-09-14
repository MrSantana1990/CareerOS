import { describe, expect, it } from "vitest";
import { publicOrigin, publicUrl } from "./public-url";

function fakeRequest(headers: Record<string, string>): Request {
  // O `url` aqui é deliberadamente o mesmo bug real de produção
  // (0.0.0.0:3000) - publicOrigin/publicUrl NUNCA devem olhar para ele.
  return new Request("http://0.0.0.0:3000/api/auth/google/callback", { headers });
}

describe("publicOrigin", () => {
  it("never uses request.url as the origin, even when it points at the internal bind address", () => {
    const origin = publicOrigin(fakeRequest({ host: "carreira.helpsystempro.site" }));
    expect(origin).not.toContain("0.0.0.0");
    expect(origin).not.toContain("3000");
  });

  it("prefers x-forwarded-host over the plain host header", () => {
    const origin = publicOrigin(fakeRequest({
      host: "web:3000", "x-forwarded-host": "carreira.helpsystempro.site",
    }));
    expect(origin).toBe("https://carreira.helpsystempro.site");
  });

  it("falls back to the host header when x-forwarded-host is absent", () => {
    const origin = publicOrigin(fakeRequest({ host: "carreira.helpsystempro.site" }));
    expect(origin).toBe("https://carreira.helpsystempro.site");
  });

  it("falls back to the known production domain when no host header exists at all", () => {
    const origin = publicOrigin(fakeRequest({}));
    expect(origin).toBe("https://carreira.helpsystempro.site");
  });

  it("respects x-forwarded-proto when present, defaults to https otherwise", () => {
    expect(publicOrigin(fakeRequest({ host: "x", "x-forwarded-proto": "http" }))).toBe("http://x");
    expect(publicOrigin(fakeRequest({ host: "x" }))).toBe("https://x");
  });
});

describe("publicUrl", () => {
  it("resolves a relative path against the trusted public origin, never the internal bind address", () => {
    const url = publicUrl("/login", fakeRequest({ "x-forwarded-host": "carreira.helpsystempro.site" }));
    expect(url.toString()).toBe("https://carreira.helpsystempro.site/login");
  });

  it("preserves the path exactly as given (e.g. the post-login redirect target)", () => {
    const url = publicUrl("/", fakeRequest({ "x-forwarded-host": "carreira.helpsystempro.site" }));
    expect(url.pathname).toBe("/");
    expect(url.host).toBe("carreira.helpsystempro.site");
  });
});
