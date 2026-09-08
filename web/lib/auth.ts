import { cookies } from "next/headers";

import { decodeClaims, TOKEN_COOKIE, type DecodedClaims } from "./claims";

export { TOKEN_COOKIE, decodeClaims };
export type { DecodedClaims };

/** Server-component / route-handler only (reads the request cookie jar). */
export function getToken(): string | undefined {
  return cookies().get(TOKEN_COOKIE)?.value;
}

export function getClaims(): DecodedClaims | null {
  return decodeClaims(getToken());
}
