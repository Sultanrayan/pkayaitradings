"""FastAPI gateway for Pkay TDAI.

Exposes health, market-data and analysis endpoints. The multi-agent pipeline is
built once during application startup and stored on ``app.state``.

Run with::

    uvicorn orchestrator.main:app --reload
"""

from __future__ import annotations

import secrets
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import (
    Depends,
    FastAPI,
    HTTPException,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field, field_validator
from starlette.responses import Response

from data_pipeline.biquote_feed import BiquoteTickFeed
from orchestrator import plans
from orchestrator.access import AccessRequestStore
from orchestrator.auth import (
    AuthError,
    User,
    UserStore,
    create_api_token,
    create_token,
    decode_token,
    sign_payload,
    verify_payload,
)
from orchestrator.billing import (
    PAYMENT_PAID,
    PAYMENT_PENDING,
    BillingPayment,
    BillingStore,
)
from orchestrator.community import router as community_router
from orchestrator.dev_api import router as dev_api_router
from orchestrator.oauth import build_authorization_url, exchange_code_for_identity
from orchestrator.pipeline import AnalysisPipeline, CycleResult, run_analysis_cycle
from orchestrator.raggrap import build_raggrap_engine, raggrap_router
from orchestrator.store import SignalRecord
from orchestrator.turnstile import verify_turnstile
from shared.circuit_breaker import CircuitOpenError
from shared.config import Settings, get_settings
from shared.email import EmailError, EmailSender, render_access_token_email
from shared.khpay import KhpayClient, KhpayError, build_khpay_client
from shared.logging import configure_logging, get_logger
from shared.schemas.enums import Impact, Timeframe
from shared.schemas.market import (
    CalendarEvent,
    MarketMover,
    MarketSummary,
    NewsArticle,
    OhlcSeries,
    Tick,
)
from shared.schemas.messages import Position
from shared.schemas.signals import (
    NewsSignal,
    RiskAssessment,
    TechnicalSignal,
    TradeDecision,
)

_logger = get_logger(__name__)

def _build_stores() -> tuple[UserStore, AccessRequestStore, BillingStore]:
    """Build the user, access-request and billing stores.

    When ``DATA_DIR`` is set (production mounts a volume there) the stores are
    persisted as JSON, so accounts, requests and payment intents survive
    restarts and redeploys. With no ``DATA_DIR`` they stay in memory
    (development and tests).
    """
    data_dir = get_settings().data_dir
    base = Path(data_dir) if data_dir else None
    return (
        UserStore(base / "users.json" if base else None),
        AccessRequestStore(base / "access_requests.json" if base else None),
        BillingStore(base / "billing_payments.json" if base else None),
    )


_users, _access_requests, _billing = _build_stores()
_bearer = HTTPBearer(auto_error=False)


def _email_sender() -> EmailSender:
    """Build a sender from the current settings (kept lazy so config changes apply)."""
    return EmailSender(get_settings())
_PUBLIC_API_PREFIXES = (
    "/api/v1/auth",
    "/api/v1/access/apply",
    "/api/v1/agents/capabilities",
    "/api/v1/billing/webhook",
)
# Only the health probe is reachable without auth. Interactive API docs and the
# OpenAPI schema are disabled unless EXPOSE_API_DOCS is explicitly enabled, so
# the endpoint surface is not published to the browser in production.
_PUBLIC_PATHS = frozenset({"/health"})


def _client_ip(request: Request) -> str | None:
    """Return the visitor IP, preferring Cloudflare's forwarded header."""
    forwarded = request.headers.get("cf-connecting-ip")
    if forwarded:
        return forwarded
    if request.client:
        return request.client.host
    return None


def _safe_redirect_path(next_path: str) -> str:
    """Return ``next_path`` when it is a safe same-origin relative path.

    Guards against open-redirects: only single-slash, non-API, relative paths
    are accepted. Anything else resolves to the default landing page.
    """
    if not next_path:
        return ""
    if not next_path.startswith("/") or next_path.startswith("//") or "\\" in next_path:
        return ""
    if next_path.startswith("/api/"):
        return ""
    return next_path


class HealthResponse(BaseModel):
    """Service health payload."""

    status: str = "ok"
    environment: str
    symbols: list[str]


class RegisterRequest(BaseModel):
    """Payload for creating an account."""

    name: str = Field(min_length=1, max_length=80)
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=128)
    turnstile_token: str = Field(default="", max_length=4096)

    @field_validator("email")
    @classmethod
    def _normalise_email(cls, value: str) -> str:
        normalised = value.strip().lower()
        local, _, domain = normalised.partition("@")
        if not local or "." not in domain:
            raise ValueError("Enter a valid email address")
        return normalised


class LoginRequest(BaseModel):
    """Payload for signing in."""

    email: str
    password: str


