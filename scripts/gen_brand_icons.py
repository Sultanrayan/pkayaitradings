"""Generate the brand-icons component from vetted public SVG sources.

Sources (monochrome/brand paths, all permissive):
  - simple-icons CDN: binance, claude, deepseek, okx, qdrant
  - svgl.app:         openai (ChatGPT mark)

Run from the repo root:  .venv/Scripts/python.exe scripts/gen_brand_icons.py
"""

from __future__ import annotations

import re
import urllib.request
from pathlib import Path

OUT = Path("frontend/src/components/marketing/brand-icons.tsx")

# slug -> (component name, source url, attribution)
SOURCES = {
    "BinanceIcon": (
        "https://cdn.simpleicons.org/binance",
        "Binance",
    ),
    "ChatGptIcon": (
        "https://svgl.app/library/openai.svg",
        "ChatGPT",
    ),
    "ClaudeIcon": (
        "https://cdn.simpleicons.org/claude",
        "Claude",
    ),
    "DeepSeekIcon": (
        "https://cdn.simpleicons.org/deepseek",
        "DeepSeek",
    ),
    "OkxIcon": (
        "https://cdn.simpleicons.org/okx",
        "OKX",
    ),
    "QdrantIcon": (
        "https://cdn.simpleicons.org/qdrant",
        "Qdrant",
    ),
}


def fetch(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "pkay-build/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8")


def viewbox_of(svg: str) -> str:
    match = re.search(r'viewBox="([^"]+)"', svg)
    return match.group(1) if match else "0 0 24 24"


def inner_of(svg: str) -> str:
    start = svg.find(">", svg.find("<svg"))
    end = svg.rfind("</svg>")
    return svg[start + 1 : end].strip()


HEADER = '''"use client";

/**
 * Brand marks for the integrations shown on the homepage.
 *
 * GENERATED FILE — do not hand-edit. Regenerate with:
 *   .venv/Scripts/python.exe scripts/gen_brand_icons.py
 *
 * Paths are vendored from simple-icons (CC0) and svgl.app so the page ships no
 * third-party requests. Every icon takes `className` and inherits sizing.
 */

'''


def main() -> None:
    blocks: list[str] = []
    for name, (url, _attribution) in SOURCES.items():
        svg = fetch(url)
        viewbox = viewbox_of(svg)
        inner = inner_of(svg)
        # Drop the accessible title/role from the source markup; the parent
        # supplies the label.
        inner = re.sub(r"<title>.*?</title>", "", inner, flags=re.S)
        blocks.append(
            f"export function {name}({{ className }}: {{ className?: string }}) {{\n"
            f"  return (\n"
            f'    <svg viewBox="{viewbox}" fill="currentColor" aria-hidden="true"\n'
            f'      className={{className}} xmlns="http://www.w3.org/2000/svg">\n'
            f"      {inner}\n"
            f"    </svg>\n"
            f"  );\n"
            f"}}\n"
        )

    body = "\n".join(blocks)
    footer = (
        "\n// Bybit has no monochrome brand mark in the sources above, so it is\n"
        "// rendered as a wordmark rather than inventing a logo.\n"
        "export function BybitIcon({ className }: { className?: string }) {\n"
        "  return (\n"
        '    <span\n'
        '      className={cn(\n'
        '        "flex items-center text-[11px] font-semibold tracking-tight",\n'
        "        className,\n"
        "      )}\n"
        "    >\n"
        "      Bybit\n"
        "    </span>\n"
        "  );\n"
        "}\n"
    )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        HEADER
        + 'import { cn } from "cn";\n\n'
        + body
        + footer,
        encoding="utf-8",
    )
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
