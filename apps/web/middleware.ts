import { NextRequest, NextResponse } from "next/server";
import { SESSION_COOKIE, validSession } from "./lib/portal-auth";

export async function middleware(request: NextRequest) {
  const forwardedProtocol = request.headers.get("x-forwarded-proto");
  if (forwardedProtocol === "http") {
    const publicHost = request.headers.get("x-forwarded-host")
      ?? request.headers.get("host")
      ?? "carreira.helpsystempro.site";
    const secureUrl = new URL(`${request.nextUrl.pathname}${request.nextUrl.search}`, `https://${publicHost}`);
    return NextResponse.redirect(secureUrl, 308);
  }
  const secret = process.env.PORTAL_SESSION_SECRET ?? "";
  const authenticated = await validSession(request.cookies.get(SESSION_COOKIE)?.value, secret);
  if (request.nextUrl.pathname === "/login") {
    return authenticated ? NextResponse.redirect(new URL("/", request.url)) : NextResponse.next();
  }
  if (authenticated) return NextResponse.next();
  if (request.nextUrl.pathname.startsWith("/api/")) return NextResponse.json({ message: "Não autenticado." }, { status: 401 });
  const login = new URL("/login", request.url);
  login.searchParams.set("next", request.nextUrl.pathname);
  return NextResponse.redirect(login);
}

export const config = { matcher: ["/((?!api/auth|health|manifest.webmanifest|_next/static|_next/image|favicon.ico).*)"] };
