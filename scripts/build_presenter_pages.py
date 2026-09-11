"""Render the presenter pages from their Markdown sources. Needs pandoc.

    uv run python scripts/build_presenter_pages.py
"""
import itertools
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
OUT = DOCS / "presentation"
COLLAPSED = ("Before the meeting", "Questions to have ready", "If it goes wrong", "Requirement coverage")
FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
         '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
         '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Libre+Franklin:wght@500;600;800'
         '&family=Newsreader:opsz,wght@6..72,300;6..72,400;6..72,500&family=IBM+Plex+Mono:wght@400;500;600&display=swap">')


def strip_tags(text):
    return re.sub(r"<[^>]+>", "", text)


def relink(match):
    href = match.group(1)
    if re.match(r"[a-z]+:|#", href):
        return match.group(0)
    # Sources live in docs/, pages in docs/presentation/.
    return f'href="{href[len("presentation/"):] if href.startswith("presentation/") else "../" + href}"'


def render(source, target, title, subtitle, sibling, nav_all):
    body = subprocess.run(["pandoc", "--from=gfm", "--to=html5", "--section-divs", "--wrap=none", str(DOCS / source)],
                          check=True, capture_output=True, text=True).stdout
    body = re.sub(r"<h1[^>]*>.*?</h1>", "", body, count=1, flags=re.S)
    body = re.sub(r'href="([^"]+)"', relink, body)
    counter = itertools.count(1)

    def paste(match):
        text = strip_tags(match.group(1)).rstrip("\n")
        i = next(counter)
        return (f'<div class="paste-field"><label for="paste-{i}">Select and copy</label>'
                f'<textarea id="paste-{i}" readonly rows="{text.count(chr(10)) + 1}" spellcheck="false">{text}</textarea></div>')

    body = re.sub(r"<pre[^>]*><code[^>]*>(.*?)</code></pre>", paste, body, flags=re.S)
    body = re.sub(r"(<table.*?</table>)", r'<div class="table-scroll">\1</div>', body, flags=re.S)

    # Level-2 sections run from their opening tag to the next one; the last ends at the level-1 close.
    starts = [m.start() for m in re.finditer(r'<section id="[^"]*" class="level2">', body)]
    ends = starts[1:] + [body.rfind("</section>")]
    nav = []
    for start, end in reversed(list(zip(starts, ends))):
        segment = body[start:end]
        anchor = re.match(r'<section id="([^"]*)"', segment).group(1)
        heading = strip_tags(re.search(r"<h2[^>]*>(.*?)</h2>", segment, re.S).group(1)).strip()
        label = heading.split(" · ")[0]
        if nav_all or re.match(r"\d+:\d\d$", label) or heading in ("Run of show", "Questions to have ready"):
            nav.append(f'<a href="#{anchor}">{label}</a>')
        if heading.startswith(COLLAPSED):
            body = body[:start] + f"<details><summary>{heading}</summary>{segment}</details>" + body[end:]

    css = (OUT / "presenter.css").read_text()
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title>{FONTS}
<style>
{css}</style></head><body><div class="wrap">
<header class="top"><div class="kicker">Chinook · client meeting · 35 minutes + 10 for questions</div><h1>{title}</h1><p class="sub">{subtitle}</p><p><a href="{sibling[0]}">{sibling[1]}</a> · <a href="client-deck.html">Client deck</a></p></header>
<nav aria-label="Jump to a section">{"".join(reversed(nav))}</nav>
<input type="checkbox" id="spoken-only"><label class="mode" for="spoken-only">Show spoken passages only</label>
<main>{body}</main>
<footer>Presenter notes, kept off the shared screen. Generated from docs/{source} by scripts/build_presenter_pages.py; edit the Markdown and rebuild.</footer>
</div></body></html>
"""
    (OUT / target).write_text(page)
    print("wrote", OUT / target)


if __name__ == "__main__":
    render("RUNBOOK.md", "promptbook.html", "Chinook client demo · full script",
           "Build with open source. Improve and operate with evidence from LangSmith.",
           ("cue-sheet.html", "Cue sheet"), nav_all=False)
    render("CUE_SHEET.md", "cue-sheet.html", "Chinook client demo · cue sheet",
           "Glance at this during the meeting. The full words are in the script.",
           ("promptbook.html", "Full script"), nav_all=True)