class UserResponse(BaseModel):
    """Public user representation (never includes the password hash)."""

    id: str
    name: str
    email: str
    created_at: datetime
    verified: bool = True
    plan: str = "free"
    plan_expires_at: datetime | None = None

    @classmethod
    def from_user(cls, user: User) -> UserResponse:
        """Build a response model from a stored user."""
        return cls(
            id=user.id,
            name=user.name,
            email=user.email,
            created_at=user.created_at,
            verified=user.verified,
            plan=user.plan,
            plan_expires_at=user.plan_expires_at,
        )


class AuthResponse(BaseModel):
    """A signed token plus the authenticated user."""

    token: str
    user: UserResponse


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    """Resolve the authenticated user from a bearer token."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = decode_token(credentials.credentials, get_settings().auth_secret)
    except AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    user = _users.get(str(payload.get("sub", "")))
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account not found")
    return user


class CycleResponse(BaseModel):
    """Serialised result of one analysis cycle."""

    symbol: str
    correlation_id: str
    technical: TechnicalSignal
    news: NewsSignal
    risk: RiskAssessment
    decision: TradeDecision


class SignalResponse(BaseModel):
    """A single recorded agent signal."""

    id: str
    correlation_id: str
    symbol: str
    agent: str
    kind: str
    direction: str
    confidence: float
    created_at: datetime
    payload: dict[str, Any]

    @classmethod
    def from_record(cls, record: SignalRecord) -> SignalResponse:
        """Build a response model from a store record."""
        return cls(
            id=record.id,
            correlation_id=record.correlation_id,
            symbol=record.symbol,
            agent=record.agent,
            kind=record.kind,
            direction=record.direction,
            confidence=record.confidence,
            created_at=record.created_at,
            payload=record.payload,
        )


class AgentStatusResponse(BaseModel):
    """Status and aggregate metrics for one agent."""

    name: str
    status: str
    signal_count: int
    avg_confidence: float
    last_signal_at: str | None


class AlertResponse(BaseModel):
    """A derived, user-facing alert."""

    id: str
    type: str
    priority: str
    symbol: str
    title: str
    detail: str
    created_at: str


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Build the pipeline on startup and release it on shutdown."""
    settings = get_settings()
    configure_logging(level=settings.log_level, json_logs=settings.log_json)
    _logger.info("api.startup", environment=settings.environment)
    app.state.settings = settings
    app.state.pipeline = await AnalysisPipeline.build(settings)
    app.state.rag_engine = build_raggrap_engine(settings) if settings.raggrap_enabled else None
    try:
        yield
    finally:
        await app.state.pipeline.close()
        if app.state.rag_engine is not None:
            app.state.rag_engine.close()
        _logger.info("api.shutdown")


_app_settings = get_settings()

