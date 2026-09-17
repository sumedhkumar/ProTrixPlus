/**
 * Edge-safe JWT payload decoding. No `next/headers`, no Node `Buffer` - usable
 * from middleware AND server components. The payload is NOT verified here; the
 * api verifies the signature for real on every call.
 */
import type { Role } from "./roles";
import { isRole } from "./roles";

export const TOKEN_COOKIE = "protrix_token";

export interface DecodedClaims {
  subject: string;
  role: Role;
  displayName: string;
  email: string;
  expiresAt: number;
}

function base64UrlDecode(input: string): string {
  const pad = input.length % 4 === 0 ? "" : "=".repeat(4 - (input.length % 4));
  const b64 = input.replace(/-/g, "+").replace(/_/g, "/") + pad;
  const bin = atob(b64);
  const bytes = Uint8Array.from(bin, (c) => c.charCodeAt(0));
  return new TextDecoder().decode(bytes);
}

export function decodeClaims(token: string | undefined | null): DecodedClaims | null {
  if (!token) return null;
  const parts = token.split(".");
  if (parts.length !== 3) return null;
  try {
    const payload = JSON.parse(base64UrlDecode(parts[1]!)) as Record<string, unknown>;
    const role = payload.role ?? payload["https://protrixplus/role"];
    if (!isRole(role) || typeof payload.sub !== "string") return null;
    return {
      subject: payload.sub,
      role,
      displayName: typeof (payload.name ?? payload["https://protrixplus/name"]) === "string" ? String(payload.name ?? payload["https://protrixplus/name"]) : "",
      email: typeof (payload.email ?? payload["https://protrixplus/email"]) === "string" ? String(payload.email ?? payload["https://protrixplus/email"]) : "",
      expiresAt: typeof payload.exp === "number" ? payload.exp : 0,
    };
  } catch {
    return null;
  }
}
