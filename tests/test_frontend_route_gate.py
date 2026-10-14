"""The route gate in ``frontend/src/middleware.ts``.

``PUBLIC_PATHS`` was never updated when the docs moved to ``/docs``: it still listed
the old top-level ``/api-reference``. The middleware matches by prefix, so with no
``/docs`` entry the whole developer documentation site answered ``307`` into
``/login`` in production while every local check passed — nothing in the app
referenced ``/docs`` as public, so nothing failed.

Two properties matter and are easy to break in opposite directions:

* every real ``(marketing)``/``(auth)`` route must be reachable without a token;
* nothing private may be exposed by a public prefix (``/pricing/checkout`` sits
  under the public ``/pricing``).

These read the middleware source and the actual route tree, so a page added in
either direction shows up as a test failure.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "frontend/src/app"
MIDDLEWARE = ROOT / "frontend/src/middleware.ts"

#: Route groups that hold pages anyone may see. Everything else is console.
PUBLIC_GROUPS = {"(marketing)", "(auth)"}

#: Pages inside a public group that still need a signed-in caller.
PRIVATE_PAGES = {"/pricing/checkout", "/admin"}


def _source() -> str:
    return MIDDLEWARE.read_text(encoding="utf-8")


def _list_named(name: str) -> list[str]:
    """Extract a `const NAME = [...]` array of strings from the middleware."""
    match = re.search(rf"const {name}\s*=\s*\[(.*?)\]", _source(), re.DOTALL)
    assert match, f"{name} not found in middleware.ts"
    return re.findall(r'"([^"]+)"', match.group(1))


def _real_routes() -> set[str]:
    """Every route the app actually serves, derived from the filesystem."""
    out: set[str] = set()
    for page in APP.rglob("page.tsx"):
        rel = page.parent.relative_to(APP).as_posix()
        # Drop route-group segments: `(marketing)/docs` is the route `/docs`.
        parts = [p for p in rel.split("/") if not (p.startswith("(") and p.endswith(")"))]
        route = "/" + "/".join(parts)
        out.add(route.rstrip("/") or "/")
    return out


def _group_of(route: str) -> str | None:
    """The route group a route lives in, e.g. `(marketing)` for `/docs`."""
    page = None
    for candidate in APP.rglob("page.tsx"):
        rel = candidate.parent.relative_to(APP).as_posix()
        parts = [p for p in rel.split("/") if not (p.startswith("(") and p.endswith(")"))]
        if ("/" + "/".join(parts)).rstrip("/") == route:
            page = rel
            break
    if page is None:
        return None
    top = page.split("/")[0]
    return top if top.startswith("(") else None


def _is_public(pathname: str, publics: list[str], privates: list[str]) -> bool:
    if any(pathname == p or pathname.startswith(f"{p}/") for p in privates):
        return False
    return any(pathname == p or pathname.startswith(f"{p}/") for p in publics)


# ------------------------------------------------------------------ the bug


def test_docs_is_a_public_prefix() -> None:
    """The regression: without this, every docs page redirected into /login."""
    assert "/docs" in _list_named("PUBLIC_PATHS")


def test_learn_more_is_public() -> None:
    assert "/learn-more" in _list_named("PUBLIC_PATHS")


# ------------------------------------------------------------- nothing public hidden


def test_every_marketing_and_auth_route_is_reachable_without_a_token() -> None:
    publics = _list_named("PUBLIC_PATHS")
    privates = _list_named("PRIVATE_PATHS")
    hidden: list[str] = []
    for route in sorted(_real_routes()):
        group = _group_of(route)
        if group is None or group not in PUBLIC_GROUPS:
            continue
        if route in PRIVATE_PAGES:
            continue
        if not _is_public(route, publics, privates):
            hidden.append(route)
    assert not hidden, (
        f"these public-group routes would redirect to /login: {hidden}. "
        f"Add them to PUBLIC_PATHS in frontend/src/middleware.ts."
    )


# ------------------------------------------------------------ nothing private exposed


def test_checkout_stays_behind_a_login() -> None:
    publics = _list_named("PUBLIC_PATHS")
    privates = _list_named("PRIVATE_PATHS")
    assert "/pricing" in publics, "the pricing page itself is public"
    assert "/pricing/checkout" in privates, (
        "/pricing/checkout upgrades a plan; the /pricing prefix would expose it"
    )
    assert not _is_public("/pricing/checkout", publics, privates)


def test_admin_is_not_exposed_by_any_public_prefix() -> None:
    publics = _list_named("PUBLIC_PATHS")
    privates = _list_named("PRIVATE_PATHS")
    assert not _is_public("/admin", publics, privates)


# -------------------------------------------------------------- console stays closed


def test_console_routes_still_require_a_token() -> None:
    publics = _list_named("PUBLIC_PATHS")
    privates = _list_named("PRIVATE_PATHS")
    for route in ("/dashboard", "/signals", "/agents", "/settings", "/zenmux", "/charts"):
        assert route in _real_routes(), f"{route} no longer exists; update this test"
        assert not _is_public(route, publics, privates), f"{route} must require a token"


def test_the_admin_console_route_is_still_private() -> None:
    publics = _list_named("PUBLIC_PATHS")
    privates = _list_named("PRIVATE_PATHS")
    assert "/pkay-control-x7q9" in _real_routes()
    assert not _is_public("/pkay-control-x7q9", publics, privates)


def test_private_is_evaluated_before_public() -> None:
    """Order matters: a public prefix must not win over an explicit private entry."""
    source = _source()
    assert "PRIVATE_PATHS" in source
    assert "!isPrivate" in source, (
        "isPublic must be gated on !isPrivate, or a longer public prefix could "
        "override a private entry"
    )
    assert source.index("const isPrivate") < source.index("const isPublic")


def test_docs_subpages_resolve_through_the_docs_prefix() -> None:
    publics = _list_named("PUBLIC_PATHS")
    privates = _list_named("PRIVATE_PATHS")
    for route in ("/docs", "/docs/guides", "/docs/api-reference"):
        assert route in _real_routes(), f"{route} no longer exists; update this test"
        assert _is_public(route, publics, privates)