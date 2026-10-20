"""Validate the generated site without requiring a browser or HTTP server."""

from __future__ import annotations

import hashlib
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit


class Document(HTMLParser):
    """Ids, links, and navbar rows collected from one HTML page or section payload."""

    def __init__(self, path=None, text=None):
        super().__init__()
        self.ids, self.links, self.nav, self.sections, self.copies = set(), [], [], [], []
        self.remote_assets = set()
        self.search_entries = []
        self.feed(text if text is not None else path.read_text(encoding="utf-8"))

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if identifier := a.get("id"):
            if identifier in self.ids:
                raise ValueError(f"Duplicate ID: {identifier}")
            self.ids.add(identifier)
        if href := a.get("href") or a.get("src"):
            self.links.append(href)
            if tag != "a" and urlsplit(href).scheme:
                self.remote_assets.add(href)
        if "nav-entry" in a.get("class", "").split():
            self.nav.append(a["href"])
            self.search_entries.append(
                {
                    key: a.get(key)
                    for key in (
                        "data-search-name",
                        "data-search-label",
                        "data-search-kind",
                        "data-section",
                        "data-signature-count",
                        "data-aliases",
                    )
                }
            )
        if tag == "section" and "api-entry" in a.get("class", "").split():
            self.sections.append(a["id"])
        if target := a.get("data-copy"):
            self.copies.append(target)


_SECTION_PREFIX = "window.KAGDocs.sectionLoaded("
_THEME_TOKENS = (
    "#1f1f28",
    "#dcd7ba",
    "#f2ecbc",
    "#545464",
    "#181616",
    "#c5c9c5",
    "Helvetica Neue",
    "CaskaydiaMono Nerd Font",
    "grid-template-columns",
    "min-width:64rem",
)
_FONT_SHA256 = {
    "CaskaydiaMonoNerdFont-Regular.ttf": "11da96738758218cd47c1b885544259b6189b3d5b3b4f2e58d8fd7443e5ac549",
    "CaskaydiaMonoNerdFont-Bold.ttf": "ecb33715f3c82b238cdb4f0e289760570c86a441feb2a541daaee89ac140814b",
}


def _load_sections(output: Path, manifest: list, virtual_ids: set) -> dict:
    """Parse lazy section scripts. Their ids join the index ids for link checks."""
    sections = {}
    for section in manifest:
        payload = (output / section["file"]).read_text(encoding="utf-8")
        if not payload.startswith(_SECTION_PREFIX) or not payload.endswith(");\n"):
            raise ValueError("Invalid section payload")
        identifier, markup = json.loads("[" + payload[len(_SECTION_PREFIX) : -3] + "]")
        assert identifier == section["id"]
        document = Document(text=markup)
        assert set(section["anchors"]) == set(document.sections)
        assert set(section["signatures"]) <= document.ids
        assert identifier in document.ids
        assert not virtual_ids & document.ids, "Duplicate lazy section anchors"
        virtual_ids.update(document.ids)
        sections[identifier] = document
    return sections


def _fragment_ids(target: Path, index: Path, virtual_ids: set, documents: dict) -> set:
    if target == index:
        return virtual_ids
    if target in documents:
        return documents.get(target).ids
    return set()


def _check_links(output: Path, documents: dict, sections: list, virtual_ids: set) -> None:
    index = output / "index.html"
    # Section markup is not its own file. Check it as though it lived in the index.
    pages = list(documents.items()) + [(index, document) for document in sections]
    existing = {}
    for path, document in pages:
        for href in document.links:
            ref = urlsplit(href)
            if ref.scheme or ref.netloc:
                if ref.scheme in {"https", "http", "mailto"} and href not in document.remote_assets:
                    continue
                raise ValueError(f"Non-local asset or unexpected external link: {href}")
            target = (path.parent / unquote(ref.path)).resolve() if ref.path else path
            if target not in existing:
                existing[target] = target.is_relative_to(output) and target.is_file()
            if not existing[target]:
                raise ValueError(f"Broken local link in {path.name}: {href}")
            for return_anchor in parse_qs(ref.query).get("ref", []):
                if return_anchor not in virtual_ids:
                    raise ValueError(f"Broken source return anchor: {href}")
            if ref.fragment and unquote(ref.fragment) not in _fragment_ids(
                target, index, virtual_ids, documents
            ):
                raise ValueError(f"Broken source/section anchor: {href}")
        if not set(document.copies) <= document.ids:
            raise ValueError("Copy button points to absent code")


def _check_catalogue(main: Document, manifest: list, coverage: dict) -> None:
    anchors = {anchor for section in manifest for anchor in section["anchors"]}
    assert len(main.nav) == len(anchors) == coverage["entries"] + coverage["guides"], (
        "Sidebar does not contain every entry"
    )
    assert {href[1:] for href in main.nav} == anchors
    assert len(main.search_entries) == coverage["entries"] + coverage["guides"]
    assert all(
        all(value for key, value in entry.items() if key != "data-aliases")
        for entry in main.search_entries
    ), "Missing quicksearch metadata"
    assert (
        sum(int(entry["data-signature-count"]) for entry in main.search_entries)
        == coverage["total"]
    )
    signatures = [anchor for section in manifest for anchor in section["signatures"]]
    assert len(signatures) == len(set(signatures)) == coverage["total"]
    routed = anchors | {
        alias for entry in main.search_entries for alias in entry["data-aliases"].split()
    }
    assert set(signatures) <= routed, "Signature deep link has no navigation route"


def _check_assets(output: Path) -> None:
    css = (output / "api.css").read_text(encoding="utf-8")
    for url in re.findall(r'url\(["\']?([^\)"\']+)', css):
        if not (output / url).is_file():
            raise ValueError(f"Missing stylesheet asset: {url}")
    for token in _THEME_TOKENS:
        assert token.casefold() in css.casefold(), f"Missing theme/responsive style: {token}"
    for name, digest in _FONT_SHA256.items():
        assert hashlib.sha256((output / "fonts" / name).read_bytes()).hexdigest() == digest, (
            f"Font checksum differs: {name}"
        )


def check(output: Path) -> dict:
    output = output.resolve()
    documents = {path.resolve(): Document(path) for path in output.rglob("*.html")}
    main = documents[output / "index.html"]
    manifest = json.loads((output / "sections.json").read_text(encoding="utf-8"))
    virtual_ids = set(main.ids)
    sections = _load_sections(output, manifest, virtual_ids)
    assert not main.sections, "The index must not eagerly render the API"
    all_sections = list(sections.values())
    _check_links(output, documents, all_sections, virtual_ids)
    _check_catalogue(main, manifest, json.loads((output / "catalogue.json").read_text()))
    _check_assets(output)
    return {
        "html_pages": len(documents),
        "lazy_sections": len(sections),
        "initial_api_entries": len(main.sections),
        "sidebar_entries": len(main.nav),
        "searchable_entries": len(main.search_entries),
        "local_links": sum(
            len(document.links) for document in list(documents.values()) + all_sections
        ),
    }
