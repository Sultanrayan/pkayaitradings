"use client";

import { useState } from "react";

import { CodeBlock } from "@/components/docs/code-block";
import { CopyButton } from "@/components/docs/copy-button";
import { API_ORIGIN, type ApiEndpoint } from "@/components/docs/docs-endpoints";
import { Button } from "@/components/ui/button";
import { cn } from "cn";

const METHOD_STYLE: Record<ApiEndpoint["method"], string> = {
  GET: "text-foreground",
  POST: "text-foreground",
};

function TryItPanel({ endpoint }: { endpoint: ApiEndpoint }) {
  const [params, setParams] = useState(
    endpoint.params.map((param) => `${param.name}=${param.example}`).join("&"),
  );
  const [token, setToken] = useState("YOUR_API_TOKEN");
  const [sent, setSent] = useState(false);

  // Paths are absolute from the origin, so `/health` does not become
  // `/api/v1/health` here.
  const requestUrl = `${API_ORIGIN}${endpoint.path}`;

  return (
    <div className="mt-2 rounded-lg border border-border bg-muted/30 p-4">
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="block">
          <span className="mb-1 block text-xs font-medium text-muted-foreground">Endpoint</span>
          <input
            readOnly
            value={requestUrl}
            className="h-8 w-full rounded-md border border-border bg-background px-2.5 font-mono text-xs text-foreground"
          />
        </label>

        <label className="block">
          <span className="mb-1 block text-xs font-medium text-muted-foreground">Method</span>
          <input
            readOnly
            value={endpoint.method}
            className="h-8 w-full rounded-md border border-border bg-background px-2.5 font-mono text-xs text-foreground"
          />
        </label>

        <label className="block">
          <span className="mb-1 block text-xs font-medium text-muted-foreground">Parameters</span>
          <input
            value={params}
            onChange={(event) => setParams(event.target.value)}
            placeholder="No parameters"
            className="h-8 w-full rounded-md border border-border bg-background px-2.5 font-mono text-xs text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          />
        </label>

        <label className="block">
          <span className="mb-1 block text-xs font-medium text-muted-foreground">Authorization</span>
          <input
            value={token}
            onChange={(event) => setToken(event.target.value)}
            className="h-8 w-full rounded-md border border-border bg-background px-2.5 font-mono text-xs text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          />
        </label>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-3">
        <Button size="sm" onClick={() => setSent(true)}>
          Send Request
        </Button>
        <p className="text-xs text-muted-foreground">
          Shows a sample payload — this panel does not call the live service.
        </p>
      </div>

      {sent ? (
        <div className="mt-4 border-t border-border pt-4">
          <div className="mb-2 flex items-center gap-2">
            <span className="text-xs font-medium text-muted-foreground">Response JSON</span>
            <span className="rounded border border-border bg-muted px-1.5 py-0.5 font-mono text-[11px] text-foreground">
              Status: 200 OK
            </span>
            <CopyButton value={endpoint.sampleResponse} className="ml-auto" />
          </div>
          <CodeBlock code={endpoint.sampleResponse} />
        </div>
      ) : null}
    </div>
  );
}

export interface EndpointTableProps {
  endpoints: ApiEndpoint[];
  className?: string;
}

/**
 * Reference table of endpoints.
 *
 * "Try it" expands in place beneath the row rather than opening a dialog, so the
 * request stays visually attached to the endpoint it belongs to.
 */
export function EndpointTable({ endpoints, className }: EndpointTableProps) {
  const [openId, setOpenId] = useState<string | null>(null);

  return (
    <div className={cn("overflow-hidden rounded-lg border border-border", className)}>
      <ul>
        {endpoints.map((endpoint, index) => {
          const open = openId === endpoint.id;
          return (
            <li
              key={endpoint.id}
              id={endpoint.id}
              className={cn(
                "scroll-mt-24",
                index > 0 && "border-t border-border",
              )}
            >
              <div className="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3">
                <span
                  className={cn(
                    "w-11 shrink-0 font-mono text-xs font-medium",
                    METHOD_STYLE[endpoint.method],
                  )}
                >
                  {endpoint.method}
                </span>

                <code className="min-w-0 flex-1 truncate font-mono text-[13px] text-foreground">
                  {endpoint.path}
                </code>

                <span className="hidden text-xs text-muted-foreground sm:inline">
                  {endpoint.summary}
                </span>

                <button
                  type="button"
                  onClick={() => setOpenId(open ? null : endpoint.id)}
                  aria-expanded={open}
                  className="ml-auto shrink-0 rounded-md border border-border px-2 py-1 text-xs font-medium transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:ml-0"
                >
                  {open ? "Close" : "Try it"}
                </button>
              </div>

              <p className="px-4 pb-3 text-xs leading-5 text-muted-foreground sm:hidden">
                {endpoint.summary}
              </p>

              {open ? (
                <div className="px-4 pb-4">
                  <p className="mb-3 text-[13px] leading-6 text-muted-foreground">
                    {endpoint.description}
                  </p>
                  <TryItPanel endpoint={endpoint} />
                </div>
              ) : null}
            </li>
          );
        })}
      </ul>
    </div>
  );
}