import { NextRequest, NextResponse } from "next/server";

const base = () => process.env.FOUNDATION_API_URL ?? "http://127.0.0.1:8001";
const headers = (contentType = true) => ({ authorization: `Bearer ${process.env.FOUNDATION_ADMIN_TOKEN ?? ""}`, ...(contentType ? { "content-type": "application/json" } : {}) });

export async function GET() {
  const response = await fetch(`${base()}/api/v1/profile`, { headers: headers(false), cache: "no-store" });
  return NextResponse.json(await response.json(), { status: response.status });
}

export async function PUT(request: NextRequest) {
  const response = await fetch(`${base()}/api/v1/profile`, { method: "PUT", headers: headers(), body: JSON.stringify(await request.json()) });
  return NextResponse.json(await response.json(), { status: response.status });
}
