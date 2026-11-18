"""Reconstruct text assets for the execution checker without touching the host filesystem."""

import posixpath
import re
from urllib.parse import unquote, urlsplit

from bs4 import BeautifulSoup


# Handle plain paths, Markdown headings, and filename comments in fenced outputs.
_FILENAME = re.compile(
    r"(?:#{1,6}\s+)?(?:file(?:name)?\s*:\s*)?[`*]*"
    r"((?:[\w.-]+/)*[\w.-]+\.[\w]+)[`*]*:?", re.IGNORECASE,
)
_FENCE = re.compile(r"^[ \t]*```([^\n]*)\n(.*?)^[ \t]*```[ \t]*$", re.MULTILINE | re.DOTALL)


def _filename(line):
    line = line.strip().removeprefix("<!--").removesuffix("-->").strip()
    line = line.removeprefix("/*").removesuffix("*/").removeprefix("//").strip()
    match = _FILENAME.fullmatch(line)
    if not match:
        return None
    path = match[1].removeprefix("./")
    if any(part in {"", ".", ".."} for part in path.split("/")):
        raise ValueError("Invalid artifact path")
    return path


def _entrypoint(files):
    if "index.html" in files:
        return "index.html"
    html = [p for p in files if p.lower().endswith((".html", ".htm"))]
    indexes = [p for p in html if posixpath.basename(p).lower() == "index.html"]
    if len(indexes) == 1:
        return indexes[0]
    if len(html) == 1:
        return html[0]
    raise ValueError("Cannot identify a unique HTML entry point")


def project_files(code: str, html: str | None) -> tuple[str, dict[str, str]]:
    """Resolve named fences and unambiguous anonymous HTML/CSS/JS blocks."""
    code = code.replace("\r\n", "\n")
    if "```" not in code:
        trailing_file = re.search(r"</html\s*>\s*\S", code, re.I)
        if html and code.strip().startswith("<") and not trailing_file and len(re.findall(r"<html\b", code, re.I)) <= 1:
            return "index.html", {"index.html": html}
        raise ValueError("Cannot reconstruct the generated project's files")

    files = {}
    unnamed = []
    end = 0
    for block in _FENCE.finditer(code):
        preceding = code[end:block.start()].strip().splitlines()
        info = block[1].strip().split()
        body = block[2]
        first_line, _, rest = body.partition("\n")
        path = _filename(" ".join(info)) or (_filename(info[-1]) if info else None)
        if not path and preceding:
            path = _filename(preceding[-1])
        if not path and first_line.strip().startswith(("<!--", "/*", "//")):
            path = _filename(first_line)
            if path:
                body = rest
        if path:
            if path in files:
                raise ValueError(f"Duplicate artifact path: {path}")
            files[path] = body
        else:
            unnamed.append((info[0].lower() if info else "", body))
        end = block.end()

    # Unclosed blocks cannot be replayed faithfully.
    if "```" in code[end:] or not (files or unnamed):
        raise ValueError("Incomplete file fences")
    assets = []
    for language, body in unnamed:
        if language in ("html", "htm") or (not language and body.lstrip().startswith("<")):
            if any(name.lower().endswith((".html", ".htm")) for name in files):
                raise ValueError("Multiple HTML files need explicit paths")
            files["index.html"] = body
        else:
            assets.append((language, body))
    entry = _entrypoint(files)
    document = BeautifulSoup(files[entry], "html.parser")
    for language, body in assets:
        if language in ("js", "javascript"):
            refs = [tag["src"] for tag in document.select("script[src]")]
        elif language == "css":
            refs = [tag["href"] for tag in document.select('link[rel~="stylesheet"][href]')]
        else:
            raise ValueError("An artifact block has no identifiable path")
        candidates = set()
        for ref in refs:
            url = urlsplit(ref)
            if not url.scheme and not url.netloc and url.path:
                path = posixpath.normpath(posixpath.join("/", posixpath.dirname(entry), unquote(url.path)))
                candidates.add(path.lstrip("/"))
        remaining = candidates - files.keys()
        if len(remaining) != 1:
            raise ValueError(f"Cannot assign an unnamed {language} block to a unique local file")
        files[remaining.pop()] = body
    return entry, files
