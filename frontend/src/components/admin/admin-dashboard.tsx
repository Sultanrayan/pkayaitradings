"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import {
  ArrowRight,
  CheckCircle2,
  Clock,
  CreditCard,
  Inbox,
  LayoutDashboard,
  RefreshCw,
  Users,
  XCircle,
  type LucideIcon,
} from "lucide-react";
import { cn } from "cn";

import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  EmptyState,
  ErrorNote,
  LoadingRows,
  PageHeader,
  StatCard,
  TonePill,
} from "@/components/shared/primitives";
import { useAsyncData } from "@/hooks/use-async-data";
import { api } from "@/lib/api";
import { adminRequestPath } from "@/lib/admin";
import { formatDateTime } from "@/lib/format";
import type { Tone } from "@/lib/format";
import type {
  AccessRequest,
  AccessRequestStatus,
  AdminBilling,
  AdminStats,
  AdminUser,
} from "@/lib/types";

type Tab = "overview" | "users" | "requests" | "billing";

const TABS: { id: Tab; label: string; icon: LucideIcon }[] = [
  { id: "overview", label: "Overview", icon: LayoutDashboard },
  { id: "users", label: "Users", icon: Users },
  { id: "requests", label: "Access requests", icon: Inbox },
  { id: "billing", label: "Billing", icon: CreditCard },
];

const EMPTY_STATS: AdminStats = {
  total_users: 0,
  users_by_plan: {},
  total_analyses: 0,
  total_requests: 0,
  pending_requests: 0,
  total_payments: 0,
  paid_payments: 0,
};

const PLAN_TONE: Record<string, Tone> = {
  free: "flat",
  pro: "bull",
  ultra: "bull",
};

