import html
import re
import tempfile
import webbrowser
from pathlib import Path

MERMAID_BLOCK_RE = re.compile(r"```mermaid\s*\n(.*?)```", re.DOTALL)

_HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>{title}</title>
<script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
<script>mermaid.initialize({{ startOnLoad: true }});</script>
<style>
body {{ font-family: sans-serif; margin: 24px; }}
.diagram {{ margin-bottom: 40px; }}
</style>
</head>
<body>
<h1>{title}</h1>
{diagrams}
</body>
</html>
"""


def extract_mermaid_blocks(markdown_text: str) -> list[str]:
    """
    Markdown中の ```mermaid ...``` ブロックを抽出する
    """
    return [m.strip() for m in MERMAID_BLOCK_RE.findall(markdown_text)]


def open_mermaid_in_browser(markdown_text: str, title: str) -> None:
    """
    Mermaidブロックを一時HTMLに埋め込み、既定のブラウザで開く
    （mermaid.js はCDNから読み込むためインターネット接続が必要）
    """
    blocks = extract_mermaid_blocks(markdown_text)
    if not blocks:
        return

    diagrams = "\n".join(
        f'<div class="diagram"><pre class="mermaid">{html.escape(block)}</pre></div>'
        for block in blocks
    )

    content = _HTML_TEMPLATE.format(title=html.escape(title), diagrams=diagrams)

    tmp_dir = Path(tempfile.gettempdir()) / "mylauncher_mermaid"
    tmp_dir.mkdir(exist_ok=True)

    out_path = tmp_dir / f"{re.sub(r'[^A-Za-z0-9_-]', '_', title)}.html"
    out_path.write_text(content, encoding="utf-8")

    webbrowser.open(out_path.as_uri())
