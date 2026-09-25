/**
 * The admin console lives on a secret, unlinked path.
 *
 * It is deliberately *not* `/admin`: the route is never linked from any page,
 * carries `noindex`, and the backend additionally rejects any account whose
 * email is not on the `ADMIN_EMAILS` allowlist. Only the secret slug is public.
 */
export const ADMIN_PATH = "/pkay-control-x7q9";

/** Secret sign-in URL to deep-link an admin after the login redirect. */
export const ADMIN_LOGIN_PATH = `/login?next=${encodeURIComponent(ADMIN_PATH)}`;

export function adminRequestPath(id: string): string {
  return `${ADMIN_PATH}/requests/${encodeURIComponent(id)}`;
}
