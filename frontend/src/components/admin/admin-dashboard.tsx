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
  Widget,
  WidgetGrid,
  WidgetRow,
  WidgetStatus,
  type WidgetSpec,
} from "@/components/ui/widget-grid";
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
  AgentStatus,
  Alert,
  HealthResponse,
  PerformanceStats,
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
/* Overview — draggable widget grid                                    */
/* ------------------------------------------------------------------ */

function AdminOverview() {
  const { data: stats, loading, error, reload } = useAsyncData<AdminStats>(
    "adminStats",
    () => api.adminStats(),
    EMPTY_STATS,
  );
  const { data: health, reload: reloadHealth } = useAsyncData<HealthResponse>(
    "adminHealth",
    () => api.health(),
    { status: "unknown", environment: "unknown", symbols: [] },
  );
  const { data: agents, reload: reloadAgents } = useAsyncData<AgentStatus[]>(
    "adminAgents",
    () => api.agents(),
    [],
  );
  const { data: alerts, reload: reloadAlerts } = useAsyncData<Alert[]>(
    "adminAlerts",
    () => api.alerts(6),
    [],
  );
  const { data: performance, reload: reloadPerf } = useAsyncData<PerformanceStats | null>(
    "adminPerformance",
    () => api.performance(),
    null,
  );

  const refreshAll = () => {
    reload();
    reloadHealth();
    reloadAgents();
    reloadAlerts();
    reloadPerf();
  };

  const planBreakdown = useMemo(
    () => [
      { label: "Free", value: stats.users_by_plan.free ?? 0 },
      { label: "Starter", value: stats.users_by_plan.starter ?? 0 },
      { label: "Pro", value: stats.users_by_plan.pro ?? 0 },
      { label: "Ultra", value: stats.users_by_plan.ultra ?? 0 },
    ],
    [stats],
  );

  const conversion = stats.total_users > 0
    ? ((planBreakdown[1].value + planBreakdown[2].value) / stats.total_users)
    : 0;

  const healthy = health.status === "ok" || health.status === "healthy";
  const agentsDown = agents.filter((agent) => agent.status === "error").length;

  const widgets: WidgetSpec[] = [
    {
      id: "system",
      children: (
        <Widget title="System status" meta={health.environment}>
          <div className="text-2xl font-semibold leading-none">
            {health.status.toUpperCase()}
          </div>
          <WidgetStatus tone={healthy ? "bull" : "bear"}>
            {healthy
              ? `Serving ${health.symbols.length} symbol${health.symbols.length === 1 ? "" : "s"}`
              : "Backend unreachable"}
          </WidgetStatus>
        </Widget>
      ),
    },
    {
      id: "users",
      children: (
        <Widget title="Total users" meta="all time">
          <div className="text-2xl font-semibold leading-none tabular">{stats.total_users}</div>
          <WidgetStatus tone="flat">
            {`${conversion > 0 ? (conversion * 100).toFixed(0) : 0}% on a paid plan`}
          </WidgetStatus>
        </Widget>
      ),
    },
    {
      id: "plans",
      span: "xl:col-span-2",
      children: (
        <Widget title="Plan distribution" meta={`${stats.total_users} accounts`}>
          <div className="space-y-1">
            {planBreakdown.map((item) => (
              <WidgetRow
                key={item.label}
                label={item.label}
                value={item.value}
                progress={
                  stats.total_users > 0 ? item.value / stats.total_users : 0
                }
              />
            ))}
          </div>
        </Widget>
      ),
    },
    {
      id: "agents",
      children: (
        <Widget title="Agents" meta="live">
          <div className="text-2xl font-semibold leading-none tabular">
            {agents.length - agentsDown}/{agents.length}
          </div>
          <WidgetStatus tone={agentsDown > 0 ? "bear" : "bull"}>
            {agentsDown > 0 ? `${agentsDown} agent(s) erroring` : "All agents operational"}
          </WidgetStatus>
        </Widget>
      ),
    },
    {
      id: "agents-detail",
      span: "xl:col-span-2",
      children: (
        <Widget title="Agent activity" meta="signal count">
          {agents.length === 0 ? (
            <p className="text-[11px] text-muted-foreground">No agent data.</p>
          ) : (
            <div className="space-y-1">
              {agents.map((agent) => (
                <WidgetRow
                  key={agent.name}
                  label={agent.name}
                  value={agent.signal_count}
                  progress={
                    Math.max(...agents.map((a) => a.signal_count), 1) > 0
                      ? agent.signal_count /
                        Math.max(...agents.map((a) => a.signal_count), 1)
                      : 0
                  }
                />
              ))}
            </div>
          )}
        </Widget>
      ),
    },
    {
      id: "analyses",
      children: (
        <Widget title="Analyses" meta="all time">
          <div className="text-2xl font-semibold leading-none tabular">
            {stats.total_analyses}
          </div>
          <WidgetStatus tone="flat">
            {performance
              ? `Avg confidence ${(performance.avg_confidence * 100).toFixed(0)}%`
              : "Confidence unavailable"}
          </WidgetStatus>
        </Widget>
      ),
    },
    {
      id: "signals",
      children: (
        <Widget title="Signal mix" meta="all time">
          {performance ? (
            <div className="space-y-1">
              <WidgetRow
                label="Bullish"
                value={performance.bullish}
                progress={
                  performance.total_signals > 0
                    ? performance.bullish / performance.total_signals
                    : 0
                }
              />
              <WidgetRow
                label="Bearish"
                value={performance.bearish}
                progress={
                  performance.total_signals > 0
                    ? performance.bearish / performance.total_signals
                    : 0
                }
              />
              <WidgetRow
                label="Neutral"
                value={performance.neutral}
                progress={
                  performance.total_signals > 0
                    ? performance.neutral / performance.total_signals
                    : 0
                }
              />
            </div>
          ) : (
            <p className="text-[11px] text-muted-foreground">No performance data.</p>
          )}
        </Widget>
      ),
    },
    {
      id: "requests",
      children: (
        <Widget title="Access requests" meta="all time">
          <div className="text-2xl font-semibold leading-none tabular">
            {stats.total_requests}
          </div>
          <WidgetStatus tone={stats.pending_requests > 0 ? "bear" : "bull"}>
            {stats.pending_requests > 0
              ? `${stats.pending_requests} awaiting review`
              : "Nothing awaiting review"}
          </WidgetStatus>
        </Widget>
      ),
    },
    {
      id: "billing",
      children: (
        <Widget title="Payments" meta="all time">
          <div className="text-2xl font-semibold leading-none tabular">
            {stats.paid_payments}/{stats.total_payments}
          </div>
          <WidgetStatus tone="flat">Confirmed payments</WidgetStatus>
        </Widget>
      ),
    },
    {
      id: "alerts",
      span: "xl:col-span-2",
      children: (
        <Widget title="Recent alerts" meta="latest">
          {alerts.length === 0 ? (
            <p className="text-[11px] text-muted-foreground">No alerts recorded.</p>
          ) : (
            <div className="space-y-1">
              {alerts.map((alert) => (
                <WidgetRow
                  key={alert.id}
                  label={`${alert.symbol} · ${alert.title}`}
                  value={formatDateTime(alert.created_at)}
                />
              ))}
            </div>
          )}
        </Widget>
      ),
    },
  ];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">Service health at a glance.</p>
        <Button variant="outline" size="sm" className="gap-1.5" onClick={refreshAll} disabled={loading}>
          <RefreshCw className={cn("size-4", loading && "animate-spin")} />
          Refresh
        </Button>
      </div>

      {error ? <ErrorNote>{error}</ErrorNote> : null}

      <WidgetGrid widgets={widgets} hint="Drag and rearrange widgets to customize the layout." />
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