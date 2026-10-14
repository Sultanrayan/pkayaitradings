import type { Metadata } from "next";

import { DeveloperView } from "@/components/docs/developer-view";

export const metadata: Metadata = {
  title: "API Reference — Pkay TDAI Docs",
  description:
    "Connect to the Pkay TDAI API: base URL and authentication, core endpoints, Zenmux analysis, and error handling.",
};

export default function ApiReferencePage() {
  return <DeveloperView />;
}
