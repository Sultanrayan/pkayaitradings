import type { Metadata } from "next";

import { DocsView } from "@/components/docs/docs-view";

export const metadata: Metadata = {
  title: "Documentation — Pkay TDAI",
  description:
    "Platform documentation: create and manage table views, sharing and permissions, workflow automation, reports and storage.",
};

export default function DocsPage() {
  return <DocsView />;
}
