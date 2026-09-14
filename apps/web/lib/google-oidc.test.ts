import { afterEach, describe, expect, it, vi } from "vitest";
import { exportJWK, generateKeyPair, SignJWT } from "jose";
import {
  buildGoogleAuthorizationUrl, exchangeCodeForGoogleIdentity, GoogleLoginError, startGoogleLoginAttempt,
} from "./google-oidc";

/**
 * GOOGLE LOGIN != GMAIL INTEGRATION. Estes testes nunca acessam a rede real
 * do Google - assinam um id_token de verdade com um par de chaves gerado
 * localmente (jose.generateKeyPair) e interceptam fetch() para devolver
 * esse token e o JWKS correspondente, exercitando a MESMA verificação real
 * (assinatura/issuer/audience/nonce/expiração) que rodaria contra o Google
 * de verdade, sem nenhuma dependência externa em CI.
 */

const CLIENT_ID = "test-client-id.apps.googleusercontent.com";
const KID = "test-key-1";

async function issueSignedIdToken(overrides: Record<string, unknown> = {}) {
  const { publicKey, privateKey } = await generateKeyPair("RS256");
  const jwk = await exportJWK(publicKey);
  const now = Math.floor(Date.now() / 1000);
  const claims = {
    sub: "10769150350006150715113082367",
    email: "rodolfo@example.com",
    email_verified: true,
    name: "Rodolfo Santana",
    picture: "https://lh3.googleusercontent.com/a/avatar.png",
    nonce: "expected-nonce-value",
    ...overrides,
  };
  const idToken = await new SignJWT(claims)
    .setProtectedHeader({ alg: "RS256", kid: KID })
    .setIssuedAt(now)
    .setIssuer("https://accounts.google.com")
    .setAudience(CLIENT_ID)
    .setExpirationTime(now + 3600)
    .sign(privateKey);
  return { idToken, jwks: { keys: [{ ...jwk, kid: KID, use: "sig", alg: "RS256" }] } };
}

