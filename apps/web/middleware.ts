import { NextRequest, NextResponse } from "next/server";
import { SESSION_COOKIE, validSession } from "./lib/portal-auth";

export async function middleware(request: NextRequest) {
  const secret = process.env.PORTAL_SESSION_SECRET ?? "";
  if (await validSession(request.cookies.get(SESSION_COOKIE)?.value, secret)) return NextResponse.next();
  if (request.nextUrl.pathname.startsWith("/api/")) return NextResponse.json({ message: "Não autenticado." }, { status: 401 });
  const login = new URL("/login", request.url);
  login.searchParams.set("next", request.nextUrl.pathname);
  return NextResponse.redirect(login);
}

export const config = { matcher: ["/((?!login|api/auth|health|manifest.webmanifest|_next/static|_next/image|favicon.ico).*)"] };
