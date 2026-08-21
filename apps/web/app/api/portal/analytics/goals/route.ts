import { NextRequest, NextResponse } from "next/server";

export async function PUT(request: NextRequest) {
  const response = await fetch(
    `${process.env.FOUNDATION_API_URL ?? "http://127.0.0.1:8001"}/api/v1/analytics/goals`,
    {
      method: "PUT",
      headers: {
        authorization: `Bearer ${process.env.FOUNDATION_ADMIN_TOKEN ?? ""}`,
        "content-type": "application/json",
      },
      body: JSON.stringify(await request.json()),
    },
  );
  return NextResponse.json(await response.json(), { status: response.status });
}