app = FastAPI(
    title="Pkay TDAI",
    description=(
        "Multi-agent AI system for real-time Gold (XAUUSD) and Bitcoin (BTCUSD) market analysis."
    ),
    version="0.1.0",
    lifespan=lifespan,
    # Hidden by default: publishing /docs, /redoc or /openapi.json lets anyone
    # enumerate every endpoint from the browser. Set EXPOSE_API_DOCS=true to
    # re-enable them (development only).
    docs_url="/docs" if _app_settings.expose_api_docs else None,
    redoc_url="/redoc" if _app_settings.expose_api_docs else None,
    openapi_url="/openapi.json" if _app_settings.expose_api_docs else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(dev_api_router)
app.include_router(community_router)
if _app_settings.raggrap_enabled:
    app.include_router(raggrap_router)


@app.middleware("http")
async def enforce_auth(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """Require a bearer token for the API when ``auth_required`` is enabled."""
    settings = get_settings()
    path = request.url.path
    if settings.auth_required and path not in _PUBLIC_PATHS:
        protected = path.startswith("/api/") and not path.startswith(_PUBLIC_API_PREFIXES)
        if protected:
            header = request.headers.get("authorization", "")
            token = header[7:] if header.lower().startswith("bearer ") else ""
            try:
                payload = decode_token(token, settings.auth_secret)
            except AuthError:
                return JSONResponse(status_code=401, content={"detail": "Not authenticated"})
            if payload.get("scope") == "developer":
                # API access tokens may only reach the agent endpoints.
                if not path.startswith("/api/v1/agents/"):
                    return JSONResponse(
                        status_code=403,
                        content={"detail": "This token is only valid for the agent endpoints"},
                    )
    return await call_next(request)


@app.post(
    "/api/v1/auth/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["auth"],
    include_in_schema=False,
)
async def register(request: Request, body: RegisterRequest) -> AuthResponse:
    """Create an account and return a signed token."""
    if not await verify_turnstile(body.turnstile_token, remote_ip=_client_ip(request)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Security check failed. Please try again.",
        )
    try:
        user = _users.register(body.name, body.email, body.password)
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    settings = get_settings()
    token = create_token(user, settings.auth_secret, ttl_seconds=settings.auth_token_ttl_seconds)
    return AuthResponse(token=token, user=UserResponse.from_user(user))


@app.post("/api/v1/auth/login", response_model=AuthResponse, tags=["auth"], include_in_schema=False)
async def login(body: LoginRequest) -> AuthResponse:
    """Authenticate with email and password."""
    user = _users.authenticate(body.email, body.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
        )
    settings = get_settings()
    token = create_token(user, settings.auth_secret, ttl_seconds=settings.auth_token_ttl_seconds)
    return AuthResponse(token=token, user=UserResponse.from_user(user))


@app.get("/api/v1/auth/me", response_model=UserResponse, tags=["auth"], include_in_schema=False)
async def me(user: Annotated[User, Depends(get_current_user)]) -> UserResponse:
    """Return the authenticated user."""
    return UserResponse.from_user(user)


class AuthConfigResponse(BaseModel):
    """Which sign-in methods are available."""

    google: bool


@app.get(
    "/api/v1/auth/config", response_model=AuthConfigResponse, tags=["auth"], include_in_schema=False
)
async def auth_config() -> AuthConfigResponse:
    """Report the configured sign-in providers."""
    settings = get_settings()
    return AuthConfigResponse(
        google=bool(settings.google_client_id and settings.google_client_secret)
    )


@app.get("/api/v1/auth/google/login", tags=["auth"], include_in_schema=False)
async def google_login(
    request: Request,
    turnstile_token: str = Query(default=""),
    next: str = Query(default=""),
) -> RedirectResponse:
    """Redirect the browser to Google's consent screen.

    An optional ``next`` relative path (e.g. the admin console) is carried
    through the signed OAuth ``state`` so the browser returns there after
    authentication instead of the default dashboard.
    """
    settings = get_settings()
    if not await verify_turnstile(turnstile_token, remote_ip=_client_ip(request)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Security check failed. Please try again.",
        )
    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google sign-in is not configured",
        )
    state = sign_payload(
        {
            "nonce": secrets.token_urlsafe(16),
            "exp": int(time.time()) + 600,
            "next": _safe_redirect_path(next),
        },
        settings.auth_secret,
    )
    url = build_authorization_url(settings.google_client_id, settings.google_redirect_uri, state)
    return RedirectResponse(url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@app.get("/api/v1/auth/google/callback", tags=["auth"], include_in_schema=False)
async def google_callback(code: str, state: str) -> RedirectResponse:
    """Handle the Google redirect, then send the browser back to the frontend."""
    settings = get_settings()
    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google sign-in is not configured",
        )
    try:
        state_payload = verify_payload(state, settings.auth_secret)
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    try:
        identity = await exchange_code_for_identity(
            code=code,
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
            redirect_uri=settings.google_redirect_uri,
        )
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    user = _users.upsert_oauth(
        name=identity.name,
        email=identity.email,
        provider="google",
        subject=identity.subject,
    )
    token = create_token(user, settings.auth_secret, ttl_seconds=settings.auth_token_ttl_seconds)
    # Land the user straight back where they asked to go (the dashboard by
    # default, or an admin console deep-link carried through the OAuth state).
    # The session cookie is set by the server (reliable on mobile browsers,
    # where a #token fragment hand-off can get dropped mid redirect-chain),
    # then the Next.js middleware and the client both read it to authorise
    # API calls.
    next_path = _safe_redirect_path(str(state_payload.get("next") or ""))
    target = f"{settings.frontend_url}{next_path}" if next_path else f"{settings.frontend_url}/dashboard"
    redirect = RedirectResponse(target, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
    redirect.set_cookie(
        key="pkay_token",
        value=token,
        max_age=settings.auth_token_ttl_seconds,
        path="/",
        secure=True,
        httponly=False,
        samesite="lax",
    )
    return redirect



def get_current_admin(user: Annotated[User, Depends(get_current_user)]) -> User:
    """Allow only allow-listed admin accounts.

    The email allowlist lives in settings (``ADMIN_EMAILS``); any account whose
    address is not on it is rejected with 403.
    """
    settings = get_settings()
    allowlist = {email.lower() for email in settings.admin_emails}
    if user.email.lower() not in allowlist:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized for the admin area"
        )
    return user


AdminDep = Annotated[User, Depends(get_current_admin)]
UserDep = Annotated[User, Depends(get_current_user)]


class AdminSessionResponse(BaseModel):
    """Confirm the caller may use the admin area."""

    admin: bool
    email: str
    name: str


@app.get(
    "/api/v1/admin/session",
    response_model=AdminSessionResponse,
    tags=["admin"],
    include_in_schema=False,
)
async def admin_session(user: AdminDep) -> AdminSessionResponse:
    """Return the admin identity, or 403 when the caller is not an admin."""
    return AdminSessionResponse(admin=True, email=user.email, name=user.name)


class AdminUserResponse(BaseModel):
    """An account as shown in the admin users table."""

    id: str
    name: str
    email: str
    provider: str
    plan: str
    analysis_used: int
    plan_expires_at: datetime | None
    created_at: datetime

    @classmethod
    def from_user(cls, user: User) -> AdminUserResponse:
        return cls(
            id=user.id,
            name=user.name,
            email=user.email,
            provider=user.provider,
            plan=user.plan,
            analysis_used=user.analysis_used,
            plan_expires_at=user.plan_expires_at,
            created_at=user.created_at,
        )


class AdminStatsResponse(BaseModel):
    """High-level numbers for the admin overview."""

    total_users: int
    users_by_plan: dict[str, int]
    total_analyses: int
    total_requests: int
    pending_requests: int
    total_payments: int
    paid_payments: int


class AdminBillingResponse(BaseModel):
    """A billing payment as shown in the admin billing table."""

    payment_id: str
    user_email: str
    plan: str
    amount: float
    status: str
    created_at: datetime


@app.get(
    "/api/v1/admin/users",
    response_model=list[AdminUserResponse],
    tags=["admin"],
    include_in_schema=False,
)
async def admin_users(_: AdminDep) -> list[AdminUserResponse]:
    """List every registered account (admin only)."""
    return [AdminUserResponse.from_user(user) for user in _users.all()]


@app.get(
    "/api/v1/admin/stats",
    response_model=AdminStatsResponse,
    tags=["admin"],
    include_in_schema=False,
)
async def admin_stats(_: AdminDep) -> AdminStatsResponse:
    """Return summary numbers for the admin overview (admin only)."""
    users = _users.all()
    users_by_plan: dict[str, int] = {"free": 0, "pro": 0, "ultra": 0}
    for user in users:
        users_by_plan[user.plan] = users_by_plan.get(user.plan, 0) + 1
    requests = _access_requests.list()
    payments = _billing.list_all()
    return AdminStatsResponse(
        total_users=len(users),
        users_by_plan=users_by_plan,
        total_analyses=sum(user.analysis_used for user in users),
        total_requests=len(requests),
        pending_requests=sum(1 for item in requests if item.status == "pending"),
        total_payments=len(payments),
        paid_payments=sum(1 for item in payments if item.status == "paid"),
    )


@app.get(
    "/api/v1/admin/billing",
    response_model=list[AdminBillingResponse],
    tags=["admin"],
    include_in_schema=False,
)
async def admin_billing(_: AdminDep) -> list[AdminBillingResponse]:
    """List billing payments with the payer email (admin only)."""
    result: list[AdminBillingResponse] = []
    for payment in _billing.list_all():
        user = _users.get(payment.user_id)
        result.append(
            AdminBillingResponse(
                payment_id=payment.transaction_id,
                user_email=user.email if user else payment.user_id,
                plan=payment.plan,
                amount=payment.amount,
                status=payment.status,
                created_at=payment.created_at,
            )
        )
    return result


class ApplyRequest(BaseModel):
    """Payload for a developer access request."""

    name: str = Field(min_length=1, max_length=80)
    email: str = Field(min_length=3, max_length=254)
    use_case: str = Field(min_length=5, max_length=2000)
    website: str = Field(default="", max_length=300)
    turnstile_token: str = Field(default="", max_length=4096)

    @field_validator("email")
    @classmethod
    def _normalise_email(cls, value: str) -> str:
        normalised = value.strip().lower()
        local, _, domain = normalised.partition("@")
        if not local or "." not in domain:
            raise ValueError("Enter a valid email address")
        return normalised


class AccessRequestResponse(BaseModel):
    """A stored developer access request."""

    id: str
    name: str
    email: str
    use_case: str
    website: str
    status: str
    created_at: datetime
    reviewed_at: datetime | None = None
    token: str | None = None

    @classmethod
    def from_request(cls, request: Any) -> AccessRequestResponse:
        """Build a response model from a stored request."""
        return cls(
            id=request.id,
            name=request.name,
            email=request.email,
            use_case=request.use_case,
            website=request.website,
            status=str(request.status),
            created_at=request.created_at,
            reviewed_at=request.reviewed_at,
            token=request.token,
        )


@app.post("/api/v1/access/apply", status_code=status.HTTP_202_ACCEPTED, tags=["access"])
async def apply_for_access(request: Request, body: ApplyRequest) -> dict[str, str]:
    """Submit a request to use the developer API."""
    if not await verify_turnstile(body.turnstile_token, remote_ip=_client_ip(request)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Security check failed. Please try again.",
        )
    access_request = _access_requests.create(
        name=body.name, email=body.email, use_case=body.use_case, website=body.website
    )
    return {
        "status": "received",
        "id": access_request.id,
        "message": "Thank you for submitting! Your request is under review. Please allow 24 to 48 hours for approval.",
    }


@app.get(
    "/api/v1/admin/requests",
    response_model=list[AccessRequestResponse],
    tags=["admin"],
    include_in_schema=False,
)
async def admin_list_requests(_: AdminDep) -> list[AccessRequestResponse]:
    """List developer access requests (admin only)."""
    return [AccessRequestResponse.from_request(item) for item in _access_requests.list()]


@app.post(
    "/api/v1/admin/requests/{request_id}/approve",
    response_model=AccessRequestResponse,
    tags=["admin"],
    include_in_schema=False,
)
async def admin_approve_request(request_id: str, _: AdminDep) -> AccessRequestResponse:
    """Approve a request and email the developer their access token."""
    request = _access_requests.get(request_id)
    if request is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")
    settings = get_settings()
    token = create_api_token(
        email=request.email,
        name=request.name,
        secret=settings.auth_secret,
        ttl_seconds=365 * 24 * 3_600,
    )
    updated = _access_requests.approve(request_id, token)
    if updated is None:  # pragma: no cover - raced deletion
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")
    html = render_access_token_email(
        name=updated.name,
        token=token,
        api_base_url=settings.public_base_url,
        logo_url=settings.logo_url,
    )
    try:
        await _email_sender().send_async(
            to=updated.email, subject="Your Pkay TDAI API access token", html=html
        )
    except EmailError as exc:
        _logger.warning("email.access_token_failed", email=updated.email, error=repr(exc))
    return AccessRequestResponse.from_request(updated)


@app.post(
    "/api/v1/admin/requests/{request_id}/reject",
    response_model=AccessRequestResponse,
    tags=["admin"],
    include_in_schema=False,
)
async def admin_reject_request(request_id: str, _: AdminDep) -> AccessRequestResponse:
    """Reject a developer access request."""
    updated = _access_requests.reject(request_id)
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")
    return AccessRequestResponse.from_request(updated)


class CheckoutRequest(BaseModel):
    """Plan the user wants to purchase."""

    plan: Literal["pro", "ultra"]


class CheckoutResponse(BaseModel):
    """A freshly created KHQR payment."""

    payment_id: str
    plan: str
    amount: float
    qr_image: str
    qr_string: str
    payment_url: str
    status: str


class VerifyRequest(BaseModel):
    """A payment id to re-check."""

    payment_id: str


class VerifyResponse(BaseModel):
    """Outcome of verifying a payment."""

    paid: bool
    status: str
    plan: str | None = None


class PlanInfoResponse(BaseModel):
    """The user's current plan, usage and the plan catalogue."""

    plan: str
    limit: int
    used: int
    remaining: int
    active: bool
    expires_at: datetime | None
    price_usd: float | None
    limits: dict[str, int]
    prices: dict[str, float]


def _khpay_client(settings: Settings) -> KhpayClient | None:
    return build_khpay_client(settings.khpay_base_url, settings.khpay_api_key)


async def _activate_from_payment(
    intent: BillingPayment, user: User, settings: Settings
) -> VerifyResponse:
    """Mark a payment paid and upgrade the user's plan."""
    _billing.mark(intent.transaction_id, PAYMENT_PAID)
    user = plans.activate(user, intent.plan, settings)
    _users.update(user)
    _logger.info(
        "billing.plan_activated",
        user_id=user.id,
        plan=intent.plan,
        payment=intent.transaction_id,
    )
    return VerifyResponse(paid=True, status=PAYMENT_PAID, plan=intent.plan)


@app.post(
    "/api/v1/billing/checkout",
    response_model=CheckoutResponse,
    tags=["billing"],
    include_in_schema=False,
)
async def billing_checkout(body: CheckoutRequest, user: UserDep) -> CheckoutResponse:
    """Create a KHQR payment for a plan upgrade."""
    settings = get_settings()
    client = _khpay_client(settings)
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Payments are not configured",
        )
    price = plans.plan_price(body.plan, settings)
    if price is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown plan")
    try:
        payment = await client.create_payment(
            amount=price,
            note=f"Pkay TDAI {body.plan.title()} plan",
            callback_url=f"{settings.public_base_url}/api/v1/billing/webhook",
            client_id=user.id,
        )
    except KhpayError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    transaction_id = str(payment.get("transaction_id") or "")
    if not transaction_id:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="Khpay did not return a payment id"
        )
    _billing.create(
        BillingPayment(
            transaction_id=transaction_id,
            user_id=user.id,
            plan=body.plan,
            amount=price,
        )
    )
    return CheckoutResponse(
        payment_id=transaction_id,
        plan=body.plan,
        amount=price,
        qr_image=str(payment.get("qr_image") or ""),
        qr_string=str(payment.get("qr_string") or ""),
        payment_url=str(payment.get("payment_url") or ""),
        status=PAYMENT_PENDING,
    )


