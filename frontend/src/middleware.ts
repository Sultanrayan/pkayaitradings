import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const AUTH_COOKIE = "pkay_token";

/** Pages anyone can view (the marketing pages and the auth flow). */
const PUBLIC_PATHS = [
  "/",
  "/pricing",
  "/how-it-works",
  "/api-reference",
  "/apply",
  "/login",
  "/register",
  "/auth/callback",
];

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

  const isPublic = PUBLIC_PATHS.some(
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