function mockFetchSequence(idToken: string, jwks: object) {
  return vi.fn(async (input: string | URL) => {
    const url = input.toString();
    if (url.includes("oauth2.googleapis.com/token")) {
      return new Response(JSON.stringify({ id_token: idToken }), { status: 200 });
    }
    if (url.includes("googleapis.com/oauth2/v3/certs")) {
      return new Response(JSON.stringify(jwks), { status: 200 });
    }
    throw new Error(`unexpected fetch: ${url}`);
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("startGoogleLoginAttempt", () => {
  it("produces unguessable, distinct state/nonce/codeVerifier every time", () => {
    const first = startGoogleLoginAttempt("/dashboard");
    const second = startGoogleLoginAttempt("/dashboard");
    expect(first.state).not.toBe(second.state);
    expect(first.nonce).not.toBe(second.nonce);
    expect(first.codeVerifier).not.toBe(second.codeVerifier);
    expect(first.state.length).toBeGreaterThan(20);
  });

  it("normalizes an unsafe next target to the app root", () => {
    expect(startGoogleLoginAttempt("https://evil.example.com").next).toBe("/");
    expect(startGoogleLoginAttempt("/jobs").next).toBe("/jobs");
  });
});

describe("buildGoogleAuthorizationUrl", () => {
  it("requests ONLY login scopes - never gmail/calendar - and access_type=online", async () => {
    const attempt = startGoogleLoginAttempt("/");
    const url = new URL(await buildGoogleAuthorizationUrl({
      clientId: CLIENT_ID, redirectUri: "https://carreira.example.com/api/auth/google/callback", attempt,
    }));
    expect(url.searchParams.get("scope")).toBe("openid email profile");
    expect(url.searchParams.get("access_type")).toBe("online");
    expect(url.searchParams.get("scope")).not.toContain("gmail");
    expect(url.searchParams.get("scope")).not.toContain("calendar");
    expect(url.searchParams.get("code_challenge_method")).toBe("S256");
    expect(url.searchParams.get("state")).toBe(attempt.state);
    expect(url.searchParams.get("nonce")).toBe(attempt.nonce);
  });
});

describe("exchangeCodeForGoogleIdentity", () => {
  it("verifies a real signed id_token end-to-end and extracts the identity", async () => {
    const { idToken, jwks } = await issueSignedIdToken();
    vi.stubGlobal("fetch", mockFetchSequence(idToken, jwks));
    const identity = await exchangeCodeForGoogleIdentity({
      code: "auth-code", codeVerifier: "verifier", redirectUri: "https://x/callback",
      clientId: CLIENT_ID, clientSecret: "shh", expectedNonce: "expected-nonce-value",
    });
    expect(identity).toMatchObject({
      sub: "10769150350006150715113082367", email: "rodolfo@example.com", emailVerified: true,
      name: "Rodolfo Santana",
    });
  });

  // B: issuer invalido -> reject -------------------------------------------------------------------------

  it("rejects a token with an untrusted issuer", async () => {
    const { publicKey, privateKey } = await generateKeyPair("RS256");
    const jwk = await exportJWK(publicKey);
    const now = Math.floor(Date.now() / 1000);
    const forged = await new SignJWT({
      sub: "x", email: "a@b.com", email_verified: true, nonce: "expected-nonce-value",
    }).setProtectedHeader({ alg: "RS256", kid: KID }).setIssuedAt(now)
      .setIssuer("https://not-google.example.com").setAudience(CLIENT_ID).setExpirationTime(now + 3600)
      .sign(privateKey);
    vi.stubGlobal("fetch", mockFetchSequence(forged, { keys: [{ ...jwk, kid: KID, use: "sig", alg: "RS256" }] }));
    await expect(exchangeCodeForGoogleIdentity({
      code: "c", codeVerifier: "v", redirectUri: "https://x/callback", clientId: CLIENT_ID,
      clientSecret: "s", expectedNonce: "expected-nonce-value",
    })).rejects.toThrow();
  });

  // C: audience invalida -> reject ------------------------------------------------------------------------

  it("rejects a token issued for a different audience/client", async () => {
    const { publicKey, privateKey } = await generateKeyPair("RS256");
    const jwk = await exportJWK(publicKey);
    const now = Math.floor(Date.now() / 1000);
    const idToken = await new SignJWT({
      sub: "x", email: "a@b.com", email_verified: true, nonce: "expected-nonce-value",
    }).setProtectedHeader({ alg: "RS256", kid: KID }).setIssuedAt(now)
      .setIssuer("https://accounts.google.com").setAudience("someone-elses-client-id").setExpirationTime(now + 3600)
      .sign(privateKey);
    vi.stubGlobal("fetch", mockFetchSequence(idToken, { keys: [{ ...jwk, kid: KID, use: "sig", alg: "RS256" }] }));
    await expect(exchangeCodeForGoogleIdentity({
      code: "c", codeVerifier: "v", redirectUri: "https://x/callback", clientId: CLIENT_ID,
      clientSecret: "s", expectedNonce: "expected-nonce-value",
    })).rejects.toThrow();
  });

  // D: token expirado -> reject -----------------------------------------------------------------------------

  it("rejects an expired token", async () => {
    const { publicKey, privateKey } = await generateKeyPair("RS256");
    const jwk = await exportJWK(publicKey);
    const now = Math.floor(Date.now() / 1000);
    const idToken = await new SignJWT({
      sub: "x", email: "a@b.com", email_verified: true, nonce: "expected-nonce-value",
    }).setProtectedHeader({ alg: "RS256", kid: KID }).setIssuedAt(now - 7200)
      .setIssuer("https://accounts.google.com").setAudience(CLIENT_ID).setExpirationTime(now - 3600)
      .sign(privateKey);
    vi.stubGlobal("fetch", mockFetchSequence(idToken, { keys: [{ ...jwk, kid: KID, use: "sig", alg: "RS256" }] }));
    await expect(exchangeCodeForGoogleIdentity({
      code: "c", codeVerifier: "v", redirectUri: "https://x/callback", clientId: CLIENT_ID,
      clientSecret: "s", expectedNonce: "expected-nonce-value",
    })).rejects.toThrow();
  });

  // nonce mismatch (parte do requisito de Secao 7) -----------------------------------------------------------

  it("rejects a token whose nonce does not match the one we generated", async () => {
    const { idToken, jwks } = await issueSignedIdToken({ nonce: "a-different-nonce" });
    vi.stubGlobal("fetch", mockFetchSequence(idToken, jwks));
    await expect(exchangeCodeForGoogleIdentity({
      code: "c", codeVerifier: "v", redirectUri: "https://x/callback", clientId: CLIENT_ID,
      clientSecret: "s", expectedNonce: "expected-nonce-value",
    })).rejects.toThrow(GoogleLoginError);
  });

  // E: email nao verificado -> a funcao ainda extrai, o CALLER decide rejeitar (route.ts faz isso) -----------

  it("surfaces emailVerified=false explicitly instead of assuming true", async () => {
    const { idToken, jwks } = await issueSignedIdToken({ email_verified: false });
    vi.stubGlobal("fetch", mockFetchSequence(idToken, jwks));
    const identity = await exchangeCodeForGoogleIdentity({
      code: "c", codeVerifier: "v", redirectUri: "https://x/callback", clientId: CLIENT_ID,
      clientSecret: "s", expectedNonce: "expected-nonce-value",
    });
    expect(identity.emailVerified).toBe(false);
  });

  it("never reads or exposes the Google access_token even when present in the response", async () => {
    const { idToken, jwks } = await issueSignedIdToken();
    const fetchMock = vi.fn(async (input: string | URL) => {
      const url = input.toString();
      if (url.includes("oauth2.googleapis.com/token")) {
        return new Response(JSON.stringify({ id_token: idToken, access_token: "should-never-be-touched" }), { status: 200 });
      }
      if (url.includes("googleapis.com/oauth2/v3/certs")) return new Response(JSON.stringify(jwks), { status: 200 });
      throw new Error(`unexpected fetch: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    const identity = await exchangeCodeForGoogleIdentity({
      code: "c", codeVerifier: "v", redirectUri: "https://x/callback", clientId: CLIENT_ID,
      clientSecret: "s", expectedNonce: "expected-nonce-value",
    });
    expect(JSON.stringify(identity)).not.toContain("should-never-be-touched");
  });

  it("raises a typed GoogleLoginError when the token endpoint fails", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("", { status: 400 })));
    await expect(exchangeCodeForGoogleIdentity({
      code: "c", codeVerifier: "v", redirectUri: "https://x/callback", clientId: CLIENT_ID,
      clientSecret: "s", expectedNonce: "n",
    })).rejects.toThrow(GoogleLoginError);
  });
});
