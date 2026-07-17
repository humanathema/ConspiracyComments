#!/usr/bin/env python3
"""Post-process nbconvert 'lab' template HTML: collapse code cells into
<details>, and wrap oversized outputs in scrollable boxes."""
import sys
from bs4 import BeautifulSoup

SRC = sys.argv[1]
DST = sys.argv[2]

OUTPUT_SCROLL_THRESHOLD_CHARS = 2000
OUTPUT_MAX_HEIGHT_PX = 350

with open(SRC, encoding="utf-8") as f:
    soup = BeautifulSoup(f, "html.parser")

n_code_collapsed = 0
for wrapper in soup.select("div.jp-CodeCell div.jp-Cell-inputWrapper"):
    details = soup.new_tag("details", **{"class": "code-collapse"})
    summary = soup.new_tag("summary")
    summary.string = "Show code"
    details.append(summary)

    # Move all existing children of wrapper into details, then put details back in wrapper
    children = list(wrapper.children)
    for child in children:
        details.append(child.extract())
    wrapper.append(details)
    n_code_collapsed += 1

n_scrolled = 0
for output_area in soup.select("div.jp-Cell-outputWrapper div.jp-Cell-outputArea"):
    text_len = len(output_area.get_text())
    if text_len > OUTPUT_SCROLL_THRESHOLD_CHARS:
        output_area["style"] = (
            output_area.get("style", "")
            + f"max-height:{OUTPUT_MAX_HEIGHT_PX}px;overflow-y:auto;"
              "border:1px solid #ddd;border-radius:4px;padding:4px 8px;"
        )
        n_scrolled += 1

style_tag = soup.new_tag("style")
style_tag.string = """
details.code-collapse { width: 100%; }
details.code-collapse > summary {
  cursor: pointer;
  padding: 4px 8px;
  color: #555;
  font-family: monospace;
  font-size: 0.85em;
  list-style: none;
}
details.code-collapse > summary::-webkit-details-marker { display: none; }
details.code-collapse > summary::before { content: "\\25B6  "; }
details.code-collapse[open] > summary::before { content: "\\25BC  "; }
"""
if soup.head:
    soup.head.append(style_tag)
else:
    soup.insert(0, style_tag)

with open(DST, "w", encoding="utf-8") as f:
    f.write(str(soup))

print(f"code cells collapsed: {n_code_collapsed}")
print(f"outputs made scrollable (>{OUTPUT_SCROLL_THRESHOLD_CHARS} chars): {n_scrolled}")
print(f"written to: {DST}")
