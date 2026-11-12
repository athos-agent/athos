"""Build each article (articles/<slug>/README.md) into articles/<slug>/index.html for the GitHub Pages site.

Standard library only, like the gallery: `python3 articles/build.py`. A video.mp4 (and poster.jpg) beside the README
is shown at the top of the page, under the byline.
"""
import html
import re
from pathlib import Path

HERE = Path(__file__).parent


def inline(text: str) -> str:
    t = html.escape(text, quote=False)
    t = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', t)
    t = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"(?<![\w*])\*([^*]+)\*(?![\w*])", r"<em>\1</em>", t)
    t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
    return t


def body(md: str, video: bool) -> tuple[str, str]:
    title, out, para, items = "", [], [], []

    def flush():
        if para:
            out.append(f"<p>{inline(' '.join(para))}</p>")
            para.clear()
        if items:
            out.append("<ul>" + "".join(f"<li>{inline(i)}</li>" for i in items) + "</ul>")
            items.clear()

    for line in md.splitlines():
        s = line.strip()
        if s.startswith("# "):
            title = s[2:]
        elif s.startswith("## "):
            flush()
            out.append(f"<h2>{inline(s[3:])}</h2>")
        elif s.startswith("- "):
            if para:
                flush()
            items.append(s[2:])
        elif not s:
            flush()
        elif items and line.startswith("  "):
            items[-1] += " " + s
        elif s.startswith("**Video") and video:
            flush()
            out.append('<video controls playsinline preload="metadata" poster="poster.jpg" src="video.mp4"></video>')
        else:
            para.append(s)
    flush()
    return title, "\n".join(out)


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="{desc}">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{desc}">
<meta property="og:image" content="poster.jpg">
<meta property="og:type" content="article">
<link href="https://fonts.googleapis.com/css2?family=EB+Garamond:wght@500;600&family=Inter:wght@400;600&display=swap" rel="stylesheet">
<style>
  :root {{ --bg: #f7f6f3; --ink: #1f1f1f; --dim: #6b6862; --acc: #c15f3c; --rule: #e2dfd8; }}
  @media (prefers-color-scheme: dark) {{ :root {{ --bg: #1c1c1a; --ink: #f0eee6; --dim: #a6a39a; --acc: #e08a65; --rule: #3d3c38; }} }}
  body {{ margin: 0; background: var(--bg); color: var(--ink); font: 18px/1.65 Inter, system-ui, sans-serif; }}
  main {{ max-width: 720px; margin: 0 auto; padding: 48px 16px 80px; }}
  h1 {{ font: 600 44px/1.1 "EB Garamond", Georgia, serif; letter-spacing: -0.01em; margin: 0 0 10px; }}
  h2 {{ font: 600 28px/1.2 "EB Garamond", Georgia, serif; margin: 44px 0 10px; }}
  a {{ color: var(--acc); }}
  em {{ color: var(--dim); }}
  ul {{ padding-left: 22px; }} li {{ margin: 6px 0; }}
  video {{ width: 100%; border-radius: 10px; margin: 20px 0 8px; background: #000; }}
  code {{ font-size: 0.9em; }}
  footer {{ margin-top: 56px; padding-top: 18px; border-top: 1px solid var(--rule); color: var(--dim); font-size: 15px; }}
</style>
</head>
<body>
<main>
<h1>{title}</h1>
{body}
<footer><a href="../../">Athos</a> · <a href="https://github.com/athos-agent/athos">github.com/athos-agent/athos</a></footer>
</main>
</body>
</html>
"""


def build() -> list[Path]:
    done = []
    for md in sorted(HERE.glob("*/README.md")):
        title, html_body = body(md.read_text(), (md.parent / "video.mp4").exists())
        first = next((l for l in md.read_text().split("\n\n")[2:] if l.strip() and not l.startswith(("*", "#"))), "")
        desc = html.escape(" ".join(first.split())[:200], quote=True)
        (md.parent / "index.html").write_text(PAGE.format(title=html.escape(title), desc=desc, body=html_body))
        done.append(md.parent / "index.html")
    return done


if __name__ == "__main__":
    for p in build():
        print(p)