@app.post(
    "/api/v1/billing/verify",
    response_model=VerifyResponse,
    tags=["billing"],
    include_in_schema=False,
)
async def billing_verify(body: VerifyRequest, user: UserDep) -> VerifyResponse:
    """Re-check a payment against Khpay and activate the plan when paid."""
    settings = get_settings()
    intent = _billing.get(body.payment_id)
    if intent is None or intent.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")

    if intent.status != PAYMENT_PAID:
        client = _khpay_client(settings)
        if client is not None:
            try:
                info = await client.check_payment(body.payment_id)
            except KhpayError:
                info = {}
            if info.get("paid"):
                return await _activate_from_payment(intent, user, settings)

    current = _billing.get(body.payment_id)
    status_value = current.status if current is not None else intent.status
    return VerifyResponse(paid=status_value == PAYMENT_PAID, status=status_value, plan=intent.plan)


@app.get(
    "/api/v1/billing/plan",
    response_model=PlanInfoResponse,
    tags=["billing"],
    include_in_schema=False,
)
async def billing_plan(user: UserDep) -> PlanInfoResponse:
    """Return the user's plan, usage and the plan catalogue."""
    settings = get_settings()
    return _plan_info_response(user, settings)


@app.post(
    "/api/v1/billing/trial",
    response_model=PlanInfoResponse,
    tags=["billing"],
    include_in_schema=False,
)
async def billing_trial(user: UserDep) -> PlanInfoResponse:
    """Grant a free Pro trial (two months) via the "Pro plan" / "gifts" flow."""
    settings = get_settings()
    updated, granted = plans.activate_trial(user, settings)
    if granted:
        _users.update(updated)
        _logger.info(
            "billing.trial_activated",
            user_id=user.id,
            days=settings.plan_trial_days,
        )
    return _plan_info_response(updated, settings)


