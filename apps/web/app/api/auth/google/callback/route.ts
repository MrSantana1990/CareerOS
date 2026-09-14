import { NextRequest, NextResponse } from "next/server";
import { createSession, SESSION_COOKIE } from "../../../../../lib/portal-auth";
import { exchangeCodeForGoogleIdentity, GoogleLoginError, type GoogleLoginAttempt } from "../../../../../lib/google-oidc";
import { publicUrl } from "../../../../../lib/public-url";

const PENDING_COOKIE = "google_oauth_pending";

async function upsertGoogleUser(identity: { sub: string; email: string; emailVerified: boolean; name?: string; picture?: string }) {
  const base = process.env.FOUNDATION_API_URL ?? "http://127.0.0.1:8001";
  const response = await fetch(`${base}/api/v1/auth/google`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      authorization: `Bearer ${process.env.FOUNDATION_ADMIN_TOKEN ?? ""}`,
    },
    body: JSON.stringify({
      provider_subject: identity.sub,
      email: identity.email,
      email_verified: identity.emailVerified,
      display_name: identity.name ?? "",
      avatar_url: identity.picture ?? null,
    }),
    cache: "no-store",
  });
  if (!response.ok) throw new Error(`core-google-upsert-failed:${response.status}`);
  return (await response.json()) as { id: string; email: string; full_name: string; avatar_url: string | null };
}

export async function GET(request: NextRequest) {
  // NUNCA construir a URL de redirect a partir de request.url diretamente
  // aqui - numa Route Handler self-hosted ele reflete o bind interno do
  // processo (0.0.0.0:3000), nao o dominio publico (achado real em
  // producao - ver lib/public-url.ts).
  const loginPage = publicUrl("/login", request);
  const clientId = process.env.GOOGLE_LOGIN_CLIENT_ID;
  const clientSecret = process.env.GOOGLE_LOGIN_CLIENT_SECRET;
  const redirectUri = process.env.GOOGLE_LOGIN_REDIRECT_URI;
  const sessionSecret = process.env.PORTAL_SESSION_SECRET ?? "";
  if (!clientId || !clientSecret || !redirectUri || sessionSecret.length < 32) {
    loginPage.searchParams.set("error", "google_not_configured");
    return NextResponse.redirect(loginPage);
  }
  const pendingCookie = request.cookies.get(PENDING_COOKIE)?.value;
  const code = request.nextUrl.searchParams.get("code");
  const state = request.nextUrl.searchParams.get("state");
  if (!pendingCookie || !code || !state) {
    loginPage.searchParams.set("error", "google_login_failed");
    return NextResponse.redirect(loginPage);
  }
  let attempt: GoogleLoginAttempt;
  try {
    attempt = JSON.parse(pendingCookie) as GoogleLoginAttempt;
  } catch {
    loginPage.searchParams.set("error", "google_login_failed");
    return NextResponse.redirect(loginPage);
  }
  // O `state` recebido de volta do Google PRECISA bater com o que
  // guardamos - essa comparação é a própria proteção CSRF do fluxo OAuth
  // (Secao 7).
  if (state !== attempt.state) {
    loginPage.searchParams.set("error", "google_login_failed");
    return NextResponse.redirect(loginPage);
  }
  try {
    const identity = await exchangeCodeForGoogleIdentity({
      code,
      codeVerifier: attempt.codeVerifier,
      redirectUri,
      clientId,
      clientSecret,
      expectedNonce: attempt.nonce,
    });
    if (!identity.emailVerified) {
      loginPage.searchParams.set("error", "google_email_unverified");
      return NextResponse.redirect(loginPage);
    }
    const user = await upsertGoogleUser(identity);
    const target = publicUrl(attempt.next, request);
    const response = NextResponse.redirect(target);
    response.cookies.set(SESSION_COOKIE, await createSession(user.email, sessionSecret, {
      authProvider: "GOOGLE",
      userId: user.id,
      displayName: user.full_name,
      ...(user.avatar_url ? { avatarUrl: user.avatar_url } : {}),
    }), {
      httpOnly: true,
      secure: process.env.NODE_ENV === "production",
      sameSite: "lax",
      path: "/",
      maxAge: 8 * 60 * 60,
    });
    response.cookies.set(PENDING_COOKIE, "", { path: "/api/auth/google", maxAge: 0 });
    return response;
  } catch (error) {
    // Nunca logar code/id_token/client_secret - so a classe do erro, que
    // e sempre uma das mensagens estaticas de GoogleLoginError/fetch,
    // nunca contém segredo algum.
    const reason = error instanceof GoogleLoginError ? error.message : "google_login_failed";
    loginPage.searchParams.set("error", reason);
    return NextResponse.redirect(loginPage);
  }
}
