import { NextRequest, NextResponse } from "next/server";

export async function POST(request: NextRequest, context: { params: Promise<{ id: string }> }) {
  const { id } = await context.params;
  const base = process.env.FOUNDATION_API_URL ?? "http://127.0.0.1:8001";
  const token = process.env.FOUNDATION_ADMIN_TOKEN ?? "";
  const body = await request.text();
  const response = await fetch(`${base}/api/v1/decisions/${encodeURIComponent(id)}`, {
    method: "POST", headers: { authorization: `Bearer ${token}`, "content-type": "application/json" }, body,
  });
  return new NextResponse(await response.text(), { status: response.status, headers: { "content-type": "application/json" } });
}
