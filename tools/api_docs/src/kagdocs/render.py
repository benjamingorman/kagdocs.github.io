"""Write the static reference from a parsed Manual and Base.

Declarations come from catalogue, call sites from examples, and prose from
content. This module only decides how those pieces are presented.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from collections import Counter, defaultdict
from dataclasses import dataclass
from html import escape
from pathlib import Path

from kagdocs.catalogue import load_vanilla, source_text
from kagdocs.content import load_content
from kagdocs.examples import ExampleIndex
from kagdocs.model import CORE_TYPES, Symbol, split_params
from kagdocs.paths import project_dir, repository_root


def token_lines(tokens: list) -> list[list]:
    lines = [[]]
    for kind, text in tokens:
        parts = text.split("\n")
        for i, part in enumerate(parts):
            if i:
                lines.append([])
            if part:
                lines[-1].append([kind, part])
    return lines


def code_tokens(
    tokens: list,
    types: set[str],
    type_links: dict[str, str] | None = None,
    mark: tuple[int, int] | None = None,
) -> str:
    pieces = []
    offset = 0
    significant = [i for i, (kind, _) in enumerate(tokens) if kind not in {4, 5}]
    # Pair each significant token with the text of the one after it.
    following = {a: tokens[b][1] for a, b in zip(significant, significant[1:], strict=False)}
    for i, (kind, text) in enumerate(tokens):
        token_start = offset
        offset += len(text)
        if kind == 5:
            pieces.append(escape(text))
            continue
        css = {0: "punct", 1: "keyword", 2: "number", 3: "identifier", 4: "comment"}.get(
            kind, "punct"
        )
        if kind == 2 and text.startswith(('"', "'")):
            css = "string"
        if kind == 1 and not re.fullmatch(r"[A-Za-z_]\w*", text):
            css = "punct"
        if kind == 3:
            if text in types:
                css = "type"
            elif following.get(i) == "(":
                css = "function"
        # Close spans at every newline so each source line is valid markup.
        rendered = "\n".join(
            f'<span class="tok-{css}">{escape(part)}</span>' for part in text.split("\n")
        )
        if type_links and css == "type" and text in type_links:
            rendered = f'<a class="underline decoration-aqua/30 underline-offset-4" href="#{type_links[text]}">{rendered}</a>'
        if mark and (token_start, offset) == mark:
            rendered = f'<mark class="call-token">{rendered}</mark>'
        pieces.append(rendered)
    return "".join(pieces)


CALLABLE_KINDS = {"function", "method", "constructor", "hook", "funcdef"}


@dataclass
class ApiEntry:
    signatures: list[Symbol]

    @property
    def anchor(self) -> str:
        first = self.signatures[0]
        if len(self.signatures) == 1:
            return first.anchor
        identity = (first.kind, first.namespace, first.owner, first.name)
        slug = re.sub(r"[^A-Za-z0-9_-]+", "-", first.qualified).strip("-")
        return f"overloads-{slug}-{hashlib.sha256(repr(identity).encode()).hexdigest()[:12]}"


def api_entries(symbols: list[Symbol]) -> list[ApiEntry]:
    grouped = {}
    for s in symbols:
        key = (s.kind, s.namespace, s.owner, s.name) if s.kind in CALLABLE_KINDS else s.key()
        grouped.setdefault(key, ApiEntry([])).signatures.append(s)
    return list(grouped.values())


def source_name(path: str) -> str:
    return hashlib.sha256(path.encode()).hexdigest()[:20] + ".html"


def section_anchor(group: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", group).strip("-")
    return f"section-{slug}-{hashlib.sha256(group.encode()).hexdigest()[:8]}"


def navigation_category(symbol: Symbol, object_types: set[str]) -> str:
    if symbol.kind in {"enum", "enum-value"}:
        parts = symbol.namespace.split("::")
        for count in range(len(parts), 0, -1):
            owner = "::".join(parts[:count])
            if owner in object_types:
                return "TYPES" if owner in CORE_TYPES else "OBJECTS"
    return symbol.category


def lucide(name: str, classes: str = "h-3.5 w-3.5 shrink-0") -> str:
    svg = (project_dir() / "icons" / f"{name}.svg").read_text(encoding="utf-8")
    return svg.replace(
        "<svg",
        f'<svg aria-hidden="true" focusable="false" class="lucide lucide-{name} {classes}"',
        1,
    )


def page(title: str, body: str, prefix="") -> str:
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(title)} · KAG API</title><link rel="icon" href="{prefix}favicon.ico" type="image/x-icon"><script src="{prefix}theme.js"></script><link rel="stylesheet" href="{prefix}api.css">
<script defer src="{prefix}site.js"></script><script defer src="{prefix}search.js"></script></head><body>{body}</body></html>'''


def source_link(path: str, line: int, label: str, classes: str = "", reference: str = "") -> str:
    href = f"source/{source_name(path)}?ref={reference}#L{line}"
    return f'<a data-source-link class="inline-flex min-w-0 items-center gap-2 text-blue hover:underline underline-offset-4 {classes}" href="{href}"><span class="min-w-0 break-all">{escape(label)}</span>{lucide("file-code")}</a>'


def numbered(lines: list[str], first=1, highlight: tuple[int, int] | None = None) -> str:
    result = []
    for n, content in enumerate(lines, first):
        css = " call-line" if highlight and highlight[0] <= n <= highlight[1] else ""
        result.append(
            f'<span class="code-line{css}" id="L{n}"><a class="line-number" href="#L{n}" aria-label="Line {n}">{n}</a><span class="line-text">{content}</span></span>'
        )
    return "".join(result)


def parameter_table(s: Symbol, type_links: dict) -> str:
    if "(" not in s.declaration:
        return ""
    before, args = s.declaration.split("(", 1)
    args = args.rsplit(")", 1)[0]
    rows = []

    def linked_type(text):
        return re.sub(
            r"\b[A-Za-z_]\w*\b",
            lambda m: (
                f'<a class="text-aqua underline underline-offset-4" href="#{type_links[m[0]]}">{m[0]}</a>'
                if m[0] in type_links
                else m[0]
            ),
            escape(text),
        )

    for i, p in enumerate(split_params(args), 1):
        declaration, *default = p.split("=", 1)
        match = re.match(r"^(.*\S)\s+([A-Za-z_]\w*)$", declaration.strip())
        named = match and match[1] != "const" and match[2] not in {"in", "out", "inout", "const"}
        name, typ = (match[2], match[1]) if named else (f"argument {i}", declaration.strip())
        rows.append(
            f'<tr class="border-t border-border"><td class="py-3 pr-3 font-mono text-paper">{escape(name)}</td><td class="py-3 pr-3 font-mono">{linked_type(typ)}</td><td class="py-3 font-mono">{escape(default[0].strip()) if default else "—"}</td></tr>'
        )
    result = ""
    if rows:
        result += (
            '<div class="mt-5 overflow-x-auto"><table class="w-full text-left text-[11px] text-muted"><thead><tr><th class="pb-2 font-normal">Parameter</th><th class="pb-2 font-normal">Type</th><th class="pb-2 font-normal">Default</th></tr></thead><tbody>'
            + "".join(rows)
            + "</tbody></table></div>"
        )
    if s.kind != "constructor":
        returns = before[: -len(before.split()[-1])].strip()
        if returns:
            result += f'<p class="mt-4 text-xs text-muted">Returns <code>{linked_type(returns)}</code></p>'
    return result


def _copy_site_assets(output: Path) -> None:
    """Scripts, fonts, and licenses. CSS is written separately by the Tailwind build."""
    shutil.copy2(repository_root() / "favicon.ico", output / "favicon.ico")
    scripts = project_dir() / "js"
    for name in ("site.js", "search.js", "theme.js"):
        shutil.copy2(scripts / name, output / name)
    shutil.copytree(project_dir() / "fonts", output / "fonts", dirs_exist_ok=True)
    shutil.copy2(project_dir() / "KANAGAWA-LICENSE", output / "KANAGAWA-LICENSE")
    shutil.copy2(project_dir() / "LUCIDE-LICENSE", output / "LUCIDE-LICENSE")
    shutil.copy2(
        project_dir() / "vendor/tree-sitter-angelscript/LICENSE",
        output / "TREE-SITTER-ANGELSCRIPT-LICENSE",
    )


def render(data: dict, output: Path, context_lines: int = 5) -> dict:
    files = {f["path"]: f for f in data["files"]}
    symbols = load_vanilla(list(files.values()))
    prose, introductions, guides = load_content(repository_root() / "docs", symbols)
    entries = api_entries(symbols)
    symbol_entries = {s.anchor: entry for entry in entries for s in entry.signatures}
    object_types = {s.qualified for s in symbols if s.kind == "class"}
    symbol_groups = {s.anchor: (navigation_category(s, object_types), s.group) for s in symbols}
    group_keys = set(symbol_groups.values())
    name_counts = Counter(name for _, name in group_keys)
    group_ids = {
        (category, name): section_anchor(name if name_counts[name] == 1 else f"{category}:{name}")
        for category, name in group_keys
    }
    if len({s.anchor for s in symbols}) != len(symbols):
        raise ValueError("Duplicate API anchor")
    examples = ExampleIndex(symbols, list(files.values()), context_lines)
    types = {s.name for s in symbols if s.kind in {"class", "enum", "typedef"}}
    type_candidates = defaultdict(list)
    for s in symbols:
        if s.kind in {"class", "enum"}:
            type_candidates[s.name].append(s.anchor)
    type_links = {
        name: anchors[0] for name, anchors in type_candidates.items() if len(anchors) == 1
    }
    output.mkdir(parents=True, exist_ok=True)
    # TemporaryDirectory starts at 0700; published files must be traversable by
    # nginx's unprivileged worker after copytree preserves directory metadata.
    output.chmod(0o755)
    (output / "source").mkdir(exist_ok=True)
    (output / "sections").mkdir(exist_ok=True)
    highlighted = {}
    source_lines = {}
    line_tokens = {}
    linked_paths = {s.source for s in symbols if s.source}
    linked_paths.update(e.path for items in examples.examples.values() for e in items)
    for path in sorted(linked_paths):
        f = files[path]
        # Match the scanner's LF-based line/column coordinates exactly.
        highlighted[path] = code_tokens(f["tokens"], types).split("\n")
        source_lines[path] = source_text(f).split("\n")
        line_tokens[path] = token_lines(f["tokens"])
        body = f'<header class="sticky top-0 z-10 border-b border-border bg-rail px-6 py-4"><a id="source-back" href="../index.html" class="text-blue">← API reference</a><h1 class="mt-2 break-all font-mono text-sm">{escape(path)}</h1></header><main class="p-4"><pre class="source-code"><code>{numbered(highlighted[path])}</code></pre></main>'
        (output / "source" / source_name(path)).write_text(
            page(path, body, "../"), encoding="utf-8"
        )
    nav_entries, sections, signature_rows = defaultdict(list), defaultdict(list), defaultdict(list)
    links = []
    # One navbar row per overload family, and one description block per signature.
    for s in symbols:
        group = symbol_groups[s.anchor]
        entry = symbol_entries[s.anchor]
        first_signature = s is entry.signatures[0]
        display = s.name + ("()" if "(" in s.declaration else "")
        if first_signature:
            aliases = (
                " ".join(v.anchor for v in entry.signatures) if len(entry.signatures) > 1 else ""
            )
            declarations_title = "\n".join(v.declaration for v in entry.signatures)
            count = (
                f'<span class="nav-count">{len(entry.signatures)}</span>'
                if len(entry.signatures) > 1
                else ""
            )
            nav_entries[group].append(
                f'<a class="nav-entry text-muted" data-section="{group_ids[group]}" data-aliases="{aliases}" data-signature-count="{len(entry.signatures)}" data-search-name="{escape(s.name, quote=True)}" data-search-label="{escape(s.qualified, quote=True)}" data-search-kind="{s.kind}" href="#{entry.anchor}" title="{escape(declarations_title, quote=True)}"><span>{escape(display)}</span>{count}<span class="nav-eye" aria-hidden="true" title="Currently in view">{lucide("eye")}</span></a>'
            )
        description = ""
        if first_signature:
            description = f'<p class="text-[10px] tracking-wide text-muted">{escape(s.group)} / {escape(s.kind)}</p><h2 class="mt-3 break-words font-mono text-xl font-bold text-paper"><a href="#{entry.anchor}">{escape(s.qualified)}</a></h2>'
        if len(entry.signatures) > 1:
            number = next(i for i, v in enumerate(entry.signatures, 1) if v is s)
            description += f'<h3 class="mt-5 text-xs font-medium text-muted">Signature {number} of {len(entry.signatures)}</h3>'
        signature_tokens = s.tokens
        signature = (
            code_tokens(signature_tokens, types, type_links)
            if signature_tokens
            else escape(s.declaration)
        )
        if s.kind == "hook":
            signature_id = f"{s.anchor}-signature"
            description += f'<div class="signature relative flex items-center gap-3"><pre class="min-w-0 flex-1 overflow-x-auto"><code id="{signature_id}">{signature}</code></pre><button type="button" class="flex shrink-0 items-center self-center rounded p-2 text-muted hover:bg-panel hover:text-paper" data-copy="{signature_id}" aria-label="Copy hook signature" title="Copy hook signature">{lucide("copy")}<span class="sr-only" data-copy-label aria-live="polite"></span></button></div>'
        else:
            description += f'<pre class="signature"><code>{signature}</code></pre>'
        description += parameter_table(s, type_links)
        if first_signature:
            description += prose.get((s.kind, s.qualified), "")
        if s.kind == "typedef":
            description += '<p class="mt-5 text-sm text-muted">Manual incomplete: this record gives an underlying type but omits its alias name.</p>'
        if s.source:
            links.append((s.source, s.line))
            description += source_link(
                s.source, s.line, f"{Path(s.source).name}:{s.line}", "mt-5 text-xs", s.anchor
            )
        cards = []
        for idx, example in enumerate(examples.examples[s.key()]):
            block_id = f"{s.anchor}-example-{idx}"
            lines = highlighted[example.path][example.first - 1 : example.last]
            actual = source_lines[example.path][example.call_first - 1]
            if actual[example.column : example.column + len(example.token)] != example.token:
                raise ValueError(
                    f"Example token mismatch for {s.qualified}: {example.path}:{example.call_first}"
                )
            lines[example.call_first - example.first] = code_tokens(
                line_tokens[example.path][example.call_first - 1],
                types,
                mark=(example.column, example.column + len(example.token)),
            )
            content = numbered(lines, example.first, (example.call_first, example.call_first))
            content = re.sub(
                r' id="L(\d+)"', lambda m, block=block_id: f' id="{block}-L{m[1]}"', content
            )
            content = re.sub(
                r'href="#L(\d+)"',
                lambda m, path=example.path, anchor=s.anchor: (
                    f'data-source-link href="source/{source_name(path)}?ref={anchor}#L{m[1]}"'
                ),
                content,
            )
            links.append((example.path, example.call_first))
            cards.append(
                f'<figure class="mb-6 overflow-hidden rounded-lg"><figcaption class="bg-rail px-4 py-3">{source_link(example.path, example.call_first, f"{example.path}:{example.call_first}", "text-[11px]", s.anchor)}</figcaption><pre class="source-code py-3" id="{block_id}"><code>{content}</code></pre></figure>'
            )
        signature_anchor = f' id="{s.anchor}"' if len(entry.signatures) > 1 else ""
        signature_rows[entry.anchor].append(
            f'<div class="api-section scroll-mt-4"{signature_anchor}><div class="description"><div class="mx-auto max-w-[70ch]">{description}</div></div><div class="examples">{"".join(cards)}</div></div>'
        )
    for entry in entries:
        group = symbol_groups[entry.signatures[0].anchor]
        sections[group].append(
            f'<section class="api-entry scroll-mt-4" id="{entry.anchor}">{"".join(signature_rows[entry.anchor])}</section>'
        )
    nav, manifest = [], []
    # Guides first, then the Manual categories. Globals stays above the object list.
    category_order = {"GUIDES": 0, "HOOKS": 1, "TYPES": 2, "GLOBALS": 3, "OBJECTS": 4}
    for guide in guides:
        group = ("GUIDES", guide["title"])
        anchor = "guide-" + guide["slug"]
        group_ids[group] = anchor
        nav_entries[group].append(
            f'<a class="nav-entry text-muted" data-section="{anchor}" data-aliases="" data-signature-count="0" data-search-name="{escape(guide["title"], quote=True)}" data-search-label="{escape(guide["title"], quote=True)}" data-search-kind="guide" href="#{anchor}-article" title="{escape(guide["title"], quote=True)}"><span>{escape(guide["title"])}</span><span class="nav-eye" aria-hidden="true" title="Currently in view">{lucide("eye")}</span></a>'
        )
        sections[group].append(
            f'<section class="api-entry guide-content" id="{anchor}-article"><div class="markdown prose-guide">{guide["html"]}</div></section>'
        )
    last_category = None
    category_sizes = Counter(category for category, _ in nav_entries)
    seen_letters = set()
    guide_order = {g["title"]: g["order"] for g in guides}
    for category, group in sorted(
        nav_entries,
        key=lambda key: (
            category_order[key[0]],
            guide_order.get(key[1], 0) if key[0] == "GUIDES" else 0,
            key[1] != "Globals",
            key[1].casefold(),
        ),
    ):
        children_entries = nav_entries[(category, group)]
        if category != last_category:
            if last_category is not None:
                nav.append("</details>")
            nav.append(
                f'<details class="group/category" id="category-{category.lower()}" open><summary class="nav-category list-none cursor-pointer [&::-webkit-details-marker]:hidden"><h2 class="flex w-full items-center justify-between gap-2 text-[10px] font-bold uppercase tracking-[.16em]"><span>{category}</span><span class="nav-caret transition-transform group-open/category:rotate-90" aria-hidden="true">▸</span></h2></summary>'
            )
            last_category = category
            seen_letters = set()
        anchor = group_ids[(category, group)]
        children = f"nav-{anchor}"
        letter_slot = ""
        # One badge per letter, and only in categories long enough to be worth jumping.
        if category_sizes[category] > 5:
            letter = group[0].upper()
            badge = ""
            if "A" <= letter <= "Z" and letter not in seen_letters:
                badge = f'<span class="nav-letter">{letter}</span>'
                seen_letters.add(letter)
            letter_slot = f'<span class="nav-letter-slot" aria-hidden="true">{badge}</span>'
        nav.append(
            f'<div class="nav-group"><a class="nav-group-link" data-section="{anchor}" data-search-name="{escape(group, quote=True)}" data-search-label="{escape(group, quote=True)}" data-search-kind="section" href="#{anchor}" aria-expanded="false" aria-controls="{children}">{letter_slot}<span class="nav-group-label min-w-0 flex-1">{escape(group)}</span><span class="nav-caret" aria-hidden="true">▸</span></a><div class="bg-ink" id="{children}" hidden>{"".join(children_entries)}</div></div>'
        )
        intro = introductions.get((category, group), "")
        heading_style = " guide-heading" if category == "GUIDES" else ""
        section_html = (
            f'<header class="api-section api-heading{heading_style}" id="{anchor}"><div class="description"><h1 class="mx-auto max-w-[70ch] font-mono text-2xl font-bold leading-8">{escape(group)}</h1>{intro}</div><div class="examples"></div></header>'
            + "".join(sections[(category, group)])
        )
        payload = f"window.KAGDocs.sectionLoaded({json.dumps(anchor)},{json.dumps(section_html, ensure_ascii=True)});\n"
        filename = f"sections/{anchor}.js"
        (output / filename).write_text(payload, encoding="utf-8")
        manifest.append(
            {
                "id": anchor,
                "name": group,
                "category": category,
                "file": filename,
                "anchors": (
                    [anchor + "-article"]
                    if category == "GUIDES"
                    else [
                        e.anchor
                        for e in entries
                        if symbol_groups[e.signatures[0].anchor] == (category, group)
                    ]
                ),
                "signatures": [
                    s.anchor for s in symbols if symbol_groups[s.anchor] == (category, group)
                ],
            }
        )
    if last_category is not None:
        nav.append("</details>")
    (output / "sections.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    body = f"""<button id="menu" aria-controls="navigation" aria-expanded="false" class="fixed right-4 top-4 z-40 rounded border border-border bg-rail px-3 py-2 text-xs lg:hidden">API menu</button>
