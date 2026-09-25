/** Authentication types and cookie helpers (shared by client and middleware). */

export interface AuthUser {
  id: string;
  name: string;
  email: string;
  created_at: string;
  verified: boolean;
  plan: string;
  plan_expires_at: string | null;
}

export interface AuthResponse {
  token: string;
  user: AuthUser;
}

/** Cookie name checked by the Next.js middleware. */
export const AUTH_COOKIE = "pkay_token";

/** Default token lifetime in seconds (matches the backend default). */
export const AUTH_MAX_AGE = 86_400;

export function readTokenCookie(): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(new RegExp(`(?:^|;\\s*)${AUTH_COOKIE}=([^;]+)`));
  return match ? decodeURIComponent(match[1]) : null;
}

export function writeTokenCookie(token: string, maxAgeSeconds: number = AUTH_MAX_AGE): void {
  if (typeof document === "undefined") return;
  document.cookie = `${AUTH_COOKIE}=${encodeURIComponent(token)}; path=/; max-age=${maxAgeSeconds}; samesite=lax`;
}

export function clearTokenCookie(): void {
  if (typeof document === "undefined") return;
  document.cookie = `${AUTH_COOKIE}=; path=/; max-age=0; samesite=lax`;
}
