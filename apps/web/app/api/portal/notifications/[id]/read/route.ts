import { NextRequest, NextResponse } from "next/server";

export async function POST(_request: NextRequest, context: { params: Promise<{ id: string }> }) {
  const { id } = await context.params;
  const response = await fetch(`${process.env.FOUNDATION_API_URL ?? "http://127.0.0.1:8001"}/api/v1/notifications/${encodeURIComponent(id)}/read`, {
    method: "POST",
    headers: { authorization: `Bearer ${process.env.FOUNDATION_ADMIN_TOKEN ?? ""}` },
  });
  return NextResponse.json(await response.json(), { status: response.status });
}
