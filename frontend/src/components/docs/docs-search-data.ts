/**
 * Search index for the documentation command palette.
 *
 * Split from `docs-endpoints.ts` so that module stays purely about the endpoint
 * reference, and this one is purely about navigation.
 */

export interface SearchEntry {
  label: string;
  /** Route the result navigates to. */
  href: string;
  /** Section anchor on that route, when the result points inside it. */
  hash?: string;
  /** Extra terms matched against, so "candle" finds the candle endpoint. */
  keywords?: string;
}

export interface SearchGroupEntry extends SearchEntry {
  group: string;
}

const documentation: SearchGroupEntry[] = [
  { group: "Documentation", label: "Documentation overview", href: "/docs" },
  { group: "Documentation", label: "Creating and Managing Table Views", href: "/docs" },
  { group: "Documentation", label: "Managing Table Views", href: "/docs", hash: "managing-table-views" },
  { group: "Documentation", label: "Troubleshooting", href: "/docs", hash: "troubleshooting" },
  { group: "Documentation", label: "Connecting to the API", href: "/docs/api-reference" },
  { group: "Documentation", label: "Base URL and authentication", href: "/docs/api-reference", hash: "base-url" },
  { group: "Documentation", label: "Making your first request", href: "/docs/api-reference", hash: "first-request" },
  { group: "Documentation", label: "Code examples", href: "/docs/api-reference", hash: "code-examples" },
  { group: "Documentation", label: "Response", href: "/docs/api-reference", hash: "response" },
  { group: "Documentation", label: "Core endpoints", href: "/docs/api-reference", hash: "core-endpoints" },
  { group: "Documentation", label: "Asking Zenmux", href: "/docs/api-reference", hash: "asking-zenmux" },
  { group: "Documentation", label: "Errors and rate limits", href: "/docs/api-reference", hash: "errors-and-limits" },
];

const guides: SearchGroupEntry[] = [
  { group: "Guides", label: "Guides", href: "/docs/guides" },
  { group: "Guides", label: "Reading your first signal", href: "/docs/guides" },
  { group: "Guides", label: "Building a workflow", href: "/docs/guides" },
  { group: "Guides", label: "Setting up shared views", href: "/docs/guides" },
  { group: "Guides", label: "Workflow Automation", href: "/docs/guides" },
];

const examples: SearchGroupEntry[] = [
  { group: "Examples", label: "cURL: fetch a tick", href: "/docs/api-reference", hash: "code-examples", keywords: "curl shell request tick price" },
  { group: "Examples", label: "JavaScript: fetch a tick", href: "/docs/api-reference", hash: "code-examples", keywords: "js node fetch await tick price" },
  { group: "Examples", label: "Python: fetch a tick", href: "/docs/api-reference", hash: "code-examples", keywords: "python requests tick price" },
  { group: "Examples", label: "Sample response payload", href: "/docs/api-reference", hash: "response", keywords: "response json sample" },
];

export const SEARCH_INDEX = { documentation, guides, examples };