export function AdminDashboard() {
  const [tab, setTab] = useState<Tab>("overview");

  return (
    <div className="space-y-6">
      <PageHeader
        title="Admin dashboard"
        description="Manage accounts, plans, access requests and payments. Access is restricted to the allow-listed Google account."
      />

      <div className="flex flex-wrap items-center gap-2">
        {TABS.map((item) => {
          const Icon = item.icon;
          return (
            <Button
              key={item.id}
              variant={tab === item.id ? "default" : "outline"}
              size="sm"
              className="gap-1.5"
              onClick={() => setTab(item.id)}
            >
              <Icon className="size-3.5" />
              {item.label}
            </Button>
          );
        })}
      </div>

      {tab === "overview" ? <AdminOverview /> : null}
      {tab === "users" ? <AdminUsers /> : null}
      {tab === "requests" ? <AdminRequests /> : null}
      {tab === "billing" ? <AdminBilling /> : null}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Overview                                                            */
/* ------------------------------------------------------------------ */
function AdminOverview() {
  const { data: stats, loading, error, reload } = useAsyncData<AdminStats>(
    "adminStats",
    () => api.adminStats(),
    EMPTY_STATS,
  );

  const planBreakdown = useMemo(
    () => [
      { label: "Free", value: stats.users_by_plan.free ?? 0 },
      { label: "Pro", value: stats.users_by_plan.pro ?? 0 },
      { label: "Ultra", value: stats.users_by_plan.ultra ?? 0 },
    ],
    [stats],
  );

  const cards: { label: string; value: number; icon: LucideIcon; hint: string }[] = [
    { label: "Total users", value: stats.total_users, icon: Users, hint: "Registered accounts" },
    { label: "Pro", value: planBreakdown[1].value, icon: CheckCircle2, hint: "Pro accounts" },
    { label: "Ultra", value: planBreakdown[2].value, icon: CreditCard, hint: "Ultra accounts" },
    { label: "Analyses", value: stats.total_analyses, icon: LayoutDashboard, hint: "All-time" },
    { label: "Pending requests", value: stats.pending_requests, icon: Clock, hint: "Awaiting review" },
    { label: "Paid payments", value: stats.paid_payments, icon: CheckCircle2, hint: "Confirmed" },
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">Service health at a glance.</p>
        <Button variant="outline" size="sm" className="gap-1.5" onClick={reload} disabled={loading}>
          <RefreshCw className={cn("size-4", loading && "animate-spin")} />
          Refresh
        </Button>
      </div>

      {error ? <ErrorNote>{error}</ErrorNote> : null}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {cards.map((card) => (
          <StatCard
            key={card.label}
            label={card.label}
            value={card.value}
            hint={card.hint}
            icon={<card.icon className="size-4" />}
          />
        ))}
      </div>

      <div className="rounded-xl border border-border bg-card p-6">
        <h2 className="text-sm font-medium tracking-wide">Plan distribution</h2>
        <div className="mt-4 grid grid-cols-3 gap-4">
          {planBreakdown.map((item) => (
            <div key={item.label} className="rounded-lg border border-border bg-muted/30 p-4 text-center">
              <div className="text-2xl font-semibold tabular">{item.value}</div>
              <div className="mt-1 text-[11px] uppercase tracking-wider text-muted-foreground">
                {item.label}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Users                                                               */
/* ------------------------------------------------------------------ */
function AdminUsers() {
  const { data: users, loading, error, reload } = useAsyncData<AdminUser[]>(
    "adminUsers",
    () => api.adminUsers(),
    [],
  );

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          {users.length} registered account{users.length === 1 ? "" : "s"}.
        </p>
        <Button variant="outline" size="sm" className="gap-1.5" onClick={reload} disabled={loading}>
          <RefreshCw className={cn("size-4", loading && "animate-spin")} />
          Refresh
        </Button>
      </div>

      {error ? <ErrorNote>{error}</ErrorNote> : null}

      <div className="rounded-xl border border-border bg-card">
        {loading && users.length === 0 ? (
          <div className="p-4">
            <LoadingRows rows={6} />
          </div>
        ) : users.length === 0 ? (
          <div className="p-4">
            <EmptyState>No accounts yet.</EmptyState>
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Account</TableHead>
                <TableHead>Plan</TableHead>
                <TableHead>Analyses</TableHead>
                <TableHead>Plan expiry</TableHead>
                <TableHead>Joined</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {users.map((user) => (
                <TableRow key={user.id}>
                  <TableCell>
                    <div className="font-medium text-foreground">{user.name}</div>
                    <div className="text-xs text-muted-foreground">{user.email}</div>
                  </TableCell>
                  <TableCell>
                    <TonePill label={user.plan} tone={PLAN_TONE[user.plan] ?? "flat"} />
                  </TableCell>
                  <TableCell className="tabular text-sm text-muted-foreground">
                    {user.analysis_used}
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {user.plan_expires_at ? formatDateTime(user.plan_expires_at) : "—"}
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {formatDateTime(user.created_at)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Access requests                                                     */
/* ------------------------------------------------------------------ */
type Filter = "all" | AccessRequestStatus;

const FILTERS: { id: Filter; label: string }[] = [
  { id: "all", label: "All" },
  { id: "pending", label: "Pending" },
  { id: "approved", label: "Approved" },
  { id: "rejected", label: "Rejected" },
];

const STATUS_TONE: Record<AccessRequestStatus, Tone> = {
  pending: "flat",
  approved: "bull",
  rejected: "bear",
};

function AdminRequests() {
  const { data: requests, loading, error, reload } = useAsyncData<AccessRequest[]>(
    "adminRequests",
    () => api.adminRequests(),
    [],
  );
  const [filter, setFilter] = useState<Filter>("all");

  const counts = useMemo(() => {
    const base = { total: 0, pending: 0, approved: 0, rejected: 0 };
    for (const request of requests) {
      base.total += 1;
      base[request.status] += 1;
    }
    return base;
  }, [requests]);

  const visible = useMemo(
    () => requests.filter((request) => filter === "all" || request.status === filter),
    [requests, filter],
  );

  const stats: { label: string; value: number; icon: LucideIcon; hint: string }[] = [
    { label: "Total requests", value: counts.total, icon: Inbox, hint: "All-time applications" },
    { label: "Pending", value: counts.pending, icon: Clock, hint: "Awaiting review" },
    { label: "Approved", value: counts.approved, icon: CheckCircle2, hint: "Tokens issued" },
    { label: "Rejected", value: counts.rejected, icon: XCircle, hint: "Declined" },
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          Approving emails the requester a bearer token for the agent endpoints.
        </p>
        <Button variant="outline" size="sm" className="gap-1.5" onClick={reload} disabled={loading}>
          <RefreshCw className={cn("size-4", loading && "animate-spin")} />
          Refresh
        </Button>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {stats.map((stat) => (
          <StatCard
            key={stat.label}
            label={stat.label}
            value={stat.value}
            hint={stat.hint}
            icon={<stat.icon className="size-4" />}
          />
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {FILTERS.map((item) => (
          <Button
            key={item.id}
            variant={filter === item.id ? "default" : "outline"}
            size="sm"
            onClick={() => setFilter(item.id)}
          >
            {item.label}
          </Button>
        ))}
      </div>

      {error ? <ErrorNote>{error}</ErrorNote> : null}

      <div className="rounded-xl border border-border bg-card">
        {loading && requests.length === 0 ? (
          <div className="p-4">
            <LoadingRows rows={5} />
          </div>
        ) : visible.length === 0 ? (
          <div className="p-4">
            <EmptyState>No requests in this view yet.</EmptyState>
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Applicant</TableHead>
                <TableHead>Website</TableHead>
                <TableHead>Submitted</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Action</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {visible.map((request) => (
                <TableRow key={request.id}>
                  <TableCell>
                    <div className="font-medium text-foreground">{request.name}</div>
                    <div className="text-xs text-muted-foreground">{request.email}</div>
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {request.website ? (
                      <a
                        href={request.website}
                        target="_blank"
                        rel="noreferrer"
                        className="underline-offset-4 hover:underline"
                      >
                        {request.website.replace(/^https?:\/\//, "")}
                      </a>
                    ) : (
                      "—"
                    )}
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {formatDateTime(request.created_at)}
                  </TableCell>
                  <TableCell>
                    <TonePill label={request.status} tone={STATUS_TONE[request.status]} />
                  </TableCell>
                  <TableCell className="text-right">
                    <Button asChild variant="ghost" size="sm" className="gap-1.5">
                      <Link href={adminRequestPath(request.id)}>
                        Review
                        <ArrowRight className="size-3.5" />
                      </Link>
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Billing                                                             */
/* ------------------------------------------------------------------ */
function AdminBilling() {
  const { data: payments, loading, error, reload } = useAsyncData<AdminBilling[]>(
    "adminBilling",
    () => api.adminBilling(),
    [],
  );

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          {payments.length} payment{payments.length === 1 ? "" : "s"} recorded.
        </p>
        <Button variant="outline" size="sm" className="gap-1.5" onClick={reload} disabled={loading}>
          <RefreshCw className={cn("size-4", loading && "animate-spin")} />
          Refresh
        </Button>
      </div>

      {error ? <ErrorNote>{error}</ErrorNote> : null}

      <div className="rounded-xl border border-border bg-card">
        {loading && payments.length === 0 ? (
          <div className="p-4">
            <LoadingRows rows={5} />
          </div>
        ) : payments.length === 0 ? (
          <div className="p-4">
            <EmptyState>No payments yet.</EmptyState>
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Payer</TableHead>
                <TableHead>Plan</TableHead>
                <TableHead>Amount</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Created</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {payments.map((payment) => (
                <TableRow key={payment.payment_id}>
                  <TableCell>
                    <div className="text-xs text-muted-foreground">{payment.user_email}</div>
                    <div className="font-mono text-xs text-foreground">{payment.payment_id}</div>
                  </TableCell>
                  <TableCell>
                    <TonePill label={payment.plan} tone={PLAN_TONE[payment.plan] ?? "flat"} />
                  </TableCell>
                  <TableCell className="tabular text-sm text-foreground">
                    ${payment.amount.toFixed(2)}
                  </TableCell>
                  <TableCell>
                    <TonePill
                      label={payment.status}
                      tone={payment.status === "paid" ? "bull" : payment.status === "pending" ? "flat" : "bear"}
                    />
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {formatDateTime(payment.created_at)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </div>
    </div>
  );
}