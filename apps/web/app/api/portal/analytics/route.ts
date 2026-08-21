import { NextResponse } from "next/server";

export async function GET() {
  const response = await fetch(`${process.env.FOUNDATION_API_URL ?? "http://127.0.0.1:8001"}/api/v1/analytics`, {
    headers: { authorization: `Bearer ${process.env.FOUNDATION_ADMIN_TOKEN ?? ""}` },
    cache: "no-store",
  });
  return NextResponse.json(await response.json(), { status: response.status });
}
