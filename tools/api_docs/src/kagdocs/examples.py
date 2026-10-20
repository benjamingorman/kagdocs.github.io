"""Conservative API usage discovery over AngelScript concrete syntax trees.

Syntax comes from Tree-sitter; this module supplies only catalogue lookup, lexical
bindings, and a deliberately limited expression type resolver. Unknown types stay
unknown. No script is executed and no variable name is used to guess a type.
Arithmetic, string concatenation, and operator methods declared in the Manual are
typed only when both sides are already known.
"""

from __future__ import annotations

import re
from bisect import bisect_right
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from tree_sitter import Node

from kagdocs.model import Symbol, compact, parameter, split_params
from kagdocs.syntax import ParsedSource, walk

NUMERIC = {"int", "uint", "int8", "uint8", "int16", "uint16", "int64", "uint64", "float", "double"}
INTEGERS = NUMERIC - {"float", "double"}
FLOATS = {"float", "double"}
ARITHMETIC = {"+", "-", "*", "/", "%"}
BITWISE = {"|", "&", "^", "<<", ">>", ">>>"}
COMPARISON = {"==", "!=", "is", "!is", "<", ">", "<=", ">="}
LOGICAL = {"&&", "||", "and", "or", "^^", "xor"}
OPERATORS = {
    "opNeg": "-",
    "opCom": "~",
    "opAdd": "+",
    "opSub": "-",
    "opMul": "*",
    "opDiv": "/",
    "opMod": "%",
    "opAnd": "&",
    "opOr": "|",
    "opXor": "^",
    "opShl": "<<",
    "opShr": ">>",
    "opUShr": ">>>",
    "opAdd_r": "+",
    "opSub_r": "-",
    "opMul_r": "*",
}
KNOWN_TYPES = NUMERIC | {"bool", "string", "?", "any", "array", "dictionary", "void"}


def base_type(text: str) -> str:
    text = re.sub(r"\b(?:const|inout|out|in)\b", "", text)
    text = compact(text)
    text = re.sub(r"&(?:inout|out|in)?|@", "", text)
    text = re.sub(r"(^|[<,])const", r"\1", text)
    if text.startswith("array<") and text.endswith(">"):
        return base_type(text[6:-1]) + "[]"
    return compact(text)


def symbol_type(symbol: Symbol) -> str:
    if symbol.kind == "constructor":
        return symbol.owner
    if symbol.kind == "property":
        return base_type(symbol.declaration.rsplit(symbol.name, 1)[0])
    return base_type(symbol.return_type)


def literal_number_type(text: str) -> str:
    """Hex, binary, and octal spellings are ints. A point or exponent makes a float."""
    lowered = text.lower()
    if lowered.startswith(("0x", "0b", "0o", "0d")):
        return "int"
    if any(character in lowered for character in ".efd"):
        return "float" if lowered.endswith("f") else "double"
    return "int"


def indexed_element(owner: str | None) -> str | None:
    """Element type of ``T[]`` or ``array<T>``. Other index targets stay unknown."""
    if owner and owner.endswith("[]"):
        return owner[:-2]
    if owner and owner.startswith("array<") and owner.endswith(">"):
        return owner[6:-1]
    return None


def consensus(types) -> str | None:
    types = set(types)
    return types.pop() if len(types) == 1 and None not in types and "" not in types else None


