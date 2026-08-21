import { NextResponse } from "next/server";

export async function POST(_: Request, context: { params: Promise<{ id: string }> }) {
  const { id } = await context.params;
  const response = await fetch(
    `${process.env.FOUNDATION_API_URL ?? "http://api:8000"}/api/v1/jobs/${encodeURIComponent(id)}/prepare`,
    { method: "POST", headers: { authorization: `Bearer ${process.env.FOUNDATION_ADMIN_TOKEN ?? ""}` } },
  );
  return new NextResponse(await response.text(), { status: response.status,
    headers: { "content-type": "application/json" } });
}
