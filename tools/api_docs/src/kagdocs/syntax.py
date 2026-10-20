"""Lossless AngelScript syntax and source coordinates from the pinned grammar.

This module knows syntax, not KAG API names or example-selection policy.
Tree-sitter byte offsets are converted at the boundary to Python character columns.
"""

from dataclasses import dataclass
from functools import lru_cache

import kag_angelscript
from tree_sitter import Language, Node, Parser, Tree


@lru_cache(maxsize=1)
def language() -> Language:
    return Language(kag_angelscript.language())


def walk(node: Node):
    """Iterative preorder, including anonymous missing tokens for diagnostics."""
    pending = [node]
    while pending:
        current = pending.pop()
        yield current
        pending.extend(reversed(current.children))


@dataclass(frozen=True)
class ParsedSource:
    data: bytes
    tree: Tree

    @classmethod
    def parse(cls, text: str) -> "ParsedSource":
        data = text.encode("utf-8")
        return cls(data, Parser(language()).parse(data))

    def text(self, node: Node) -> str:
        return self.data[node.start_byte : node.end_byte].decode("utf-8")

    def column(self, node: Node) -> int:
        beginning = self.data.rfind(b"\n", 0, node.start_byte) + 1
        return len(self.data[beginning : node.start_byte].decode("utf-8"))

    def errors(self) -> list[dict]:
        return [
            {
                "kind": "missing" if node.is_missing else "error",
                "line": node.start_point.row + 1,
                "column": self.column(node),
                "text": self.text(node)[:120],
            }
            for node in walk(self.tree.root_node)
            if node.is_error or node.is_missing
        ]

    @staticmethod
    def safe(node: Node) -> bool:
        """Reject damaged lexical scopes, even when a candidate itself looks valid."""
        current = node
        while current and current.type != "script":
            if current.is_error or current.is_missing:
                return False
            if current.has_error and current.type in {
                "statement_block",
                "func_declaration",
                "class_declaration",
                "mixin_declaration",
                "namespace_declaration",
                "lambda_expression",
            }:
                return False
            current = current.parent
        return node.type == "script" or not node.has_error

    def tokens(self) -> list[list]:
        """Adapt syntax leaves to the renderer's highlighting classes.

        Classes are 0 punctuation, 1 keyword, 2 literal, 3 identifier,
        4 comment, and 5 whitespace. Gaps the grammar does not name are kept
        so the token stream can be joined back into the original source.
        """
        result, offset, pending = [], 0, [self.tree.root_node]
        atoms = {
            "comment": 4,
            "string_literal": 2,
            "number_literal": 2,
            "boolean_literal": 1,
            "null_literal": 1,
        }
        while pending:
            node = pending.pop()
            if node.children and node.type not in atoms:
                pending.extend(reversed(node.children))
                continue
            if node.is_missing or node.end_byte <= offset:
                continue
            if node.start_byte > offset:
                gap = self.data[offset : node.start_byte].decode("utf-8")
                result.append([5 if gap.isspace() else 0, gap])
            text = self.text(node)
            kind = atoms.get(node.type)
            if kind is None:
                kind = 3 if node.type == "identifier" else (1 if text.isidentifier() else 0)
            result.append([kind, text])
            offset = node.end_byte
        if offset < len(self.data):
            tail = self.data[offset:].decode("utf-8")
            result.append([5 if tail.isspace() else 0, tail])
        return result
