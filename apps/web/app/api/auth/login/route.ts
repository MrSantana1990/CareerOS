import { NextRequest, NextResponse } from "next/server";
import { createSession, SESSION_COOKIE, verifyPassword } from "../../../../lib/portal-auth";

export async function POST(request: NextRequest) {
  const expectedEmail = process.env.PORTAL_LOGIN_EMAIL?.trim().toLowerCase();
  const passwordHash = process.env.PORTAL_PASSWORD_HASH ?? "";
  const sessionSecret = process.env.PORTAL_SESSION_SECRET ?? "";
  if (!expectedEmail || !passwordHash || sessionSecret.length < 32) {
    return NextResponse.json({ message: "Portal ainda não configurado." }, { status: 503 });
  }
  const body = await request.json().catch(() => ({})) as { email?: string; password?: string };
  const email = body.email?.trim().toLowerCase() ?? "";
  const password = body.password ?? "";
  const valid = email === expectedEmail && password.length <= 256 && await verifyPassword(password, passwordHash);
  if (!valid) return NextResponse.json({ message: "E-mail ou senha inválidos." }, { status: 401 });
  const response = NextResponse.json({ ok: true });
  response.cookies.set(SESSION_COOKIE, await createSession(email, sessionSecret), {
    httpOnly: true, secure: process.env.NODE_ENV === "production", sameSite: "strict", path: "/", maxAge: 8 * 60 * 60,
  });
  return response;
}