def _plan_info_response(user: User, settings: Settings) -> PlanInfoResponse:
    enforced = plans.enforce(user, settings)
    if enforced != user:
        _users.update(enforced)
    info = plans.status(enforced, settings)
    return PlanInfoResponse(
        plan=info.plan,
        limit=info.limit,
        used=info.used,
        remaining=info.remaining,
        active=info.active,
        expires_at=info.expires_at,
        price_usd=info.price_usd,
        limits={
            "free": settings.plan_free_monthly_limit,
            "pro": settings.plan_pro_monthly_limit,
            "ultra": settings.plan_ultra_monthly_limit,
        },
        prices={
            "pro": settings.plan_pro_price_usd,
            "ultra": settings.plan_ultra_price_usd,
        },
    )


@app.post(
    "/api/v1/billing/webhook",
    tags=["billing"],
    include_in_schema=False,
)
async def billing_webhook(request: Request) -> dict[str, object]:
    """Khpay payment notification; verifies server-side before activating."""
    try:
        body = await request.json()
    except Exception:
        return {"ok": False, "error": "invalid body"}
    if not isinstance(body, dict):
        return {"ok": False, "error": "invalid body"}

    transaction_id = _extract_transaction_id(body)
    if not transaction_id:
        return {"ok": False, "error": "missing transaction id"}
    intent = _billing.get(transaction_id)
    if intent is None:
        return {"ok": False, "error": "unknown payment"}
    if intent.status == PAYMENT_PAID:
        return {"ok": True}

    settings = get_settings()
    client = _khpay_client(settings)
    if client is not None:
        try:
            info = await client.check_payment(transaction_id)
        except KhpayError as exc:
            _logger.warning("billing.webhook_check_failed", error=repr(exc))
            info = {}
        if info.get("paid"):
            user = _users.get(intent.user_id)
            if user is not None:
                await _activate_from_payment(intent, user, settings)
                return {"ok": True, "plan": intent.plan}
    return {"ok": True}


