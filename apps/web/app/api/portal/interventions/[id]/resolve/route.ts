import { NextRequest, NextResponse } from "next/server";

export async function POST(request: NextRequest, context: { params: Promise<{ id: string }> }) {
  const { id } = await context.params;
  const response = await fetch(`${process.env.FOUNDATION_API_URL ?? "http://127.0.0.1:8001"}/api/v1/interventions/${encodeURIComponent(id)}/resolve`, {
    method: "POST",
    headers: {
      authorization: `Bearer ${process.env.FOUNDATION_ADMIN_TOKEN ?? ""}`,
      "content-type": "application/json",
    },
    body: JSON.stringify(await request.json()),
    cache: "no-store",
  });
  return NextResponse.json(await response.json(), { status: response.status });
}
