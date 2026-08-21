import { NextRequest, NextResponse } from "next/server";
import { createSession, SESSION_COOKIE, verifyRecoveryCode } from "../../../../../lib/portal-auth";

export async function POST(request: NextRequest) {
  const body = await request.json().catch(() => ({})) as { email?: string; code?: string };
  const email = body.email?.trim().toLowerCase() ?? "";
  const code = body.code ?? "";
  const expectedEmail = process.env.PORTAL_LOGIN_EMAIL?.trim().toLowerCase() ?? "";
  const secret = process.env.PORTAL_SESSION_SECRET ?? "";
  if (email !== expectedEmail || !(await verifyRecoveryCode(email, code, secret))) {
    return NextResponse.json({ message: "Código inválido ou expirado." }, { status: 401 });
  }
  const response = NextResponse.json({ ok: true });
  response.cookies.set(SESSION_COOKIE, await createSession(email, secret), {
    httpOnly: true, secure: process.env.NODE_ENV === "production", sameSite: "lax", path: "/", maxAge: 8 * 60 * 60,
  });
  return response;
}
