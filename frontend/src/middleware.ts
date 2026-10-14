import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const AUTH_COOKIE = "pkay_token";

/**
 * Pages anyone can view: the marketing pages, the documentation, and the auth
 * flow.
 *
 * A prefix match counts, so `/docs` covers `/docs/guides` and
 * `/docs/api-reference`. Keep this list in step with the `(marketing)` and
 * `(auth)` route groups — a public page missing here is invisible behind a login
 * redirect, which is how the whole docs site ended up gated behind sign-in.
 */
const PUBLIC_PATHS = [
  "/",
  "/pricing",
  "/about",
  "/how-it-works",
  "/learn-more",
  "/docs",
  "/api-reference",
  "/apply",
  "/changelog",
  "/contact",
  "/status",
  "/privacy",
  "/terms",
  "/login",
  "/register",
  "/auth/callback",
];

/**
 * Always private, even when a prefix above would match. `/pricing/checkout` is
 * reached through the prefix rule from `/pricing`, but it upgrades a plan, so it
 * needs a signed-in caller. Checked before {@link PUBLIC_PATHS} so a longer public
 * prefix cannot quietly expose a private page.
 */
const PRIVATE_PATHS = ["/pricing/checkout", "/admin"];

/** Auth pages a signed-in user should be bounced away from. */
const AUTH_PAGES = ["/login", "/register"];

/**
 * TEMPORARILY DISABLED for local testing: set `AUTH_DISABLED=true` in
 * `.env.local` to bypass the login gate so pages (e.g. `/dashboard`) load
 * directly without sign-in. Remove that flag (or set it to `false`) to restore
 * the normal protected-console behaviour.
 */
const AUTH_DISABLED = process.env.AUTH_DISABLED === "true";

/**
 * Gate the console behind authentication while keeping the homepage public.
 *
 * Cookie presence is checked here for fast redirects; the backend validates the
 * token on every API call.
 */
export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Local testing shortcut: everything is reachable, no redirects.
  if (AUTH_DISABLED) {
    return NextResponse.next();
  }

  const hasToken = Boolean(request.cookies.get(AUTH_COOKIE)?.value);

  // An explicit private entry wins over any public prefix.
  const isPrivate = PRIVATE_PATHS.some(
    (path) => pathname === path || pathname.startsWith(`${path}/`),
  );

  const isPublic =
    !isPrivate &&
    PUBLIC_PATHS.some(
      (path) => pathname === path || pathname.startsWith(`${path}/`),
    );
  const isAuthPage = AUTH_PAGES.some(
    (path) => pathname === path || pathname.startsWith(`${path}/`),
  );

  if (!hasToken && !isPublic) {
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    url.search = "";
    if (pathname !== "/") url.searchParams.set("next", pathname);
    return NextResponse.redirect(url);
  }

  if (hasToken && isAuthPage) {
    const url = request.nextUrl.clone();
    url.pathname = "/dashboard";
    url.search = "";
    return NextResponse.redirect(url);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|.*\\.[\\w]+$).*)"],
};
