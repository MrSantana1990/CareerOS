import { NextRequest, NextResponse } from "next/server";
import { buildGoogleAuthorizationUrl, startGoogleLoginAttempt } from "../../../../../lib/google-oidc";

const PENDING_COOKIE = "google_oauth_pending";

export async function GET(request: NextRequest) {
  const clientId = process.env.GOOGLE_LOGIN_CLIENT_ID;
  const redirectUri = process.env.GOOGLE_LOGIN_REDIRECT_URI;
  if (!clientId || !redirectUri) {
    return NextResponse.json({ message: "Login com Google ainda não configurado." }, { status: 503 });
  }
  const next = request.nextUrl.searchParams.get("next") ?? "/";
  const attempt = startGoogleLoginAttempt(next);
  const authorizationUrl = await buildGoogleAuthorizationUrl({ clientId, redirectUri, attempt });
  const response = NextResponse.redirect(authorizationUrl);
  // Cookie efêmera (10 min) só para round-trip do state/nonce/PKCE - nunca
  // é a sessão do CareerOS em si (essa só nasce depois da verificação
  // completa do id_token, no callback).
  response.cookies.set(PENDING_COOKIE, JSON.stringify(attempt), {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/api/auth/google",
    maxAge: 600,
  });
  return response;
}