class Catalogue:
    """Index declarations once; keep overload policy independent of syntax walking."""

    def __init__(self, symbols: list[Symbol]):
        self.families = defaultdict(list)
        self.classes = {s.qualified for s in symbols if s.kind == "class"}
        self.enum_types, aliases = set(), defaultdict(set)
        property_names = {s.name for s in symbols if s.kind == "property"}
        property_qualified = {s.qualified for s in symbols if s.kind == "property"}
        for symbol in symbols:
            self.families[(symbol.kind, symbol.namespace, symbol.owner, symbol.name)].append(symbol)
            if symbol.kind != "enum-value":
                continue
            enum_type = "::".join(x for x in (symbol.namespace, symbol.owner) if x)
            self.enum_types.add(enum_type)
            candidates = {symbol.qualified, symbol.name}
            if symbol.namespace:
                candidates.add(f"{symbol.namespace}::{symbol.name}")
            for alias in candidates:
                if alias in property_qualified or ("::" not in alias and alias in property_names):
                    continue
                aliases[alias].add(enum_type)
        # Scripts spell class enums as Owner::value. Keep an alias only when it
        # names a single enum, and never when it is also a property.
        self.enums = {alias: types.pop() for alias, types in aliases.items() if len(types) == 1}
        shorts = defaultdict(set)
        for enum_type in self.enum_types:
            shorts[enum_type.rsplit("::", 1)[-1]].add(enum_type)
        # Object files name an enum by its unique final component (`Style`, `ScriptLayer`).
        self.enum_short = {name: types.pop() for name, types in shorts.items() if len(types) == 1}
        self.operators, self.reversed_operators = defaultdict(list), defaultdict(list)
        for symbol in symbols:
            opcode = OPERATORS.get(symbol.name)
            if symbol.kind != "method" or not opcode or "(" not in symbol.declaration:
                continue
            params = split_params(symbol.declaration.split("(", 1)[1].rsplit(")", 1)[0])
            entry = (
                base_type(parameter(params[0], False)) if params else "",
                symbol_type(symbol),
                symbol,
            )
            if symbol.name.endswith("_r"):
                self.reversed_operators[(symbol.owner, opcode)].append(entry)
            else:
                self.operators[(symbol.owner, opcode)].append(entry)

    def get(self, kind: str, name: str, owner: str = "", namespace: str = "") -> list[Symbol]:
        if "::" in owner:
            namespace, owner = owner.rsplit("::", 1)
        return self.families.get((kind, namespace, owner, name), [])

    def known_type(self, text: str) -> bool:
        if text.endswith("[]"):
            return self.known_type(text[:-2])
        return (
            text in KNOWN_TYPES
            or text in self.classes
            or text in self.enum_types
            or text in self.enum_short
        )

    def same_type(self, actual: str | None, expected: str) -> bool:
        if actual == expected:
            return True
        if not actual:
            return False
        folded = {self.enum_short.get(actual, actual), self.enum_short.get(expected, expected)}
        return len(folded) == 1 and (
            actual in self.enum_types
            or actual in self.enum_short
            or expected in self.enum_types
            or expected in self.enum_short
        )

    def conversion(self, actual: str | None, param: str) -> int | None:
        """Rank one argument. None means the candidate cannot accept it."""
        expected = base_type(parameter(param, False))
        if self.same_type(actual, expected):
            return 3
        if expected == "?":
            return 0  # Explicitly generic reference; a real conversion outranks it.
        if actual == "null":
            return 0 if "@" in param else None
        if actual in self.enum_types and expected in INTEGERS:
            return 1  # AngelScript enums convert to integers, less specifically than an exact type.
        if actual in NUMERIC and expected in NUMERIC:
            if actual in INTEGERS and expected in INTEGERS:
                return 2
            if actual in FLOATS and expected in FLOATS:
                return 2
            return 1
        if actual:
            return None
        return 0

    def overloads(self, candidates: list[Symbol], arguments: list[str | None]) -> list[Symbol]:
        ranked = []
        for symbol in candidates:
            params = split_params(symbol.declaration.split("(", 1)[1].rsplit(")", 1)[0])
            if not sum("=" not in p for p in params) <= len(arguments) <= len(params):
                continue
            score, compatible = 0, True
            # Defaults and extra arguments make these sequences different lengths.
            for actual, param in zip(arguments, params, strict=False):
                rank = self.conversion(actual, param)
                if rank is None:
                    compatible = False
                    break
                score += rank
            if compatible:
                ranked.append((score, symbol))
        if not ranked:
            return []
        best = max(score for score, _ in ranked)
        result = [symbol for score, symbol in ranked if score == best]
        # Const/default variants can describe the same call. Distinct parameter
        # signatures cannot share an example when inference leaves a tie.
        return result if len({s.key(False)[-1][1] for s in result}) == 1 else []

    def operator(
        self, owner: str | None, opcode: str, argument: str | None, reversed_operand: bool = False
    ):
        """Resolve a Manual operator method. Primitive arithmetic is not represented here."""
        table = self.reversed_operators if reversed_operand else self.operators
        matches = []
        for expected, result, symbol in table.get((owner, opcode), []):
            if not expected:
                if argument is None:
                    matches.append((3, result, symbol))
                continue
            if argument is None:
                continue
            rank = 3 if argument == expected else None
            if rank is None and argument in NUMERIC and expected in NUMERIC:
                rank = 2 if (argument in INTEGERS) == (expected in INTEGERS) else 1
            if rank is not None:
                matches.append((rank, result, symbol))
        if not matches:
            return None, None
        best = max(rank for rank, _, _ in matches)
        chosen = [item for item in matches if item[0] == best]
        results = {result for _, result, _ in chosen}
        symbols = {symbol.key(False)[-1]: symbol for _, _, symbol in chosen}
        if len(results) != 1 or len(symbols) != 1:
            return None, None
        return results.pop(), next(iter(symbols.values()))


