/**
 * Sidebar navigation data for the documentation site.
 *
 * Sections are the top-level split (Platform / Developer). Each section owns a set
 * of groups; a group has an uppercase heading and a list of link items, one of which
 * may be the current page.
 *
 * Items carry real destinations rather than placeholders. Where a planned page does
 * not exist yet, the item points at the closest section on the current page instead
 * of a URL that would 404 — so every entry is navigable, and adding a page later is a
 * matter of changing one `href`.
 */

export interface SidebarItem {
  label: string;
  href: string;
  /** Marks the current page. */
  active?: boolean;
}

export interface SidebarGroup {
  title: string;
  items: SidebarItem[];
}

export interface DocsSection {
  id: string;
  label: string;
  /** Landing page for the section. */
  href: string;
  description: string;
  groups: SidebarGroup[];
}

const DEV = "#";

/* ------------------------------------------------------------------ Developer */

const DEVELOPER_GROUPS: SidebarGroup[] = [
  {
    title: "Getting Started",
    items: [
      { label: "Introduction", href: "/docs/api-reference" },
      { label: "Quickstart", href: `${DEV}first-request` },
      { label: "Authentication", href: `${DEV}base-url`, active: true },
    ],
  },
  {
    title: "Market Data",
    items: [
      { label: "Overview", href: `${DEV}core-endpoints` },
      { label: "Symbols", href: `${DEV}core-endpoints` },
      { label: "Candles", href: "#endpoint-ohlc-xauusd" },
      { label: "Ticks", href: "#endpoint-tick-xauusd" },
    ],
  },
  {
    title: "Analysis",
    items: [
      { label: "Zenmux Analysis", href: `${DEV}asking-zenmux` },
      { label: "Technical Analysis", href: `${DEV}core-endpoints` },
      { label: "AI Signals", href: `${DEV}core-endpoints` },
    ],
  },
  {
    title: "Risk & Execution",
    items: [
      { label: "Risk Management", href: `${DEV}try-it` },
      { label: "Positions", href: `${DEV}core-endpoints` },
      { label: "Execution", href: `${DEV}core-endpoints` },
    ],
  },
  {
    title: "Resources",
    items: [{ label: "Examples", href: `${DEV}code-examples` }],
  },
];

/* ------------------------------------------------------------------- Platform */

const PLATFORM_GROUPS: SidebarGroup[] = [
  {
    title: "Basics",
    items: [
      { label: "Ticket Introduction", href: "/docs" },
      { label: "Core Concepts", href: `${DEV}overview` },
      { label: "Glossary", href: `${DEV}overview` },
    ],
  },
  {
    title: "Working with Data",
    items: [
      { label: "Create and Manage Table Views", href: "/docs" },
      { label: "Sharing and Permissions", href: `${DEV}managing-table-views` },
    ],
  },
  {
    title: "Automation",
    items: [
      { label: "Workflow Automation", href: "/docs/guides" },
      { label: "Updates and Activity", href: "/docs/guides" },
    ],
  },
  {
    title: "Configuration",
    items: [
      { label: "Managing Attributes and Custom Fields", href: `${DEV}troubleshooting` },
      { label: "Comments and Mentions", href: `${DEV}troubleshooting` },
    ],
  },
  {
    title: "Reporting",
    items: [
      { label: "Reports and Analytics", href: `${DEV}troubleshooting` },
      { label: "Drive and Storage", href: `${DEV}troubleshooting` },
    ],
  },
];

export const DOCS_SECTIONS: DocsSection[] = [
  {
    id: "platform",
    label: "Platform",
    href: "/docs",
    description: "System usage and general guidance.",
    groups: PLATFORM_GROUPS,
  },
  {
    id: "developer",
    label: "Developer",
    href: "/docs/api-reference",
    description: "Connect to the Pkay TDAI API endpoints.",
    groups: DEVELOPER_GROUPS,
  },
];

export function sectionById(id: string): DocsSection {
  return DOCS_SECTIONS.find((section) => section.id === id) ?? DOCS_SECTIONS[0];
}