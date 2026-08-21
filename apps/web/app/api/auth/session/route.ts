import { NextRequest, NextResponse } from "next/server";
import { SESSION_COOKIE, validSession } from "../../../../lib/portal-auth";

export async function GET(request: NextRequest) {
  const valid = await validSession(request.cookies.get(SESSION_COOKIE)?.value, process.env.PORTAL_SESSION_SECRET ?? "");
  return NextResponse.json({ authenticated: valid }, { status: valid ? 200 : 401 });
}
