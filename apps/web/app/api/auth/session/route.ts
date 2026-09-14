import { NextRequest, NextResponse } from "next/server";
import { readSession, SESSION_COOKIE } from "../../../../lib/portal-auth";

export async function GET(request: NextRequest) {
  const session = await readSession(request.cookies.get(SESSION_COOKIE)?.value, process.env.PORTAL_SESSION_SECRET ?? "");
  if (!session) return NextResponse.json({ authenticated: false }, { status: 401 });
  // authProvider aqui é só COMO a sessão do CareerOS nasceu (senha vs.
  // Google Sign-In) - nunca o status da integração de Gmail, que é
  // consultado separadamente (Secao 14: Google Account != Gmail).
  return NextResponse.json({
    authenticated: true,
    email: session.email,
    authProvider: session.authProvider,
    displayName: session.displayName ?? null,
    avatarUrl: session.avatarUrl ?? null,
  });
}
