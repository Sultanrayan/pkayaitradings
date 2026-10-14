"use client";

import Link from "next/link";
import { ArrowRight } from "lucide-react";

import { ArticleHeader } from "@/components/docs/article-header";
import { ArticleSection } from "@/components/docs/article-section";
import { DocsShell } from "@/components/docs/docs-shell";

const CONTENTS = [
  { id: "before-you-start", label: "Before you start" },
  { id: "first-guide", label: "Reading your first signal" },
  { id: "building-a-workflow", label: "Building a workflow" },
  { id: "next-steps", label: "Next steps" },
];

const GUIDES = [
  {
    title: "Reading your first signal",
    description: "What each part of a signal card means, and which fields to trust first.",
    meta: "5 min read",
  },
  {
    title: "Building a workflow",
    description: "Turn a manual review into an automated sequence with triggers and conditions.",
    meta: "8 min read",
  },
  {
    title: "Setting up shared views",
    description: "Give a team one agreed set of columns without editing everyone's workspace.",
    meta: "4 min read",
  },
];

export function GuidesView() {
  return (
    <DocsShell
      sectionId="platform"
      activeNav="Guides"
      activeGroup="Workflow Automation"
      pageContents={CONTENTS}
    >
      <ArticleHeader
        breadcrumbs={[
          { label: "Platform", href: "/docs" },
          { label: "Guides", href: "/docs/guides" },
        ]}
        category="Guides"
        title="Guides"
        readTime="4 min read"
        updatedAt="Updated 14 Aug 2026"
      />

      <ArticleSection id="before-you-start" title="Before you start">
        <p>
          Guides are task-shaped walkthroughs. The reference documentation under Platform
          describes what each feature does; a guide walks through doing it once, end to
          end. Start here if you know what you want to achieve but not which screen it
          lives on.
        </p>
      </ArticleSection>

      <ArticleSection id="first-guide" title="Reading your first signal" divided>
        <p>
          Every signal carries the same fields, so learning one card teaches you all of
          them. Work from the top down: what was traded, what the agents concluded, and
          what the risk limits did to the size.
        </p>
        <p>
          The field that matters most is the reasoning. It records which agents voted,
          which way, and what they were looking at — so a past call can be audited rather
          than taken on trust.
        </p>

        <ul className="space-y-2">
          {GUIDES.map((guide) => (
            <li key={guide.title}>
              <Link
                href="/docs/guides"
                className="flex items-start gap-3 rounded-md border border-border p-4 transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <span className="min-w-0 flex-1">
                  <span className="block text-sm font-medium text-foreground">
                    {guide.title}
                  </span>
                  <span className="mt-1 block text-sm text-muted-foreground">
                    {guide.description}
                  </span>
                  <span className="mt-2 block text-xs text-muted-foreground">
                    {guide.meta}
                  </span>
                </span>
                <ArrowRight aria-hidden className="mt-1 size-4 shrink-0 text-muted-foreground" />
              </Link>
            </li>
          ))}
        </ul>
      </ArticleSection>

      <ArticleSection id="building-a-workflow" title="Building a workflow" divided>
        <p>
          A workflow watches for a trigger, checks it against conditions you set, then
          runs an action. The order matters: a workflow with no conditions fires on every
          matching event, which is rarely what you want.
        </p>
        <p>
          Start with one trigger and one action, confirm it behaves, then add conditions.
          Building three conditions at once makes a misfire hard to trace.
        </p>
      </ArticleSection>

      <ArticleSection id="next-steps" title="Next steps" divided>
        <p>
          For the underlying concepts rather than the walkthroughs, return to{" "}
          <Link
            href="/docs"
            className="font-medium text-foreground underline underline-offset-4 hover:no-underline"
          >
            Create and Manage Table Views
          </Link>
          . To connect programmatically, switch the sidebar section to{" "}
          <Link
            href="/docs/api-reference"
            className="font-medium text-foreground underline underline-offset-4 hover:no-underline"
          >
            Developer
          </Link>
          .
        </p>
      </ArticleSection>
    </DocsShell>
  );
}