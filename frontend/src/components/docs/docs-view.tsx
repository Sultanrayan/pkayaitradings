"use client";

import { ArticleHeader } from "@/components/docs/article-header";
import { ArticleSection } from "@/components/docs/article-section";
import { DocumentationImage } from "@/components/docs/documentation-image";
import { DocsShell } from "@/components/docs/docs-shell";
import { StepList } from "@/components/docs/step-list";
import { WatchVideoButton } from "@/components/docs/watch-video-button";

const CONTENTS = [
  { id: "creating-a-table-view", label: "Creating a table view" },
  { id: "managing-table-views", label: "Managing table views" },
  { id: "tips-for-effective-table-views", label: "Tips for Effective Table Views" },
  { id: "troubleshooting", label: "Troubleshooting" },
];

export function DocsView() {
  return (
    <DocsShell
      sectionId="platform"
      activeNav="Documentation"
      activeGroup="Create and Manage Table Views"
      pageContents={CONTENTS}
    >
      <ArticleHeader
        breadcrumbs={[
          { label: "Platform", href: "/docs" },
          { label: "Create & Manage Table Views", href: "/docs" },
        ]}
        category="Tutorial"
        title="Creating and Managing Table Views"
        readTime="2 min read"
        updatedAt="Updated 14 Aug 2026"
      />

      <ArticleSection id="overview" title="Overview">
        <p>
          A table view is a saved set of fields, filters and sort order. Rather than
          rebuilding the same layout each time you open a workspace, you define it once
          and reuse it — so everyone reads the same columns in the same order.
        </p>
        <p>
          Views are scoped to the table they are created from, and any view can be shared
          with the rest of the team. Start from{" "}
          <strong className="font-medium text-foreground">Ticket Introduction</strong> if
          you have not worked with tables before.
        </p>
        <WatchVideoButton />

        <DocumentationImage
          src="/dashboard.png"
          alt="The Pkay TDAI dashboard showing a XAU/USD price panel, an AI signal reading SELL at 79% confidence, market structure, a one-hour candlestick chart with EMA overlays, and an AI analysis panel listing the reasoning and a confidence breakdown."
          caption="The dashboard: price, AI signal and chart on the left, with the agent reasoning and confidence breakdown alongside."
        />
      </ArticleSection>

      <ArticleSection id="creating-a-table-view" title="Creating a Table View" divided>
        <StepList
          steps={[
            {
              title: "Navigate to the Table View Manager",
              children: (
                <p>
                  Open the workspace and select{" "}
                  <strong className="font-medium text-foreground">Table View Manager</strong>{" "}
                  from the sidebar. Every view for the current table is listed here.
                </p>
              ),
            },
            {
              title: 'Click "Create New View"',
              children: (
                <p>
                  Select{" "}
                  <strong className="font-medium text-foreground">Create New View</strong>{" "}
                  in the toolbar. Give the view a name that describes how it is used, not
                  what it contains.
                </p>
              ),
            },
            {
              title: "Define View Criteria",
              children: (
                <p>
                  Choose the fields to show, then set filters and sort order. Criteria are
                  evaluated when the view is opened, so a view stays current without being
                  rebuilt.
                </p>
              ),
            },
            {
              title: "Save Your View",
              children: (
                <p>
                  Save the view to add it to the list. See{" "}
                  <a
                    href="#managing-table-views"
                    className="font-medium text-foreground underline underline-offset-4 hover:no-underline"
                  >
                    Managing Table Views
                  </a>{" "}
                  to edit, duplicate or remove it later.
                </p>
              ),
            },
          ]}
        />
      </ArticleSection>

      <ArticleSection id="managing-table-views" title="Managing Table Views" divided>
        <StepList
          steps={[
            {
              title: "Accessing Existing Views",
              children: (
                <p>
                  Saved views appear in the Table View Manager and in the view switcher at
                  the top of the table. Selecting one applies its criteria immediately.
                </p>
              ),
            },
            {
              title: "Editing Views",
              children: (
                <p>
                  Editing a view changes it for everyone it is shared with. To experiment
                  safely, duplicate the view first and edit the copy.
                </p>
              ),
            },
            {
              title: "Duplicating Views",
              children: (
                <p>
                  Duplicating copies the fields, filters and sort order but not the sharing
                  settings. This is the quickest way to branch a view for a new purpose.
                </p>
              ),
            },
          ]}
        />
      </ArticleSection>

      <ArticleSection
        id="tips-for-effective-table-views"
        title="Tips for Effective Table Views"
        divided
      >
        <p>
          Keep views narrow. A view that carries every field is harder to scan than the
          default table it replaced, and filtering is cheaper to adjust than columns are
          to hide.
        </p>
        <p>
          Name views after the task they serve — <em>Unassigned &amp; overdue</em> rather
          than <em>View 3</em> — so the list stays navigable once there are more than a
          handful.
        </p>
      </ArticleSection>

      <ArticleSection id="troubleshooting" title="Troubleshooting" divided>
        <p>
          If a view looks empty, confirm its filters still match the data. Views do not
          fail; they evaluate against whatever is in the table now, so a field that was
          renamed or removed will silently drop out of the view.
        </p>
        <p>
          If edits are not visible to a colleague, check that the view is shared with
          them. Editing a shared view updates it for every recipient.
        </p>
      </ArticleSection>
    </DocsShell>
  );
}