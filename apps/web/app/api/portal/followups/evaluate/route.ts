import { NextResponse } from "next/server";

export async function POST() {
  const response = await fetch(`${process.env.FOUNDATION_API_URL ?? "http://127.0.0.1:8001"}/api/v1/followups/evaluate`, {
    method: "POST",
    headers: { authorization: `Bearer ${process.env.FOUNDATION_ADMIN_TOKEN ?? ""}` },
  });
  return NextResponse.json(await response.json(), { status: response.status });
}