@dataclass
class Binding:
    type: str | None
    condition: tuple[int, ...] = ()


@dataclass
class Scope:
    parent: Scope | None = None
    namespace: str = ""
    bindings: dict[str, Binding] = field(default_factory=dict)

    def lookup(self, name: str, condition: tuple[int, ...] = ()) -> tuple[bool, str | None]:
        if name in self.bindings:
            binding = self.bindings[name]
            compatible = condition[: len(binding.condition)] == binding.condition
            return True, binding.type if compatible else None
        return self.parent.lookup(name, condition) if self.parent else (False, None)


@dataclass(frozen=True)
class Example:
    path: str
    first: int
    last: int
    call_first: int
    call_last: int
    column: int
    token: str


class SourceAnalysis:
    """One file's lexical state. Bindings never escape their block or function."""

    def __init__(self, source: ParsedSource, catalogue: Catalogue, emit, skipped):
        self.source, self.catalogue = source, catalogue
        self.emit, self.skipped = emit, skipped
        # Do not evaluate build conditions. A binding established in one branch
        # can be used there, but must not supply a type to another branch or to
        # code after #endif. Directives themselves come from the syntax tree.
        self.condition_starts, self.conditions = [0], [()]
        stack, branch = [], 0
        for node in walk(source.tree.root_node):
            if node.type != "preproc_directive":
                continue
            words = source.text(node)[1:].strip().split(maxsplit=1)
            directive = words[0] if words else ""
            if directive in {"if", "ifdef", "ifndef", "elif", "else"}:
                if directive in {"elif", "else"} and stack:
                    stack.pop()
                branch += 1
                stack.append(branch)
            elif directive == "endif" and stack:
                stack.pop()
            self.condition_starts.append(node.end_byte)
            self.conditions.append(tuple(stack))
        self.script_types = {
            source.text(n.child_by_field_name("name"))
            for n in walk(source.tree.root_node)
            if n.type in {"class_declaration", "interface_declaration", "enum_declaration"}
            and n.child_by_field_name("name")
        }
        # File-local declarations shadow native functions regardless of order.
        self.functions = defaultdict(list)
        for node in walk(source.tree.root_node):
            if node.type in {"func_declaration", "import_declaration"}:
                name = node.child_by_field_name("name")
                if name and not self.in_class(node):
                    self.functions[(self.namespace(node), source.text(name))].append(node)

    @staticmethod
    def in_class(node: Node) -> bool:
        parent = node.parent
        while parent:
            if parent.type in {"class_declaration", "mixin_declaration", "interface_declaration"}:
                return True
            parent = parent.parent
        return False

    def namespace(self, node: Node) -> str:
        names = []
        parent = node.parent
        while parent:
            if parent.type == "namespace_declaration":
                names.insert(0, self.source.text(parent.child_by_field_name("name")))
            parent = parent.parent
        return "::".join(names)

    def text(self, node: Node | None) -> str:
        return self.source.text(node) if node else ""

    def condition(self, node: Node) -> tuple[int, ...]:
        return self.conditions[bisect_right(self.condition_starts, node.start_byte) - 1]

    def declared_type(self, node: Node | None) -> str | None:
        typ = base_type(self.text(node))
        # A script class with an API type's spelling is a different type.
        return (
            None if not typ or typ == "auto" or typ.split("<", 1)[0] in self.script_types else typ
        )

    def arguments(self, node: Node, scope: Scope, depth: int) -> list[str | None] | None:
        if node.child_by_field_name("arg_name"):
            return None  # Positional arity/type matching is unsafe for named arguments.
        return [
            self.expression(n, scope, depth + 1)
            for n in node.named_children
            if n.type not in {"comment", "preproc_directive"}
        ]

    def property(self, node: Node, scope: Scope, depth: int) -> list[Symbol]:
        owner = self.expression(node.child_by_field_name("object"), scope, depth + 1)
        return (
            self.catalogue.get("property", self.text(node.child_by_field_name("member")), owner)
            if owner
            else []
        )

    def qualified(self, node: Node, scope: Scope) -> tuple[str, str]:
        text = self.text(node).lstrip(":")
        return tuple(text.rsplit("::", 1)) if "::" in text else (scope.namespace, text)

    def call(
        self, node: Node, scope: Scope, depth: int = 0, record_miss: bool = True
    ) -> list[Symbol]:
        function, args = node.child_by_field_name("function"), node.child_by_field_name("arguments")
        if not function or not args or depth > 24:
            return []
        types = self.arguments(args, scope, depth)
        if types is None:
            return []
        if function.type == "member_expression":
            owner = self.expression(function.child_by_field_name("object"), scope, depth + 1)
            candidates = (
                self.catalogue.get(
                    "method", self.text(function.child_by_field_name("member")), owner
                )
                if owner
                else []
            )
        elif function.type in {"identifier", "qualified_identifier", "primitive_type"}:
            namespace, name = self.qualified(function, scope)
            bound, _ = (
                scope.lookup(name, self.condition(node))
                if function.type != "qualified_identifier"
                else (False, None)
            )
            if bound or (namespace, name) in self.functions or name in self.script_types:
                return []
            if name in self.catalogue.classes:
                candidates = self.catalogue.get("constructor", name, name)
            else:
                candidates = self.catalogue.get("function", name, namespace=namespace)
        else:
            return []
        matches = self.catalogue.overloads(candidates, types)
        # Nested type queries must not count the same call again when visit() records it.
        if record_miss and candidates and not matches:
            self.skipped["unresolved_overload"] += 1
        return matches

    def binding_type(self, declared: Node, initializer: Node | None, scope: Scope) -> str | None:
        inferred = self.declared_type(declared)
        if base_type(self.text(declared)) == "auto":
            return self.expression(initializer, scope) if initializer else None
        # The Manual omits typedef alias names. An unrecognized local type can
        # still take a type from its initializer; a script class never does.
        if inferred and not self.catalogue.known_type(inferred) and initializer:
            return self.expression(initializer, scope) or inferred
        return inferred

    def binary(self, node: Node, operator: str, left: str | None, right: str | None) -> str | None:
        token = node.child_by_field_name("operator")
        if left in NUMERIC and right in NUMERIC and operator in ARITHMETIC | BITWISE:
            if operator in BITWISE or operator == "%":
                if left in INTEGERS and right in INTEGERS:
                    return left if left == right else "int"
                return None
            if left in FLOATS or right in FLOATS:
                return "double" if "double" in (left, right) else "float"
            return left if left == right else "int"
        result, symbol = self.catalogue.operator(left, operator, right)
        if symbol is None and not self.catalogue.operators.get((left, operator)):
            result, symbol = self.catalogue.operator(right, operator, left, reversed_operand=True)
        if symbol is not None and token is not None:
            self.emit(symbol, token, node)
            return result
        if operator == "+" and left and right and "string" in (left, right):
            return "string"
        if operator in COMPARISON | LOGICAL and left and right:
            return "bool"
        return None

    def expression(self, node: Node | None, scope: Scope, depth: int = 0) -> str | None:
        """Type of one expression. ``None`` means unknown, which must not be guessed.

        The depth cap stops a pathological nest from recursing without bound.
        """
        if not node or depth > 24:
            return None
        typ, text = node.type, self.text(node)
        if typ in {"identifier", "qualified_identifier"}:
            if typ == "identifier":
                bound, result = scope.lookup(text, self.condition(node))
                if bound:
                    return result
            if text in self.catalogue.enums:
                return self.catalogue.enums[text]
            namespace, name = self.qualified(node, scope)
            return consensus(
                symbol_type(s) for s in self.catalogue.get("property", name, namespace=namespace)
            )
        if typ == "member_expression":
            found = self.property(node, scope, depth)
            if found:
                return consensus(symbol_type(s) for s in found)
            obj, member = node.child_by_field_name("object"), node.child_by_field_name("member")
            if obj and member and obj.type == "identifier" and self.text(obj) == "this":
                bound, result = scope.lookup(self.text(member), self.condition(node))
                if bound:
                    return result
            return None
        if typ == "call_expression":
            function = node.child_by_field_name("function")
            if function and function.type in {"identifier", "primitive_type"}:
                name = self.text(function)
                bound, _ = scope.lookup(name, self.condition(node))
                if (
                    not bound
                    and name not in self.script_types
                    and (scope.namespace, name) not in self.functions
                ):
                    if name in self.catalogue.classes or base_type(name) in NUMERIC | {
                        "bool",
                        "string",
                    }:
                        return base_type(name)
            return consensus(
                symbol_type(s) for s in self.call(node, scope, depth + 1, record_miss=False)
            )
        if typ == "binary_expression":
            operator = self.text(node.child_by_field_name("operator"))
            left = self.expression(node.child_by_field_name("left"), scope, depth + 1)
            right = self.expression(node.child_by_field_name("right"), scope, depth + 1)
            return self.binary(node, operator, left, right)
        if typ in {"cast_expression", "type_constructor_expression"}:
            return self.declared_type(node.child_by_field_name("type"))
        if typ == "index_expression":
            owner = self.expression(node.child_by_field_name("object"), scope, depth + 1)
            return indexed_element(owner)
        if typ == "parenthesized_expression":
            children = [n for n in node.named_children if n.type != "comment"]
            return self.expression(children[0], scope, depth + 1) if len(children) == 1 else None
        if typ in {"unary_expression", "postfix_expression"}:
            operator_node = node.child_by_field_name("operator")
            operator = self.text(operator_node)
            if operator in {"!", "not"}:
                return "bool"
            operand = self.expression(node.child_by_field_name("operand"), scope, depth + 1)
            if typ == "unary_expression" and operator in {"-", "~"}:
                result, symbol = self.catalogue.operator(operand, operator, None)
                if symbol is not None and operator_node:
                    self.emit(symbol, operator_node, node)
                    return result
            return operand if operator == "@" or operand in NUMERIC else None
        if typ == "ternary_expression":
            return consensus(
                self.expression(node.child_by_field_name(f), scope, depth + 1)
                for f in ("consequence", "alternative")
            )
        if typ == "string_literal":
            return "string"
        if typ == "boolean_literal":
            return "bool"
        if typ == "null_literal":
            return "null"
        if typ == "number_literal":
            return literal_number_type(text)
        return None

    def visit(self, node: Node, scope: Scope):
        if not self.source.safe(node):
            self.skipped["damaged_scope"] += 1
            return
        typ = node.type
        if typ in {"comment", "string_literal", "preproc_directive"}:
            return
        if typ == "namespace_declaration":
            body = node.child_by_field_name("body")
            if body:
                self.visit(body, Scope(scope, self.namespace(body)))
            return
        if typ in {"class_declaration", "mixin_declaration", "interface_declaration"}:
            local = Scope(scope, scope.namespace, {"this": Binding(None)})
            body = node.child_by_field_name("body")
            if body:
                # Fields and methods are visible throughout the class. Unknown
                # members shadow global API names just as typed members do.
                for member in body.named_children:
                    if member.type == "func_declaration":
                        local.bindings[self.text(member.child_by_field_name("name"))] = Binding(
                            None
                        )
                    elif member.type == "variable_declaration":
                        declared = member.child_by_field_name("var_type")
                        for var in member.named_children:
                            name = var.child_by_field_name("name")
                            if not name:
                                continue
                            initializer = next(
                                (
                                    n
                                    for n in var.named_children
                                    if n != name and n.type != "comment"
                                ),
                                None,
                            )
                            local.bindings[self.text(name)] = Binding(
                                self.binding_type(declared, initializer, scope),
                                self.condition(member),
                            )
                self.visit(body, local)
            return
        if typ in {"func_declaration", "lambda_expression"}:
            local = Scope(scope, scope.namespace)
            params, body = node.child_by_field_name("parameters"), node.child_by_field_name("body")
            if params:
                for param in params.named_children:
                    name = param.child_by_field_name("name")
                    if name:
                        local.bindings[self.text(name)] = Binding(
                            self.declared_type(param.child_by_field_name("param_type"))
                        )
            if typ == "func_declaration" and params and not self.in_class(node):
                name = node.child_by_field_name("name")
                signature = tuple(
                    parameter(self.text(p), False)
                    for p in params.named_children
                    if p.type == "parameter"
                )
                for symbol in self.catalogue.get("hook", self.text(name)):
                    if not scope.namespace and symbol.key(False)[-1][1] == signature:
                        self.emit(symbol, name, params)
            if body:
                self.visit(body, local)
            return
        if typ in {"statement_block", "for_statement", "foreach_statement"}:
            scope = Scope(scope, scope.namespace)
        if typ == "foreach_variable":
            scope.bindings[self.text(node.child_by_field_name("name"))] = Binding(
                self.declared_type(node.child_by_field_name("type")), self.condition(node)
            )
            return
        if typ == "variable_declaration":
            declared = node.child_by_field_name("var_type")
            for var in node.named_children:
                if var.type != "variable_declarator":
                    continue
                name = var.child_by_field_name("name")
                initializer = next(
                    (n for n in var.named_children if n != name and n.type != "comment"), None
                )
                inferred = self.binding_type(declared, initializer, scope)
                # Unknown declarations must still shadow outer API receivers.
                scope.bindings[self.text(name)] = Binding(inferred, self.condition(var))
                if initializer and initializer.type == "argument_list" and inferred:
                    args = self.arguments(initializer, scope, 0)
                    candidates = self.catalogue.get("constructor", inferred, inferred)
                    if args is not None:
                        for symbol in self.catalogue.overloads(candidates, args):
                            token = next(
                                (n for n in walk(declared) if n.type == "identifier"), declared
                            )
                            self.emit(symbol, token, initializer)
                if initializer:
                    self.visit(initializer, scope)
            return
        if typ in {"binary_expression", "unary_expression"}:
            self.expression(node, scope)
        if typ == "call_expression":
            function = node.child_by_field_name("function")
            token = (
                function.child_by_field_name("member")
                if function.type == "member_expression"
                else function
            )
            if function.type == "qualified_identifier":
                token = function.child_by_field_name("name")
            for symbol in self.call(node, scope):
                self.emit(symbol, token, node)
        elif typ == "member_expression":
            # A method-name expression is not a property read.
            parent = node.parent
            if not (
                parent.type == "call_expression" and parent.child_by_field_name("function") == node
            ):
                for symbol in self.property(node, scope, 0):
                    self.emit(symbol, node.child_by_field_name("member"), node)
        elif typ in {"identifier", "qualified_identifier"}:
            parent = node.parent
            # Restrict globals to actual expression positions, never declaration
            # names, namespace components, member names, or function callees.
            if parent.type in {
                "binary_expression",
                "unary_expression",
                "assignment_expression",
                "argument_list",
                "return_statement",
                "parenthesized_expression",
                "ternary_expression",
                "variable_declarator",
                "index_expression",
            }:
                namespace, name = self.qualified(node, scope)
                bound, _ = (
                    scope.lookup(name, self.condition(node))
                    if typ == "identifier"
                    else (False, None)
                )
                if not bound:
                    token = (
                        node.child_by_field_name("name") if typ == "qualified_identifier" else node
                    )
                    for symbol in self.catalogue.get("property", name, namespace=namespace):
                        self.emit(symbol, token, node)
        for child in node.named_children:
            self.visit(child, scope)


