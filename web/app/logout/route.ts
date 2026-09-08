import { NextResponse } from "next/server";

import { TOKEN_COOKIE } from "@/lib/auth";

export function GET(req: Request) {
  const res = NextResponse.redirect(new URL("/login", req.url));
  res.cookies.set(TOKEN_COOKIE, "", { httpOnly: true, path: "/", maxAge: 0 });
  return res;
}
