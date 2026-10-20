"""Validated Markdown documentation independent of the API declaration source."""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

import markdown
import yaml


def read_markdown(path: Path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8")
    match = re.match(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|$)([\s\S]*)", text, re.S)
    if not match:
        raise ValueError(f"{path}: expected YAML frontmatter delimited by ---")
    try:
        metadata = yaml.safe_load(match[1])
    except yaml.YAMLError as error:
        raise ValueError(f"{path}: invalid YAML: {error}") from error
    if not isinstance(metadata, dict):
        raise ValueError(f"{path}: frontmatter must be a mapping")
    body = match[2].strip()
    # Repository-authored Markdown is trusted; fenced code is escaped by Markdown.
    rendered = markdown.markdown(body, extensions=["fenced_code", "tables", "sane_lists"])
    return metadata, f'<div class="markdown">{rendered}</div>' if rendered else ""


def families(symbols) -> dict:
    """Group overload signatures that share a kind and a qualified name."""
    result = defaultdict(list)
    for symbol in symbols:
        result[(symbol.kind, symbol.qualified)].append(symbol)
    return result


def _load_api(directory: Path, symbols, known: dict) -> tuple[dict, dict]:
    prose, introductions = {}, {}
    for path in sorted((directory / "api").rglob("*.md")):
        meta, html = read_markdown(path)
        kind, name, signatures = (meta.get(key) for key in ("kind", "symbol", "signatures"))
        if (
            not isinstance(kind, str)
            or not isinstance(name, str)
            or not isinstance(signatures, list)
            or not all(isinstance(item, str) for item in signatures)
        ):
            raise ValueError(f"{path}: require kind, symbol, and a list of signature strings")
        key = kind, name
        if key in prose:
            raise ValueError(f"{path}: duplicate documentation for {kind} {name}")
        if kind == "namespace":
            matches = [
                symbol for symbol in symbols if symbol.namespace == name and not symbol.owner
            ]
            if not matches or signatures:
                raise ValueError(f"{path}: namespace must exist and use signatures: []")
            introductions[("GLOBALS", name)] = html
        else:
            if key not in known:
                raise ValueError(f"{path}: unknown API symbol {kind} {name}")
            expected = {symbol.source_declaration for symbol in known[key]}
            if len(signatures) != len(set(signatures)) or set(signatures) != expected:
                raise ValueError(
                    f"{path}: stale signatures for {name}; expected {sorted(expected)!r}"
                )
        prose[key] = html
    return prose, introductions


def _load_guides(directory: Path) -> list[dict]:
    guides = []
    for path in sorted((directory / "guides").glob("*.md")):
        meta, html = read_markdown(path)
        title, order = meta.get("title"), meta.get("order")
        if not isinstance(title, str) or not title.strip() or not isinstance(order, int):
            raise ValueError(f"{path}: guide requires title and integer order")
        if any(guide["title"] == title for guide in guides):
            raise ValueError(f"{path}: duplicate guide title {title}")
        guides.append({"slug": path.stem, "title": title, "order": order, "html": html})
    guides.sort(key=lambda guide: (guide["order"], guide["title"]))
    return guides


def load_content(directory: Path, symbols) -> tuple[dict, dict, list]:
    """Load authored API prose and guides. Missing prose is allowed."""
    directory = Path(directory)
    prose, introductions = _load_api(directory, symbols, families(symbols))
    return prose, introductions, _load_guides(directory)


def scaffold(directory: Path, symbols, selection: str) -> list[Path]:
    """Create missing Markdown templates. Existing files are left untouched."""
    directory = Path(directory)
    known = families(symbols)
    selected = [
        (key, value) for key, value in known.items() if selection == "*" or key[1] == selection
    ]
    if not selected:
        raise ValueError(
            f"No Manual symbol matches {selection!r}; use a qualified name, e.g. CBlob::getHealth"
        )
    created = []
    for (kind, qualified), members in selected:
        first = members[0]
        if first.owner:
            parent = directory / "api/objects" / first.namespace.replace("::", "/") / first.owner
        elif kind == "class":
            parent = directory / "api/objects" / qualified.replace("::", "/")
        elif first.namespace:
            parent = directory / "api/namespaces" / first.namespace.replace("::", "/")
        else:
            parent = directory / "api/globals"
        name = "_index" if kind == "class" else first.name
        name = re.sub(r"[^A-Za-z0-9_-]", "_", name)
        # Properties/functions with the same name must have distinct file paths.
        if any(other_kind != kind and other_name == qualified for other_kind, other_name in known):
            name += "-" + kind
        parent.mkdir(parents=True, exist_ok=True)
        path = parent / (name + ".md")
        metadata = {
            "kind": kind,
            "symbol": qualified,
            "signatures": [s.source_declaration for s in members],
        }
        try:
            with path.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(
                    "---\n"
                    + yaml.safe_dump(metadata, sort_keys=False, allow_unicode=True)
                    + "---\n"
                )
            created.append(path)
        except FileExistsError:
            pass
    return created
