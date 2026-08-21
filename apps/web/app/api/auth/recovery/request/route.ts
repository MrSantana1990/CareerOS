import { NextRequest, NextResponse } from "next/server";
import { recoveryCode } from "../../../../../lib/portal-auth";

const attempts = new Map<string, number>();

export async function POST(request: NextRequest) {
  const body = await request.json().catch(() => ({})) as { email?: string };
  const email = body.email?.trim().toLowerCase() ?? "";
  const expectedEmail = process.env.PORTAL_LOGIN_EMAIL?.trim().toLowerCase() ?? "";
  const secret = process.env.PORTAL_SESSION_SECRET ?? "";
  const generic = { message: "Se o e-mail estiver cadastrado, o código chegará em instantes." };
  if (!email || email !== expectedEmail || secret.length < 32) return NextResponse.json(generic);
  const key = `${request.headers.get("cf-connecting-ip") ?? request.headers.get("x-forwarded-for") ?? "unknown"}:${email}`;
  const lastAttempt = attempts.get(key) ?? 0;
  if (Date.now() - lastAttempt < 60_000) return NextResponse.json(generic);
  attempts.set(key, Date.now());
  const code = await recoveryCode(email, secret);
  const response = await fetch(`${process.env.AUTOMATION_HOST_URL ?? "http://127.0.0.1:8765"}/google/security-code`, {
    method: "POST",
    headers: {
      authorization: `Bearer ${process.env.FOUNDATION_ADMIN_TOKEN ?? ""}`,
      "content-type": "application/json",
    },
    body: JSON.stringify({ recipient: email, code }),
    cache: "no-store",
  }).catch(() => null);
  if (!response?.ok) return NextResponse.json({ message: "A entrega está temporariamente indisponível. Tente novamente em alguns minutos." }, { status: 503 });
  return NextResponse.json(generic);
}
