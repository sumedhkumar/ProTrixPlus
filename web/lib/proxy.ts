import { NextResponse } from "next/server";

import { getToken } from "@/lib/auth";

const API_URL = process.env.PROTRIX_API_URL ?? "http://localhost:8000";

/**
 * Forward an authenticated mutation from a client component to a *specific,
 * known* api path - never an open/arbitrary proxy. The api's own auth guard
 * (role checks, ownership checks) is still the real authorization boundary;
 * this just carries the httpOnly session cookie server-side, since client
 * components can't read it themselves.
 */
export async function proxyToApi(
  apiPath: string,
  method: "POST" | "PATCH" | "PUT" | "DELETE",
  req: Request,
): Promise<NextResponse> {
  const token = getToken();
  if (!token) {
    return NextResponse.json({ error: "not signed in" }, { status: 401 });
  }

  const body = await req.text();
  const res = await fetch(`${API_URL}${apiPath}`, {
    method,
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: body || undefined,
    cache: "no-store",
  });

  if (res.status === 204) {
    // A Response with a null-body status (204/205/304) must not be constructed
    // with a body init at all, even an empty string - Node's Response throws.
    return new NextResponse(null, { status: 204 });
  }

  const responseBody = await res.text();
  return new NextResponse(responseBody, {
    status: res.status,
    headers: { "Content-Type": res.headers.get("Content-Type") ?? "application/json" },
  });
}