def _extract_transaction_id(body: dict[str, Any]) -> str | None:
    """Pull a Khpay transaction id from common webhook payload shapes."""
    raw_data = body.get("data")
    data: dict[str, Any] = raw_data if isinstance(raw_data, dict) else body
    for key in ("transaction_id", "reference", "id"):
        value = data.get(key)
        if isinstance(value, str) and value.startswith("txn_"):
            return value
    for value in data.values():
        if isinstance(value, str) and value.startswith("txn_"):
            return value
    return None


def get_pipeline(request: Request) -> AnalysisPipeline:
    """Dependency returning the process-wide analysis pipeline."""
    pipeline: AnalysisPipeline | None = getattr(request.app.state, "pipeline", None)
    if pipeline is None:  # pragma: no cover - only before startup completes
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Pipeline is not initialised",
        )
    return pipeline


PipelineDep = Annotated[AnalysisPipeline, Depends(get_pipeline)]


def get_app_settings(request: Request) -> Settings:
    """Dependency returning the loaded settings."""
    return getattr(request.app.state, "settings", get_settings())


SettingsDep = Annotated[Settings, Depends(get_app_settings)]


@app.get("/health", response_model=HealthResponse, tags=["system"])
async def health(settings: SettingsDep) -> HealthResponse:
    """Liveness/readiness probe."""
    return HealthResponse(environment=settings.environment, symbols=settings.trading_symbols)


