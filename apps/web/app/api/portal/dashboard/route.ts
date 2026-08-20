import { NextResponse } from "next/server";

async function foundation(path: string) {
  const base = process.env.FOUNDATION_API_URL ?? "http://127.0.0.1:8001";
  const token = process.env.FOUNDATION_ADMIN_TOKEN ?? "";
  const response = await fetch(`${base}${path}`, { headers: { authorization: `Bearer ${token}` }, cache: "no-store" });
  if (!response.ok) throw new Error(`${path}:${response.status}`);
  return response.json();
}

export async function GET() {
  try {
    const [workspace, rules, decisions] = await Promise.all([
      foundation("/api/v1/workspace"), foundation("/api/v1/career-rules"), foundation("/api/v1/decisions"),
    ]);
    return NextResponse.json({ workspace, rules, decisions, generatedAt: new Date().toISOString() });
  } catch {
    return NextResponse.json({ message: "A central de dados está temporariamente indisponível." }, { status: 503 });
  }
}
