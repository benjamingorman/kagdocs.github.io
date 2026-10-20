"""Turn Manual text files into one declaration per API symbol."""

from pathlib import Path

from kagdocs.inputs import lex
from kagdocs.model import Symbol, parse_decl

# Class names taken from an object filename are not scanned as source, so the
# highlighter receives the identifier token directly.
_IDENTIFIER = 3


def source_text(file: dict) -> str:
    """Rejoin scanner tokens. Line breaks stay inside the token text."""
    return "".join(token for _, token in file["tokens"])


def _remember(
    found: dict, text: str, kind: str, path: str, line: int, owner: str = "", namespace: str = ""
) -> None:
    symbol = parse_decl(text, kind, owner, namespace, source=path, line=line, tokens=lex(text))
    if symbol.kind == "class":
        symbol.tokens = [[_IDENTIFIER, symbol.name]]
    found[symbol.key()] = symbol


def _declarations(file: dict):
    """Yield declaration lines, keeping the raw text so indentation still means nesting."""
    for line, raw in enumerate(source_text(file).splitlines(), 1):
        text = raw.strip().lstrip("\ufeff")
        if text and not text.startswith(("--", "#")):
            yield line, raw, text


def _member_kind(text: str) -> str:
    return "method" if "(" in text else "property"


def _load_flat(found: dict, file: dict, kind: str) -> None:
    path = file["path"]
    for line, _raw, text in _declarations(file):
        _remember(found, text, kind, path, line)


def _load_objects_list(found: dict, file: dict) -> None:
    """``Objects.txt`` indents members under an unindented class name."""
    path = file["path"]
    owner = ""
    for line, raw, text in _declarations(file):
        if not raw[0].isspace():
            owner = text
            _remember(found, text, "class", path, line)
        else:
            _remember(found, text, _member_kind(text), path, line, owner)


def _load_object_file(found: dict, file: dict) -> None:
    """A per-object file is the class. Its lines are members, not a repeated class heading."""
    path = file["path"]
    owner = Path(path).stem
    _remember(found, owner, "class", path, 2)
    for line, _raw, text in _declarations(file):
        _remember(found, text, _member_kind(text), path, line, owner)


def _load_enums(found: dict, file: dict) -> None:
    path = file["path"]
    owner = ""
    for line, raw, text in _declarations(file):
        if not raw[0].isspace():
            owner = text
            _remember(found, text, "enum", path, line)
        else:
            _remember(found, text, "enum-value", path, line, owner)


def load_vanilla(files: list[dict]) -> list[Symbol]:
    """Merge aggregate Manual lists with the per-object files.

    Object files carry properties that ``Objects.txt`` omits. ``Objects.txt``
    still contributes addon types that have no file of their own. Individual
    files are applied last so they win when a declaration appears in both.
    """
    found: dict = {}
    # ``/Objects/`` sorts after the aggregate lists, so a per-object file replaces
    # the same declaration from Objects.txt.
    ordered = sorted(files, key=lambda item: ("/Objects/" in item["path"], item["path"]))
    for file in ordered:
        path = file["path"]
        if not path.startswith("Manual/interface/") or path.endswith("allowlist.txt"):
            continue
        name = Path(path).name
        if name == "Objects.txt":
            _load_objects_list(found, file)
        elif "/Objects/" in path:
            _load_object_file(found, file)
        elif name == "Functions.txt":
            _load_flat(found, file, "function")
        elif name == "Variables.txt":
            _load_flat(found, file, "property")
        elif name == "Hooks.txt":
            _load_flat(found, file, "hook")
        elif name == "Enums.txt":
            _load_enums(found, file)
        elif name == "TypeDefs.txt":
            # The dump lists underlying types and omits the alias names.
            _load_flat(found, file, "typedef")
    return list(found.values())
