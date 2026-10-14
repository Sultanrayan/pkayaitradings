import type { Metadata } from "next";

import { GuidesView } from "@/components/docs/guides-view";

export const metadata: Metadata = {
  title: "Guides — Pkay TDAI Docs",
  description:
    "Task-shaped walkthroughs: reading your first signal, building a workflow, and setting up shared views.",
};

export default function GuidesPage() {
  return <GuidesView />;
}
