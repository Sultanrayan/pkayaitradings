"use client";

import { useState } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  Check,
  Copy,
  Globe,
  Loader2,
  Mail,
  ShieldCheck,
  X,
} from "lucide-react";
import { toast } from "sonner";
import { cn } from "cn";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { ErrorNote, LoadingRows, PageHeader } from "@/components/shared/primitives";
import { useAsyncData } from "@/hooks/use-async-data";
import { api } from "@/lib/api";
import { ADMIN_PATH } from "@/lib/admin";
import { formatDateTime } from "@/lib/format";
import type { AccessRequest, AccessRequestStatus } from "@/lib/types";

const STATUS_CLASS: Record<AccessRequestStatus, string> = {
  pending: "bg-amber-500/10 text-amber-400 ring-amber-500/30",
  approved: "bg-bull/10 text-bull ring-bull/30",
  rejected: "bg-bear/10 text-bear ring-bear/30",
};

export function AdminRequestDetail({ id }: { id: string }) {
  const { data: requests, loading, error: loadError } = useAsyncData<AccessRequest[]>(
    "adminRequests",
    () => api.adminRequests(),
    [],
  );
  const [updated, setUpdated] = useState<AccessRequest | null>(null);
  const [acting, setActing] = useState<"approve" | "reject" | null>(null);
  const [copied, setCopied] = useState(false);

  const request = updated ?? requests.find((item) => item.id === id) ?? null;
  const notFound = !loading && !loadError && request === null;

  const approve = async () => {
    setActing("approve");
    try {
      const result = await api.approveRequest(id);
      setUpdated(result);
      toast.success(`Access token emailed to ${result.email}`);
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Approval failed");
    } finally {
      setActing(null);
    }
  };

  const reject = async () => {
    setActing("reject");
    try {
      const result = await api.rejectRequest(id);
      setUpdated(result);
      toast.success("Request rejected");
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Rejection failed");
    } finally {
      setActing(null);
    }
  };

  const copyToken = async () => {
    if (!request?.token) return;
    try {
      await navigator.clipboard.writeText(request.token);
      setCopied(true);
      toast.success("Token copied");
      setTimeout(() => setCopied(false), 2000);
    } catch {
      toast.error("Could not copy the token");
    }
  };

  const back = (
    <Button asChild variant="ghost" size="sm" className="gap-1.5">
      <Link href={ADMIN_PATH}>
        <ArrowLeft className="size-4" />
        Back to requests
      </Link>
    </Button>
  );

  if (loadError || notFound) {
    return (
      <div className="space-y-4">
        {back}
        <ErrorNote>{loadError ?? "Request not found"}</ErrorNote>
      </div>
    );
  }

  if (!request) {
    return (
      <div className="space-y-6">
        <PageHeader title="Review request" />
        <LoadingRows rows={4} />
      </div>
    );
  }

  const pending = request.status === "pending";

  return (
    <div className="space-y-6">
      {back}

      <PageHeader
        title={request.name}
        description="Review this application and decide whether to grant access to the agent API."
        actions={
          <span
            className={cn(
              "inline-flex items-center rounded-full px-3 py-1 text-xs font-medium capitalize ring-1",
              STATUS_CLASS[request.status],
            )}
          >
            {request.status}
          </span>
        }
      />

      <div className="grid gap-6 lg:grid-cols-[2fr_1fr]">
        <div className="space-y-6">
          <Card className="bg-card ring-border">
            <CardHeader>
              <CardTitle className="text-sm font-medium">Intended use case</CardTitle>
              <CardDescription className="text-xs">
                What the developer plans to build with the endpoints on the API reference.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <p className="whitespace-pre-wrap text-sm leading-relaxed text-foreground/90">
                {request.use_case}
              </p>
            </CardContent>
          </Card>

          {request.token ? (
            <Card className="bg-card ring-border">
              <CardHeader>
                <CardTitle className="text-sm font-medium">Access token</CardTitle>
                <CardDescription className="text-xs">
                  Issued and emailed to {request.email}. Send it as{" "}
                  <code className="text-foreground/80">Authorization: Bearer &lt;token&gt;</code>.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="flex items-start gap-2 rounded-lg border border-border bg-muted/40 p-3">
                  <code className="flex-1 break-all font-mono text-xs text-bull">{request.token}</code>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    onClick={() => void copyToken()}
                    aria-label="Copy token"
                  >
                    {copied ? <Check className="size-4" /> : <Copy className="size-4" />}
                  </Button>
                </div>
              </CardContent>
            </Card>
          ) : null}
        </div>

        <div className="space-y-6">
          <Card className="bg-card ring-border">
            <CardHeader>
              <CardTitle className="text-sm font-medium">Applicant</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4 text-sm">
              <div className="flex items-start gap-3">
                <Mail className="mt-0.5 size-4 text-muted-foreground" />
                <div>
                  <div className="text-xs text-muted-foreground">Email</div>
                  <a href={`mailto:${request.email}`} className="underline-offset-4 hover:underline">
                    {request.email}
                  </a>
                </div>
              </div>
              <div className="flex items-start gap-3">
                <Globe className="mt-0.5 size-4 text-muted-foreground" />
                <div className="min-w-0">
                  <div className="text-xs text-muted-foreground">Website</div>
                  {request.website ? (
                    <a
                      href={request.website}
                      target="_blank"
                      rel="noreferrer"
                      className="break-all underline-offset-4 hover:underline"
                    >
                      {request.website}
                    </a>
                  ) : (
                    <span className="text-muted-foreground">Not provided</span>
                  )}
                </div>
              </div>
              <Separator />
              <div className="flex items-center justify-between text-xs text-muted-foreground">
                <span>Submitted</span>
                <span>{formatDateTime(request.created_at)}</span>
              </div>
              {request.reviewed_at ? (
                <div className="flex items-center justify-between text-xs text-muted-foreground">
                  <span>Reviewed</span>
                  <span>{formatDateTime(request.reviewed_at)}</span>
                </div>
              ) : null}
            </CardContent>
          </Card>

          <Card className="bg-card ring-border">
            <CardHeader>
              <CardTitle className="text-sm font-medium">Decision</CardTitle>
              <CardDescription className="text-xs">
                Approving issues a bearer token and emails it to the developer.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <Button
                className="w-full gap-2"
                onClick={() => void approve()}
                disabled={!pending || acting !== null}
              >
                {acting === "approve" ? (
                  <Loader2 className="size-4 animate-spin" />
                ) : (
                  <ShieldCheck className="size-4" />
                )}
                Approve &amp; send token
              </Button>
              <Button
                variant="outline"
                className="w-full gap-2 text-bear"
                onClick={() => void reject()}
                disabled={!pending || acting !== null}
              >
                {acting === "reject" ? (
                  <Loader2 className="size-4 animate-spin" />
                ) : (
                  <X className="size-4" />
                )}
                Reject request
              </Button>
              {!pending ? (
                <p className="text-center text-xs text-muted-foreground">
                  This request has already been {request.status}.
                </p>
              ) : null}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
