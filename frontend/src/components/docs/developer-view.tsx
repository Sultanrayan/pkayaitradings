"use client";

import { ArticleHeader } from "@/components/docs/article-header";
import { ArticleSection } from "@/components/docs/article-section";
import { CodeBlock } from "@/components/docs/code-block";
import { API_BASE_URL, API_ENDPOINTS } from "@/components/docs/docs-endpoints";
import { DocsShell } from "@/components/docs/docs-shell";
import { EndpointTable } from "@/components/docs/endpoint-table";
import { StepList } from "@/components/docs/step-list";

const CONTENTS = [
  { id: "base-url", label: "Base URL and authentication" },
  { id: "first-request", label: "Making your first request" },
  { id: "code-examples", label: "Code examples" },
  { id: "response", label: "Response" },
  { id: "core-endpoints", label: "Core endpoints" },
  { id: "asking-zenmux", label: "Asking Zenmux" },
  { id: "errors-and-limits", label: "Errors and rate limits" },
];

const CURL = `curl ${API_BASE_URL}/tick/XAUUSD \\
  -H "Authorization: Bearer YOUR_API_TOKEN"`;

const JAVASCRIPT = `const response = await fetch(
  "${API_BASE_URL}/tick/XAUUSD",
  {
    headers: {
      Authorization: \`Bearer \${YOUR_API_TOKEN}\`,
    },
  },
);

const data = await response.json();`;

const PYTHON = `import requests

response = requests.get(
    f"{API_BASE_URL}/tick/XAUUSD",
    headers={"Authorization": f"Bearer {YOUR_API_TOKEN}"},
)

data = response.json()`;

function Value({ children }: { children: React.ReactNode }) {
  return (
    <code className="rounded border border-border bg-muted px-1.5 py-0.5 font-mono text-[13px] text-foreground">
      {children}
    </code>
  );
}

export function DeveloperView() {
  return (
    <DocsShell
      sectionId="developer"
      activeNav="Documentation"
      activeGroup="Getting Started"
      pageContents={CONTENTS}
    >
      <ArticleHeader
        breadcrumbs={[
          { label: "Developer", href: "/docs/api-reference" },
          { label: "API Reference", href: "/docs/api-reference" },
          { label: "Authentication", href: "#base-url" },
        ]}
        category="Developer"
        title="Connecting to the API"
        readTime="6 min read"
        updatedAt="Updated 5 Oct 2026"
      />

      <ArticleSection id="base-url" title="Base URL and authentication">
        <p>
          The API is served from this site&apos;s origin, under a single versioned prefix:
        </p>
        <Value>{API_BASE_URL}</Value>

        <p className="mt-4">
          Append the path to it, for example{" "}
          <Value>{`${API_BASE_URL}/tick/XAUUSD`}</Value>. One route sits outside the
          prefix: <Value>GET /health</Value> is unauthenticated and lives at the root so
          it can be probed before you hold a token.
        </p>

        <p className="mt-5">
          Authentication is a bearer token obtained from{" "}
          <Value>POST /api/v1/auth/login</Value>. Send it on every request as an{" "}
          <Value>Authorization</Value> header:
        </p>

        <CodeBlock
          language="HTTP header"
          code="Authorization: Bearer YOUR_API_TOKEN"
        />

        <p className="mt-5">
          Market data endpoints are readable without a token. Positions, signals and
          analysis require one. Keep the token server-side and out of client bundles — it
          is a bearer credential, so anyone holding it has the caller&apos;s access.
        </p>
      </ArticleSection>

      <ArticleSection id="first-request" title="Making your first request" divided>
        <StepList
          variant="pad"
          steps={[
            {
              title: "Log in and keep the token",
              meta: "POST /api/v1/auth/login",
              children: (
                <p>The response carries the token and its expiry. Store it; you cannot read it again.</p>
              ),
            },
            {
              title: "Check the service is up",
              meta: "GET /health",
              children: <p>Needs no token, and is the quickest way to confirm you are pointed at the right host.</p>,
            },
            {
              title: "Read a price",
              meta: "GET /api/v1/tick/XAUUSD",
              children: <p>Try this before anything that spends an agent cycle.</p>,
            },
            {
              title: "Run an analysis",
              meta: "POST /api/v1/analyze",
              children: (
                <p>
                  Returns every agent&apos;s contribution alongside the decision, so a call
                  can be traced rather than taken on trust.
                </p>
              ),
            },
          ]}
        />
      </ArticleSection>

      <ArticleSection id="code-examples" title="Code examples" divided>
        <p>
          The same request in three languages. Each tab is a complete, runnable call once
          you replace the token.
        </p>

        <CodeBlock
          tabs={{ cURL: CURL, JavaScript: JAVASCRIPT, Python: PYTHON }}
        />
      </ArticleSection>

      <ArticleSection id="response" title="Response" divided>
        <p>
          A successful tick returns the symbol and the current quote. The feed is a CFD
          broker feed, so read <Value>mid</Value> — <Value>last</Value> and{" "}
          <Value>volume</Value> are always zero and are not meaningful here.
        </p>

        <div className="mt-5 flex flex-wrap items-center gap-2">
          <span className="rounded border border-border bg-muted px-2 py-1 font-mono text-xs text-foreground">
            200 OK
          </span>
          <span className="font-mono text-[13px] text-muted-foreground">
            application/json
          </span>
        </div>

        <CodeBlock
          className="mt-3"
          code={`{
  "symbol": "XAUUSD",
  "description": "Gold vs US Dollar",
  "bid": 4140.58,
  "ask": 4140.70,
  "mid": 4140.64,
  "spread": 0.12,
  "high": 4152.10,
  "low": 4128.44
}`}
        />
      </ArticleSection>

      <ArticleSection id="core-endpoints" title="Core endpoints" divided>
        <p>
          The endpoints below cover connectivity, market data and analysis. Expand{" "}
          <span className="font-medium text-foreground">Try it</span> on any row to build
          and send a request.
        </p>

        <EndpointTable endpoints={API_ENDPOINTS} className="mt-5" />
      </ArticleSection>

      <ArticleSection id="asking-zenmux" title="Asking Zenmux" divided>
        <p>
          <Value>POST /api/v1/zenmux</Value> takes a free-text question and returns a
          structured analysis card. Call <Value>GET /api/v1/zenmux/models</Value> first to
          see which models are available — the registry is served from the running service,
          so it changes with deployment rather than with this page.
        </p>
        <p>
          The response records the model, the timeframe it reasoned at, and a source label
          per field, so a client can tell model output from analysis-derived output.
        </p>
      </ArticleSection>

      <ArticleSection id="errors-and-limits" title="Errors and rate limits" divided>
        <p>
          Failures return a non-2xx status with a JSON body carrying <Value>detail</Value>.
          A missing or expired token is a <Value>401</Value>; an unknown symbol is a{" "}
          <Value>404</Value>.
        </p>
        <p>
          Analysis endpoints are rate limited per token. Back off on a <Value>429</Value>{" "}
          rather than retrying immediately — a full agent cycle is the most expensive call
          you can make.
        </p>
      </ArticleSection>
    </DocsShell>
  );
}