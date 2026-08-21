import { NextRequest, NextResponse } from "next/server";

const base = process.env.FOUNDATION_API_URL ?? "http://api:8000";
const headers = () => ({ authorization: `Bearer ${process.env.FOUNDATION_ADMIN_TOKEN ?? ""}`,
  "content-type": "application/json" });

export async function GET() {
  const response = await fetch(`${base}/api/v1/answers`, { headers: headers(), cache: "no-store" });
  return new NextResponse(await response.text(), { status: response.status,
    headers: { "content-type": "application/json" } });
}

export async function PUT(request: NextRequest) {
  const response = await fetch(`${base}/api/v1/answers`, { method: "PUT", headers: headers(),
    body: await request.text() });
  return new NextResponse(await response.text(), { status: response.status,
    headers: { "content-type": "application/json" } });
}