<aside id="navigation" aria-label="API navigation" class="nav-rail fixed inset-y-0 left-0 z-30 w-[280px] border-r border-border bg-rail max-lg:hidden">
<div class="flex items-center justify-between gap-2 pl-5 pr-4 pt-6 pb-4"><a href="#overview"><strong class="block text-xl tracking-tight">KAG<span class="font-normal text-muted"> / api</span></strong></a><button id="theme-toggle" class="rounded-md p-2 text-muted hover:bg-panel hover:text-paper [perspective:120px]" type="button" aria-label="Switch to Kanagawa Lotus theme" title="Switch to Kanagawa Lotus"><span class="theme-flipper" aria-hidden="true"><span class="theme-face" data-theme-icon="wave">{lucide("moon", "h-4 w-4")}</span><span class="theme-face" data-theme-icon="lotus">{lucide("sun", "h-4 w-4")}</span><span class="theme-face" data-theme-icon="dragon">{lucide("flame", "h-4 w-4")}</span></span></button></div>
<div class="px-4 pb-4"><button id="search-open" type="button" class="search-launch" aria-haspopup="dialog" aria-controls="quick-search">{lucide("search", "h-4 w-4 shrink-0")}<span class="flex-1 text-left">Search API…</span><kbd id="search-shortcut" class="rounded border border-border px-1.5 py-0.5 text-[10px]">Ctrl K</kbd></button></div>
<p class="border-t border-border px-5 py-4 text-[11px] leading-5 text-muted">KAG build {escape(str(data["build"]))}</p>{"".join(nav)}</aside>
<dialog id="quick-search" class="quick-search" aria-labelledby="search-title">
<h2 id="search-title" class="sr-only">Search the KAG API</h2>
<div class="flex items-center gap-3 border-b border-border px-5 py-4">{lucide("search", "h-5 w-5 shrink-0 text-aqua")}<input id="search-input" type="search" role="combobox" aria-label="Search API names" aria-autocomplete="list" aria-controls="search-results" aria-expanded="false" autocomplete="off" spellcheck="false" placeholder="Search functions, methods, variables, objects…" class="min-w-0 flex-1 bg-transparent text-sm text-paper outline-none"><button id="search-close" class="rounded border border-border px-2 py-1 text-[10px] text-muted hover:bg-panel" type="button" aria-label="Close search">Esc</button></div>
<p id="search-status" class="px-5 py-3 text-xs text-muted" role="status"></p><div id="search-results" class="max-h-[55vh] overflow-y-auto overscroll-contain" role="listbox" aria-label="API search results"></div>
<p class="border-t border-border px-5 py-3 text-[11px] text-muted">↑ ↓ to navigate · Enter to open · Esc to close</p></dialog>
<main class="min-w-0 lg:ml-[280px]"><header id="overview" class="px-6 pt-6 pb-14 lg:px-10">
<p class="flex h-8 items-center text-sm text-aqua">Docs</p><h1 class="mt-4 text-4xl font-bold tracking-tight">KAG AngelScript API</h1>
<p class="mt-5 max-w-[110ch] text-sm leading-7 text-muted">Welcome to the King Arthur’s Gold AngelScript API docs!<br/>Here you can browse through all functions, objects, hooks, and globals used in the game. Where possible, code examples from the scripts in Base are given. There are also some community-authored modding guides for certain useful concepts such as TCPR.<br/>The contents of these docs are based on the KAG 'Manual' directory, which is generated automatically by the game to document the available AngelScript interface.</p>
<p class="mt-5 text-xs text-muted">{len(symbols):,} declarations · KAG build {escape(str(data["build"]))}</p>
<p class="mt-8 text-xs text-muted"><a class="text-blue underline underline-offset-4" href="https://github.com/rebelot/kanagawa.nvim">Kanagawa Theme</a> · <a class="text-blue underline underline-offset-4" href="https://www.nerdfonts.com/">CaskaydiaMono Nerd Font</a></p>
</header><div id="api-content" aria-live="polite"></div><noscript><p class="p-8">Enable JavaScript to navigate API sections.</p></noscript></main>"""
    html = page("Reference", body)
    ids = re.findall(r'\bid="([^"]+)"', html)
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate HTML IDs")
    route_ids = (
        {a for m in manifest for a in m["anchors"]}
        | {m["id"] for m in manifest}
        | {s.anchor for s in symbols}
        | {e.anchor for e in entries}
    )
    for target in re.findall(r'href="#([^"]+)"', html):
        if target not in set(ids) | route_ids:
            raise ValueError(f"Broken anchor: {target}")
    for path, line in links:
        if path not in highlighted or not 1 <= line <= len(highlighted[path]):
            raise ValueError(f"Broken source link: {path}:{line}")
    (output / "index.html").write_text(html, encoding="utf-8")
    _copy_site_assets(output)
    (output / "example-diagnostics.json").write_text(
        json.dumps(examples.diagnostics, indent=2) + "\n", encoding="utf-8"
    )
    (output / ".nojekyll").touch()
    report = {
        "vanilla_build": data["build"],
        "total": len(symbols),
        "entries": len(entries),
        "guides": len(guides),
        "with_examples": sum(bool(examples.examples[s.key()]) for s in symbols),
        "source_files": len(linked_paths),
        "sections": len(manifest),
        "example_context": context_lines,
    }
    (output / "catalogue.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report
