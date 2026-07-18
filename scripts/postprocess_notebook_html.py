#!/usr/bin/env python3
"""Post-process nbconvert 'lab' template HTML:
- collapse code cells into <details>
- wrap oversized outputs in scrollable boxes
- wrap markdown sections (by H2/H3/H4 heading) into nested collapsible
  <details>, mirroring Jupyter's "collapsible headings" feature
- generate a clickable, nested table of contents that auto-expands
  collapsed ancestor sections on click
"""
import sys
from bs4 import BeautifulSoup

SRC = sys.argv[1]
DST = sys.argv[2]

OUTPUT_SCROLL_THRESHOLD_CHARS = 2000
OUTPUT_MAX_HEIGHT_PX = 350
HEADING_TAGS = ("h2", "h3", "h4")  # h1 is the one-off document title, not a section

with open(SRC, encoding="utf-8") as f:
    soup = BeautifulSoup(f, "html.parser")

# --- 1. Collapse code cells ---
n_code_collapsed = 0
for wrapper in soup.select("div.jp-CodeCell div.jp-Cell-inputWrapper"):
    details = soup.new_tag("details", **{"class": "code-collapse"})
    summary = soup.new_tag("summary")
    summary.string = "Show code"
    details.append(summary)
    for child in list(wrapper.children):
        details.append(child.extract())
    wrapper.append(details)
    n_code_collapsed += 1

# --- 2. Scrollable oversized outputs ---
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

# --- 3. Build the TOC entry list (every heading anywhere, including ones
#     nested inside cell 0's intro block, not just cell-leading ones) ---
toc_entries = []  # (level, id, text)
for tag in soup.find_all(HEADING_TAGS):
    if tag.get("id"):
        toc_entries.append((int(tag.name[1]), tag["id"], tag.get_text().rstrip("¶").strip()))

# --- 4. Wrap sections into nested collapsible <details>, at cell granularity ---
main = soup.find("main") or soup.body
cells = main.find_all("div", class_="jp-Cell", recursive=False) if main else []


def leading_heading_tag(cell):
    """If this cell's rendered content starts with an H2-H4 (after skipping
    a leading <hr> -- most section headers are written as "---\\n## Heading"
    in the source markdown -- and blank text nodes), return the heading tag
    itself, still attached to the tree."""
    md = cell.select_one("div.jp-Cell-inputWrapper .jp-RenderedMarkdown, div.jp-MarkdownCell .jp-RenderedMarkdown")
    if not md:
        return None
    for child in md.children:
        name = getattr(child, "name", None)
        if name is None:
            if str(child).strip():
                return None  # non-blank text before any heading
            continue
        if name == "hr":
            continue
        if name in HEADING_TAGS and child.get("id"):
            return child
        return None  # first real element isn't a heading
    return None


n_sections = 0
if cells:
    stack = []  # list of (level, details_tag)
    new_top_level = []  # cells/details placed directly under <main>

    for cell in cells:
        heading_tag = leading_heading_tag(cell)
        if heading_tag:
            level = int(heading_tag.name[1])
            hid = heading_tag["id"]
            while stack and stack[-1][0] >= level:
                stack.pop()
            details = soup.new_tag("details", **{"class": "section-collapse", "open": ""})
            summary = soup.new_tag("summary")
            # Drop any leading <hr> siblings that preceded the heading --
            # redundant now that the details wrapper has its own border.
            for sibling in list(heading_tag.previous_siblings):
                if getattr(sibling, "name", None) == "hr":
                    sibling.extract()
            summary.append(heading_tag.extract())  # only the heading itself is clickable
            details.append(summary)
            if stack:
                stack[-1][1].append(details)
            else:
                new_top_level.append(details)
            stack.append((level, details))
            n_sections += 1
            # Any content that followed the heading within the SAME cell
            # (e.g. a one-paragraph description written right under "##
            # Heading" in the same markdown block) becomes the section's
            # first body item, not part of the clickable summary.
            if cell.get_text(strip=True) or cell.find(True):
                stack[-1][1].append(cell.extract())
            else:
                cell.decompose()
        else:
            if stack:
                stack[-1][1].append(cell.extract())
            else:
                new_top_level.append(cell.extract())

    for item in new_top_level:
        main.append(item)

# --- 5. Build the TOC nav block, inserted right after the H1 title ---
def build_toc_list(entries):
    ul = soup.new_tag("ul")
    stack = [(1, ul)]  # (level, current <ul>)
    for level, hid, text in entries:
        while stack[-1][0] >= level:
            stack.pop()
        li = soup.new_tag("li")
        a = soup.new_tag("a", href=f"#{hid}")
        a.string = text
        li.append(a)
        stack[-1][1].append(li)
        child_ul = soup.new_tag("ul")
        li.append(child_ul)
        stack.append((level, child_ul))
    # drop empty trailing <ul> tags with no <li> children -- scoped to
    # this TOC only, NOT soup.find_all, which would touch unrelated
    # empty <ul> elements anywhere else in the rendered notebook content
    for tag in ul.find_all("ul"):
        if not tag.find("li"):
            tag.decompose()
    return ul


