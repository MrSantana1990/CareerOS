import { NextRequest, NextResponse } from "next/server";

export async function POST(request: NextRequest) {
  const family = request.nextUrl.searchParams.get("family") ?? "GENERAL";
  const language = request.nextUrl.searchParams.get("language") ?? "pt-BR";
  const target = new URL(`${process.env.FOUNDATION_API_URL ?? "http://127.0.0.1:8001"}/api/v1/profile/resume`);
  target.searchParams.set("family", family);
  target.searchParams.set("language", language);
  const response = await fetch(target, {
    method: "POST",
    headers: { authorization: `Bearer ${process.env.FOUNDATION_ADMIN_TOKEN ?? ""}` },
    body: await request.formData(),
  });
  return NextResponse.json(await response.json(), { status: response.status });
}