class ExampleIndex:
    """Deterministic selection: first usage in each of at most three Base files."""

    def __init__(self, symbols: list[Symbol], files: list[dict], context_lines: int = 5):
        if context_lines < 0:
            raise ValueError("Example context must be non-negative")
        self.examples = defaultdict(list)
        self.diagnostics = {"files": 0, "parse_errors": [], "skipped": Counter()}
        catalogue = Catalogue(symbols)
        for file in sorted(files, key=lambda f: f["path"]):
            if not file["path"].startswith("Base/") or not file["path"].endswith(".as"):
                continue
            source = file.get("syntax") or ParsedSource.parse("".join(t[1] for t in file["tokens"]))
            self.diagnostics["files"] += 1
            errors = source.errors()
            if errors:
                self.diagnostics["parse_errors"].append({"path": file["path"], "errors": errors})
            lines = source.data.count(b"\n") + 1

            def emit(symbol, token, end, path=file["path"], parsed=source, line_count=lines):
                first, last = token.start_point.row + 1, end.end_point.row + 1
                examples = self.examples[symbol.key()]
                if len(examples) < 3 and all(item.path != path for item in examples):
                    examples.append(
                        Example(
                            path,
                            max(1, first - context_lines),
                            min(line_count, last + context_lines),
                            first,
                            last,
                            parsed.column(token),
                            parsed.text(token),
                        )
                    )

            analysis = SourceAnalysis(source, catalogue, emit, self.diagnostics["skipped"])
            analysis.visit(source.tree.root_node, Scope())