if toc_entries:
    toc_details = soup.new_tag("details", **{"class": "toc-nav", "open": ""})
    toc_summary = soup.new_tag("summary")
    toc_summary.string = "Contents"
    toc_details.append(toc_summary)
    toc_details.append(build_toc_list(toc_entries))

    h1 = soup.find("h1")
    if h1:
        # insert right after the H1's containing cell
        h1_cell = h1.find_parent("div", class_="jp-Cell")
        if h1_cell:
            h1_cell.insert_after(toc_details)
        else:
            h1.insert_after(toc_details)

# --- 6. Styles + click-to-expand-ancestors behavior ---
style_tag = soup.new_tag("style")
style_tag.string = """
/* Clean documentation aesthetic */
body {
  max-width: 960px !important;
  margin: 0 auto !important;
  padding: 24px 32px !important;
  background-color: #ffffff;
}

body, .jp-RenderedMarkdown, .jp-MarkdownCell {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif !important;
  line-height: 1.6 !important;
  color: #24292e !important;
}

/* Headings scale and hierarchy */
h1 {
  font-size: 2.5em !important;
  font-weight: 700 !important;
  margin-top: 1.5em !important;
  margin-bottom: 0.5em !important;
  color: #24292e !important;
}

h2 {
  font-size: 2.0em !important;
  font-weight: 700 !important;
  margin-top: 2.0em !important;
  margin-bottom: 0.5em !important;
  border-bottom: 1px solid #eaecef !important;
  padding-bottom: 0.3em !important;
  color: #24292e !important;
}

h3 {
  font-size: 1.5em !important;
  font-weight: 600 !important;
  margin-top: 1.8em !important;
  margin-bottom: 0.5em !important;
  color: #24292e !important;
}

h4 {
  font-size: 1.2em !important;
  font-weight: 600 !important;
  margin-top: 1.5em !important;
  margin-bottom: 0.5em !important;
  color: #24292e !important;
}

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

details.section-collapse {
  border-left: 3px solid #e8e8e8;
  padding-left: 14px;
  margin: 6px 0 6px 2px;
}
details.section-collapse > summary {
  cursor: pointer;
  list-style: none;
  margin-left: -14px;
  padding-left: 14px;
}
details.section-collapse > summary::-webkit-details-marker { display: none; }
details.section-collapse > summary::before {
  content: "\\25BC";
  display: inline-block;
  width: 1em;
  margin-left: -1.3em;
  color: #aaa;
  font-size: 0.75em;
}
details.section-collapse:not([open]) > summary::before { content: "\\25B6"; }
details.section-collapse > summary h2,
details.section-collapse > summary h3,
details.section-collapse > summary h4 { display: inline; }

details.toc-nav {
  background: #f7f7f7;
  border: 1px solid #e2e2e2;
  border-radius: 6px;
  padding: 10px 16px;
  margin: 16px 0 24px 0;
}
details.toc-nav > summary {
  cursor: pointer;
  font-weight: 600;
  list-style: none;
}
details.toc-nav > summary::-webkit-details-marker { display: none; }
details.toc-nav > summary::before { content: "\\25BC  "; color: #888; }
details.toc-nav:not([open]) > summary::before { content: "\\25B6  "; }
details.toc-nav ul { list-style: none; padding-left: 18px; margin: 4px 0; }
details.toc-nav > ul { padding-left: 4px; }
details.toc-nav a { text-decoration: none; color: #2c5aa0; font-size: 0.92em; }
details.toc-nav a:hover { text-decoration: underline; }

@media (prefers-color-scheme: dark) {
  body { background-color: #1e1e1e !important; }
  body, .jp-RenderedMarkdown, .jp-MarkdownCell, h1, h2, h3, h4 { color: #e4e4e4 !important; }
  details.section-collapse { border-left-color: #3a3a3a; }
  details.toc-nav { background: #252526; border-color: #3a3a3a; }
  details.toc-nav a { color: #7aa7e0; }
  h2 { border-bottom-color: #3a3a3a !important; }
}
"""
if soup.head:
    soup.head.append(style_tag)
else:
    soup.insert(0, style_tag)

script_tag = soup.new_tag("script")
script_tag.string = """
document.querySelectorAll('details.toc-nav a[href^="#"]').forEach(function (a) {
  a.addEventListener('click', function (e) {
    e.preventDefault();
    var id = decodeURIComponent(this.getAttribute('href').slice(1));
    var target = document.getElementById(id);
    if (!target) return;
    var el = target.closest('details');
    while (el) {
      el.open = true;
      el = el.parentElement ? el.parentElement.closest('details') : null;
    }
    target.scrollIntoView({behavior: 'smooth', block: 'start'});
    history.pushState(null, '', '#' + id);
  });
});
"""
soup.append(script_tag)

with open(DST, "w", encoding="utf-8") as f:
    f.write(str(soup))

print(f"code cells collapsed: {n_code_collapsed}")
print(f"outputs made scrollable (>{OUTPUT_SCROLL_THRESHOLD_CHARS} chars): {n_scrolled}")
print(f"sections wrapped: {n_sections}")
print(f"TOC entries: {len(toc_entries)}")
print(f"written to: {DST}")
