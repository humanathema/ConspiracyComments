#!/usr/bin/env python3
"""Post-process nbconvert 'lab' template HTML:
- collapse code cells into <details>
- wrap oversized outputs in scrollable boxes
- wrap markdown sections into collapsible <details> (preserving 100% native Jupyter typography & alignment)
- make Research Map table section numbers clickable anchor links
"""
import sys
import re
from bs4 import BeautifulSoup

SRC = sys.argv[1]
DST = sys.argv[2]

OUTPUT_SCROLL_THRESHOLD_CHARS = 2000
OUTPUT_MAX_HEIGHT_PX = 350
HEADING_TAGS = ("h1", "h2", "h3", "h4")

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

# Find the main document title (the first H1 tag)
h1_tags = soup.find_all("h1")
first_h1 = h1_tags[0] if h1_tags else None

# --- 3. Make Research Map table section numbers clickable links ---
heading_id_map = {}
for tag in soup.find_all(HEADING_TAGS):
    if tag is not first_h1 and tag.get("id"):
        txt = tag.get_text().rstrip("¶").strip()
        heading_id_map[txt] = tag["id"]

for table in soup.find_all("table"):
    if "Section" in table.get_text():
        for tr in table.find_all("tr"):
            tds = tr.find_all(["td", "th"])
            if len(tds) >= 2 and tds[0].name == "td":
                raw_sec = tds[0].get_text().strip()
                m = re.match(r"^(\d+(?:\.\d+)?)", raw_sec)
                sec_num = m.group(1) if m else raw_sec
                
                target_id = None
                for htxt, hid in heading_id_map.items():
                    if htxt.startswith(sec_num + ".") or htxt.startswith(sec_num + " "):
                        target_id = hid
                        break
                
                if target_id:
                    strong = tds[0].find("strong")
                    a = soup.new_tag("a", href=f"#{target_id}", style="color: #2c5aa0; text-decoration: underline; cursor: pointer;")
                    if strong:
                        a.string = strong.get_text()
                        strong.clear()
                        strong.append(a)
                    else:
                        a.string = raw_sec
                        tds[0].clear()
                        tds[0].append(a)

# --- 4. Wrap sections into collapsible <details>, preserving exact native Jupyter layout ---
main = soup.find("main") or soup.body
cells = main.find_all("div", class_="jp-Cell", recursive=False) if main else []


def leading_heading_tag(cell):
    md = cell.select_one("div.jp-Cell-inputWrapper .jp-RenderedMarkdown, div.jp-MarkdownCell .jp-RenderedMarkdown")
    if not md:
        return None
    first_heading = None
    for child in md.children:
        name = getattr(child, "name", None)
        if name is None:
            if str(child).strip():
                return None
            continue
        if name == "hr":
            continue
        if name in HEADING_TAGS and child.get("id"):
            if child is first_h1:
                return None
            first_heading = child
            break
        return None

    if not first_heading:
        return None

    same_level_headings = md.find_all(first_heading.name)
    if len(same_level_headings) > 1:
        return None

    return first_heading


n_sections = 0
if cells:
    stack = []  # list of (level, details_tag)
    new_top_level = []

    for cell in cells:
        heading_tag = leading_heading_tag(cell)
        if heading_tag:
            level = int(heading_tag.name[1])
            hid = heading_tag["id"]
            while stack and stack[-1][0] >= level:
                stack.pop()
            
            details = soup.new_tag("details", **{"class": "jp-Section-collapse", "open": ""})
            summary = soup.new_tag("summary")
            
            # Reconstruct the exact Jupyter boilerplate flex layout wrapper 
            # so the heading inherits 100% native padding, margins, and prompt gutters
            summary_cell = soup.new_tag("div", **{"class": "jp-Cell jp-MarkdownCell jp-Notebook-cell"})
            summary_input_wrapper = soup.new_tag("div", **{"class": "jp-Cell-inputWrapper"})
            summary_collapser = soup.new_tag("div", **{"class": "jp-Collapser jp-InputCollapser jp-Cell-inputCollapser"})
            summary_input_area = soup.new_tag("div", **{"class": "jp-InputArea jp-Cell-inputArea"})
            
            # The empty left gutter where [ ]: usually goes
            summary_prompt = soup.new_tag("div", **{"class": "jp-InputPrompt jp-InputArea-prompt"})
            
            summary_md = soup.new_tag("div", **{"class": "jp-RenderedHTMLCommon jp-RenderedMarkdown jp-MarkdownOutput", "data-mime-type": "text/markdown"})
            
            for sibling in list(heading_tag.previous_siblings):
                if getattr(sibling, "name", None) == "hr":
                    sibling.extract()
            
            summary_md.append(heading_tag.extract())
            
            summary_input_area.append(summary_prompt)
            summary_input_area.append(summary_md)
            summary_input_wrapper.append(summary_collapser)
            summary_input_wrapper.append(summary_input_area)
            summary_cell.append(summary_input_wrapper)
            
            summary.append(summary_cell)
            details.append(summary)
            
            if stack:
                stack[-1][1].append(details)
            else:
                new_top_level.append(details)
            stack.append((level, details))
            n_sections += 1
            
            # If the original cell still has paragraph text left over, add it as a normal body cell
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

# --- 5. Native Jupyter CSS overrides & smooth scroll JS ---
style_tag = soup.new_tag("style")
style_tag.string = """
/* Guarantee native Jupyter sans-serif typography */
summary {
  font-family: var(--jp-content-font-family, system-ui, -apple-system, blinkmacsystemfont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif) !important;
}

/* Reset Details Container completely transparent to layout */
details.jp-Section-collapse {
  border: none !important;
  margin: 0 !important;
  padding: 0 !important;
}

details.jp-Section-collapse > summary {
  list-style: none !important;
  list-style-type: none !important;
  cursor: pointer;
  outline: none;
  display: block !important; 
}

details.jp-Section-collapse > summary::-webkit-details-marker,
details.jp-Section-collapse > summary::marker {
  display: none !important;
  content: "" !important;
}

/* Inject the disclosure triangle securely inside the invisible Jupyter prompt gutter */
details.jp-Section-collapse > summary .jp-InputPrompt::after {
  content: "\\25BC";
  display: block;
  width: 100%;
  text-align: right;
  padding-right: 12px;
  box-sizing: border-box;
  color: #757575;
  font-size: 0.7em;
  padding-top: 1.5em; /* Aligns triangle vertically with the H1/H2 text baseline */
}

details.jp-Section-collapse:not([open]) > summary .jp-InputPrompt::after {
  content: "\\25B6";
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
"""
if soup.head:
    soup.head.append(style_tag)
else:
    soup.insert(0, style_tag)

script_tag = soup.new_tag("script")
script_tag.string = """
document.querySelectorAll('a[href^="#"]').forEach(function (a) {
  a.addEventListener('click', function (e) {
    var href = this.getAttribute('href');
    if (!href || href === '#') return;
    var id = decodeURIComponent(href.slice(1));
    var target = document.getElementById(id);
    if (!target) return;
    e.preventDefault();
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
print(f"written to: {DST}")