@app.get("/api/v1/tick/{symbol}", response_model=Tick, tags=["market"])
async def get_tick(
    symbol: str,
    pipeline: PipelineDep,
    allow_stale: Annotated[bool, Query()] = True,
) -> Tick:
    """Return the latest tick for ``symbol``."""
    try:
        return await pipeline.client.get_tick(symbol, allow_stale=allow_stale)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@app.get("/api/v1/ohlc/{symbol}", response_model=OhlcSeries, tags=["market"])
async def get_ohlc(
    symbol: str,
    pipeline: PipelineDep,
    interval: Annotated[Timeframe, Query()] = Timeframe.H1,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
) -> OhlcSeries:
    """Return OHLCV candles (oldest-first) for ``symbol``."""
    try:
        return await pipeline.client.get_ohlc(symbol, interval=interval, limit=limit)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


class AnalysisRequest(BaseModel):
    """Request body for the single `/v1/analysis` agent endpoint."""

    symbol: str = Field(min_length=1, max_length=20)
    timeframes: list[Timeframe] = Field(default_factory=list)


@app.post("/v1/analysis", response_model=CycleResponse, tags=["analysis"])
async def analysis(
    body: AnalysisRequest, pipeline: PipelineDep, user: UserDep
) -> CycleResponse:
    """Run the four agents on a symbol and return the combined analysis.

    This is the canonical single endpoint backed by all four agents:
    Technical Analyst, News Monitor, Risk Manager and Decision Maker. Requires a
    bearer token; each call consumes one analysis against the caller's plan.
    """
    settings = get_settings()
    consumption = plans.consume(user, settings)
    _users.update(consumption.user)
    if not consumption.allowed:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"{consumption.reason}. Upgrade your plan to continue.",
        )
    timeframes = body.timeframes or None
    result = await pipeline.run_cycle(body.symbol.upper(), timeframes)
    return _to_response(result)


@app.post("/api/v1/analyze/{symbol}", response_model=CycleResponse, tags=["analysis"])
async def analyze_symbol(
    symbol: str,
    pipeline: PipelineDep,
    user: UserDep,
    timeframes: Annotated[str | None, Query(description="Comma-separated timeframes")] = None,
) -> CycleResponse:
    """Run a full multi-agent analysis cycle for ``symbol``."""
    settings = get_settings()
    consumption = plans.consume(user, settings)
    _users.update(consumption.user)
    if not consumption.allowed:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"{consumption.reason}. Upgrade your plan to continue.",
        )
    parsed = _parse_timeframes(timeframes)
    try:
        result = await pipeline.run_cycle(symbol, parsed)
    except CircuitOpenError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return _to_response(result)


@app.get("/api/v1/positions", response_model=list[Position], tags=["execution"])
async def positions(pipeline: PipelineDep) -> list[Position]:
    """Return currently open paper positions."""
    executor = getattr(pipeline.decision, "executor", None)
    if executor is None:
        return []
    return list(await executor.positions())


@app.get("/api/v1/equity", response_model=float, tags=["execution"])
async def equity(pipeline: PipelineDep) -> float:
    """Return current paper-trading equity."""
    executor = getattr(pipeline.decision, "executor", None)
    if executor is None:
        return 0.0
    return float(await executor.equity())


