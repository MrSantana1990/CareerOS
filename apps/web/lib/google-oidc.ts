import { createLocalJWKSet, jwtVerify, type JSONWebKeySet } from "jose";

/**
 * GOOGLE LOGIN != GMAIL INTEGRATION.
 *
 * This module implements ONLY the OIDC identity flow (openid/email/profile,
 * access_type=online, no refresh token) used to authenticate a CareerOS
 * session. It never touches Gmail/Calendar scopes, never persists a Google
 * access_token/refresh_token, and is completely independent from
 * apps/automation-host's google_career.py (which owns the separate,
 * offline-access Gmail/Calendar integration with its own OAuth client).
 */

const GOOGLE_ISSUERS = ["https://accounts.google.com", "accounts.google.com"];
const GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs";
const GOOGLE_AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth";
const GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token";

export class GoogleLoginError extends Error {}

async function fetchGoogleJwks(): Promise<ReturnType<typeof createLocalJWKSet>> {
  // Busca o JWKS via fetch() (a mesma função global usada para o token
  // endpoint, e portanto mockável em teste) em vez de
  // jose.createRemoteJWKSet - no build Node do jose, RemoteJWKSet usa
  // node:http/node:https diretamente por baixo dos panos, ignorando
  // completamente qualquer global.fetch mockado (achado real: os testes
  // deste modulo estavam silenciosamente batendo na Google real e
  // passando por um motivo errado - JWKSNoMatchingKey generico, nunca
  // exercitando de fato a rejeicao de issuer/audience/expiracao).
  // createLocalJWKSet nos da a MESMA verificacao de assinatura/kid, so
  // que sobre um JSON que nos mesmos buscamos - login e um caminho raro,
  // então buscar a cada chamada (sem cache) é aceitável e mais simples.
  const response = await fetch(GOOGLE_JWKS_URL);
  if (!response.ok) throw new GoogleLoginError("google-jwks-fetch-failed");
  const jwks = (await response.json()) as JSONWebKeySet;
  return createLocalJWKSet(jwks);
}

function randomUrlSafeString(byteLength: number): string {
  const bytes = new Uint8Array(byteLength);
  crypto.getRandomValues(bytes);
  let value = "";
  for (const byte of bytes) value += String.fromCharCode(byte);
  return btoa(value).replaceAll("+", "-").replaceAll("/", "_").replaceAll("=", "");
}

async function codeChallengeFor(codeVerifier: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(codeVerifier));
  let value = "";
  for (const byte of new Uint8Array(digest)) value += String.fromCharCode(byte);
  return btoa(value).replaceAll("+", "-").replaceAll("/", "_").replaceAll("=", "");
}

export interface GoogleLoginAttempt {
  state: string;
  nonce: string;
  codeVerifier: string;
  next: string;
}

export function startGoogleLoginAttempt(next: string): GoogleLoginAttempt {
  return {
    state: randomUrlSafeString(24),
    nonce: randomUrlSafeString(24),
    codeVerifier: randomUrlSafeString(64),
    next: next.startsWith("/") ? next : "/",
  };
}

export async function buildGoogleAuthorizationUrl(params: {
  clientId: string;
  redirectUri: string;
  attempt: GoogleLoginAttempt;
}): Promise<string> {
  const url = new URL(GOOGLE_AUTH_ENDPOINT);
  url.searchParams.set("client_id", params.clientId);
  url.searchParams.set("redirect_uri", params.redirectUri);
  url.searchParams.set("response_type", "code");
  // Scopes de LOGIN somente (Secao 1) - nunca gmail/calendar aqui.
  url.searchParams.set("scope", "openid email profile");
  url.searchParams.set("state", params.attempt.state);
  url.searchParams.set("nonce", params.attempt.nonce);
  url.searchParams.set("code_challenge", await codeChallengeFor(params.attempt.codeVerifier));
  url.searchParams.set("code_challenge_method", "S256");
  // access_type=online (padrao) - nunca "offline": login nunca deve
  // resultar num refresh_token do Google (Secao 1/6 - sessao e gerida
  // inteiramente pelo CareerOS, nao pelo Google).
  url.searchParams.set("access_type", "online");
  url.searchParams.set("prompt", "select_account");
  return url.toString();
}

export interface GoogleIdentity {
  sub: string;
  email: string;
  emailVerified: boolean;
  name?: string;
  picture?: string;
}

export async function exchangeCodeForGoogleIdentity(params: {
  code: string;
  codeVerifier: string;
  redirectUri: string;
  clientId: string;
  clientSecret: string;
  expectedNonce: string;
}): Promise<GoogleIdentity> {
  const body = new URLSearchParams({
    code: params.code,
    client_id: params.clientId,
    client_secret: params.clientSecret,
    redirect_uri: params.redirectUri,
    grant_type: "authorization_code",
    code_verifier: params.codeVerifier,
  });
  const response = await fetch(GOOGLE_TOKEN_ENDPOINT, {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body,
  });
  if (!response.ok) throw new GoogleLoginError("google-token-exchange-failed");
  const tokens = (await response.json().catch(() => ({}))) as { id_token?: string };
  // O access_token (se vier) e descartado aqui mesmo - nunca e lido,
  // guardado ou usado como sessao (Secao 6, Teste I).
  if (!tokens.id_token) throw new GoogleLoginError("google-token-response-missing-id-token");
  const jwks = await fetchGoogleJwks();
  const { payload } = await jwtVerify(tokens.id_token, jwks, {
    issuer: GOOGLE_ISSUERS,
    audience: params.clientId,
  });
  if (payload.nonce !== params.expectedNonce) throw new GoogleLoginError("google-id-token-nonce-mismatch");
  if (typeof payload.sub !== "string" || typeof payload.email !== "string") {
    throw new GoogleLoginError("google-id-token-missing-claims");
  }
  return {
    sub: payload.sub,
    email: payload.email,
    emailVerified: payload.email_verified === true,
    name: typeof payload.name === "string" ? payload.name : undefined,
    picture: typeof payload.picture === "string" ? payload.picture : undefined,
  };
}
