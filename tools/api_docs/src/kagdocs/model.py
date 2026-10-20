"""Manual declaration model shared by the parser, matcher, and HTML renderer."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

BUILTIN_TYPES = {"any", "array", "string", "dictionary", "dictionaryIter", "dictionaryValue"}
CORE_TYPES = BUILTIN_TYPES | {"Vec2f", "SColor", "Vertex"}
ALIASES = {
    "u8": "uint8",
    "u16": "uint16",
    "u32": "uint",
    "u64": "uint64",
    "s8": "int8",
    "s16": "int16",
    "s32": "int",
    "s64": "int64",
    "f32": "float",
    "f64": "double",
    "uint32": "uint",
    "int32": "int",
}


def compact(text: str) -> str:
    """Fold integer aliases and drop whitespace so two spellings of one signature compare equal."""
    text = re.sub(r"\b(?:" + "|".join(ALIASES) + r")\b", lambda m: ALIASES[m[0]], text)
    return re.sub(r"\s+", "", text)


def split_params(text: str) -> list[str]:
    """Split on top-level commas. Nested brackets and quoted commas stay inside a parameter."""
    result, start, depth, quote = [], 0, 0, ""
    for i, c in enumerate(text):
        if quote:
            if c == quote and (i == 0 or text[i - 1] != "\\"):
                quote = ""
        elif c in "\"'":
            quote = c
        elif c in "(<[{":
            depth += 1
        elif c in ")>]}":
            depth -= 1
        elif c == "," and depth == 0:
            result.append(text[start:i].strip())
            start = i + 1
    if text[start:].strip():
        result.append(text[start:].strip())
    return result


def parameter(text: str, defaults: bool = True) -> str:
    """Normalize one parameter. A trailing name is dropped; ``in``, ``out``, and ``const`` stay."""
    parts = text.split("=", 1)
    declaration = parts[0].strip()
    match = re.match(r"^(.*\S)\s+([A-Za-z_]\w*)$", declaration)
    if match and match[1] != "const" and match[2] not in {"in", "out", "inout", "const"}:
        declaration = match[1]
    return compact(declaration) + ("=" + compact(parts[1]) if len(parts) == 2 and defaults else "")


@dataclass
class Symbol:
    kind: str
    name: str
    declaration: str
    owner: str = ""
    namespace: str = ""
    return_type: str = ""
    source: str = ""
    line: int = 0
    tokens: list = field(default_factory=list)
    source_declaration: str = ""

    @property
    def qualified(self) -> str:
        return "::".join(x for x in (self.namespace, self.owner, self.name) if x)

    @property
    def group(self) -> str:
        """Sidebar group: the owning type, or a top-level bucket such as Globals."""
        if self.kind == "hook":
            return "Hooks"
        if self.kind in {"class", "enum"}:
            return self.qualified
        return "::".join(x for x in (self.namespace, self.owner) if x) or {
            "class": "Types",
            "enum": "Enums",
            "typedef": "Type aliases",
            "funcdef": "Function types",
        }.get(self.kind, "Globals")

    @property
    def category(self) -> str:
        """Top-level navbar section: HOOKS, TYPES, OBJECTS, or GLOBALS."""
        if self.kind == "hook":
            return "HOOKS"
        if self.kind in {"typedef", "funcdef"} and not self.owner:
            return "TYPES"
        host = self.owner or (self.name if self.kind == "class" else "")
        if not self.namespace and host.split("<", 1)[0] in CORE_TYPES:
            return "TYPES"
        if self.kind in {"class", "method", "constructor"} or (
            self.owner and self.kind in {"property", "funcdef"}
        ):
            return "OBJECTS"
        return "GLOBALS"

    def key(self, defaults: bool = True) -> tuple:
        decl = self.declaration
        if "(" in decl:
            before, rest = decl.split("(", 1)
            args, suffix = rest.rsplit(")", 1)
            result = before.rsplit(self.name, 1)[0].strip()
            if self.kind == "constructor":
                result, suffix = "", ""
            signature = (
                compact(result),
                tuple(parameter(p, defaults) for p in split_params(args)),
                compact(suffix),
            )
        elif self.kind == "enum-value":
            signature = ()
        else:
            signature = (compact(decl),)
        return self.kind, self.namespace, self.owner, self.name, signature

    @property
    def anchor(self) -> str:
        slug = re.sub(r"[^A-Za-z0-9_-]+", "-", self.qualified).strip("-")
        digest = hashlib.sha256(repr(self.key()).encode()).hexdigest()[:12]
        return f"{slug}-{digest}"


def parse_decl(text: str, kind: str, owner: str = "", namespace: str = "", **kwargs) -> Symbol:
    """Parse one Manual declaration line into a symbol.

    Constructors are written as ``<constructor>(...)``. Namespace-qualified
    names are split so the symbol name itself stays unqualified.
    """
    text = text.strip()
    original = text
    if "::" in owner:
        namespace, owner = owner.rsplit("::", 1)
    if "(" in text:
        before = text.split("(", 1)[0].strip()
        name = before.split()[-1]
        if "::" in name:
            namespace, name = name.rsplit("::", 1)
            text = text.replace(before, before[: -len(before.split()[-1])] + name, 1)
        if name == "<constructor>" or kind == "constructor":
            kind, name = "constructor", owner
            text = owner + "(" + text.split("(", 1)[1]
        result = before[: -len(before.split()[-1])].strip()
    elif kind in {"property", "typedef"}:
        # Manual globals can put the namespace before the type (Maths::float Pi).
        match = re.match(r"^(\w+)::(\w+)\s+", text)
        if match:
            namespace = match[1]
            text = text[len(namespace) + 2 :]
        name, result = text.split()[-1], ""
    else:
        name, result = text.split("=", 1)[0].strip(), ""
        if "::" in name:
            namespace, name = name.rsplit("::", 1)
            text = text.replace(namespace + "::", "", 1)
    return Symbol(kind, name, text, owner, namespace, result, source_declaration=original, **kwargs)