@app.get("/api/v1/signals", response_model=list[SignalResponse], tags=["signals"])
async def list_signals(
    pipeline: PipelineDep,
    symbol: Annotated[str | None, Query()] = None,
    agent: Annotated[str | None, Query()] = None,
    direction: Annotated[str | None, Query()] = None,
    min_confidence: Annotated[float | None, Query(ge=0.0, le=1.0)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[SignalResponse]:
    """Return recorded agent signals, newest first."""
    records = pipeline.store.query(
        symbol=symbol,
        agent=agent,
        direction=direction,
        min_confidence=min_confidence,
        limit=limit,
    )
    return [SignalResponse.from_record(record) for record in records]


@app.get("/api/v1/agents", response_model=list[AgentStatusResponse], tags=["agents"])
async def list_agents(pipeline: PipelineDep) -> list[AgentStatusResponse]:
    """Return status and metrics for each agent."""
    return [AgentStatusResponse(**entry) for entry in pipeline.store.agent_status()]


@app.get("/api/v1/performance", tags=["analytics"])
async def performance(pipeline: PipelineDep) -> dict[str, Any]:
    """Return aggregate signal statistics."""
    return pipeline.store.stats()


@app.get("/api/v1/alerts", response_model=list[AlertResponse], tags=["alerts"])
async def list_alerts(
    pipeline: PipelineDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[AlertResponse]:
    """Return alerts derived from recorded signals."""
    return [AlertResponse(**alert) for alert in pipeline.store.alerts(limit=limit)]


@app.get("/api/v1/news", response_model=list[NewsArticle], tags=["news"])
async def get_news(
    pipeline: PipelineDep,
    symbol: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 15,
) -> list[NewsArticle]:
    """Return aggregated market news."""
    return await pipeline.client.get_news(symbol=symbol, max_results=limit)


@app.get("/api/v1/calendar", response_model=list[CalendarEvent], tags=["news"])
async def get_calendar(
    pipeline: PipelineDep,
    importance: Annotated[str | None, Query()] = None,
    countries: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[CalendarEvent]:
    """Return scheduled macroeconomic releases."""
    parsed_importance = _parse_importance(importance)
    parsed_countries = (
        [code.strip().upper() for code in countries.split(",") if code.strip()]
        if countries
        else None
    )
    return await pipeline.client.get_calendar(
        importance=parsed_importance,
        countries=parsed_countries,
        limit=limit,
    )


@app.get("/api/v1/market/movers", response_model=list[MarketMover], tags=["market"])
async def market_movers(
    pipeline: PipelineDep,
    kind: Annotated[str, Query(pattern="^(gainers|losers|most-active)$")] = "gainers",
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
) -> list[MarketMover]:
    """Return top gainers, losers or most-active symbols."""
    return await pipeline.client.get_market_movers(kind, limit=limit)


@app.get("/api/v1/market/summary", response_model=MarketSummary, tags=["market"])
async def market_summary(pipeline: PipelineDep) -> MarketSummary:
    """Return overall market breadth."""
    return await pipeline.client.get_market_summary()


class AnalyzeRequest(BaseModel):
    """Request body for the batch analysis endpoint."""

    symbols: list[str] = Field(default_factory=list)
    timeframes: list[Timeframe] = Field(default_factory=list)


@app.post("/api/v1/analyze", response_model=list[CycleResponse], tags=["analysis"])
async def analyze_batch(
    pipeline: PipelineDep, body: AnalyzeRequest, user: UserDep
) -> list[CycleResponse]:
    """Run analysis cycles for several symbols."""
    settings = get_settings()
    symbols = body.symbols or list(pipeline.settings.trading_symbols)
    consumption = plans.consume_many(user, settings, count=len(symbols))
    _users.update(consumption.user)
    if not consumption.allowed:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"{consumption.reason}. Upgrade your plan to continue.",
        )
    timeframes = body.timeframes or None
    results = []
    for symbol in symbols:
        result = await pipeline.run_cycle(symbol, timeframes)
        results.append(_to_response(result))
    return results


@app.websocket("/ws/ticks")
async def stream_ticks(websocket: WebSocket, symbols: str = "", token: str = "") -> None:
    """Stream live biquote ticks over a WebSocket.

    On connect the client receives a ``snapshot`` frame with the latest known
    price per symbol, then a ``tick`` frame for every update. Errors are
    reported as an ``error`` frame; the socket is then closed. When
    ``auth_required`` is enabled a valid ``token`` query parameter is required.
    """
    settings = get_settings()
    if settings.auth_required:
        try:
            decode_token(token, settings.auth_secret)
        except AuthError:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
    await websocket.accept()
    requested = [item.strip().upper() for item in symbols.split(",") if item.strip()]
    if not requested:
        requested = list(get_settings().trading_symbols)

    feed = BiquoteTickFeed(requested)
    try:
        await feed.start()
        snapshot = await feed.snapshot()
        await websocket.send_json(
            {
                "type": "snapshot",
                "symbols": requested,
                "ticks": {name: tick.model_dump(mode="json") for name, tick in snapshot.items()},
            }
        )
        async for tick in feed.stream():
            await websocket.send_json({"type": "tick", "tick": tick.model_dump(mode="json")})
    except WebSocketDisconnect:
        _logger.info("ws.ticks.disconnect", symbols=requested)
    except Exception as exc:
        _logger.warning("ws.ticks.error", symbols=requested, error=repr(exc))
        try:
            await websocket.send_json({"type": "error", "message": str(exc)})
            await websocket.close()
        except Exception:
            pass
    finally:
        await feed.stop()


def _parse_importance(raw: str | None) -> Impact | None:
    if not raw:
        return None
    try:
        return Impact(raw.strip().upper())
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc


def _parse_timeframes(raw: str | None) -> list[Timeframe] | None:
    if not raw:
        return None
    try:
        return [Timeframe(item.strip().upper()) for item in raw.split(",") if item.strip()]
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc


def _to_response(result: CycleResult) -> CycleResponse:
    return CycleResponse(
        symbol=result.symbol,
        correlation_id=result.correlation_id,
        technical=result.primary,
        news=result.news,
        risk=result.risk,
        decision=result.decision,
    )


__all__ = ["app", "run_analysis_cycle"]
