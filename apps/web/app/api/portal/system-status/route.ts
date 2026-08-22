import { NextResponse } from "next/server";

async function foundation(path: string) {
  const base = process.env.FOUNDATION_API_URL ?? "http://127.0.0.1:8001";
  const response = await fetch(`${base}${path}`, { cache: "no-store" });
  if (!response.ok) throw new Error(`${path}:${response.status}`);
  return response.json();
}

export async function GET() {
  try {
    const [status, health] = await Promise.all([
      foundation("/api/v1/system/status"),
      foundation("/health/ready"),
    ]);
    return NextResponse.json({ status, health, generatedAt: new Date().toISOString() });
  } catch {
    return NextResponse.json({ message: "Status do Core indisponível." }, { status: 503 });
  }
}
