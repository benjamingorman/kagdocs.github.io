"""Apply narrow KAG syntax compatibility changes to a build-stage grammar copy.

The vendored upstream files remain byte-for-byte intact. Exact substitutions
fail closed when the pinned grammar changes; the resulting C parser is generated
with a pinned CLI, not patched by hand.
"""

import sys
from pathlib import Path


def patch(text: str, before: str, after: str) -> str:
    if text.count(before) != 1:
        raise ValueError(f"Pinned grammar patch no longer applies: {before!r}")
    return text.replace(before, after)


def patch_grammar(text: str) -> str:
    text = patch(
        text,
        'choice("-", "+", "!", "~", "@", "++", "--")',
        'choice("-", "+", "!", "not", "~", "@", "++", "--")',
    )
    text = patch(
        text,
        '$.funcdef_declaration,\n      )),\n      "}",\n    ),',
        '$.funcdef_declaration,\n        ";",\n      )),\n      "}",\n    ),',
    )
    text = patch(
        text,
        "      $.cast_expression,\n",
        "      $.cast_expression,\n      $.type_constructor_expression,\n      $.primitive_type,\n",
    )
    text = patch(
        text,
        "    // --- Cast expression ---",
        """    // KAG uses array<T>(), T[](), and nested T[][]() constructions.
    type_constructor_expression: $ => prec(17, seq(
      field("type", $.constructor_type),
      field("arguments", $.argument_list),
    )),
    constructor_type: $ => seq(
      optional($.scope), $.datatype,
      choice(
        seq($.template_type_list, repeat(seq("[", "]"))),
        repeat1(seq("[", "]")),
      ),
      optional("@"),
    ),

    // --- Cast expression ---""",
    )
    text = patch(text, "    [$.scope],", "    [$.scope],\n    [$.type, $.constructor_type],")
    return text


def patch_scanner(text: str) -> str:
    # The upstream scanner optimistically completes templates at end-of-line
    # for editor use. Batch analysis must require real balanced delimiters and
    # must allow comparisons and type arguments to span multiple lines.
    text = patch(
        text,
        "// Incomplete code at end of file - optimistically a template\n            return true;",
        "// Batch input: incomplete templates are errors.\n            return false;",
    )
    start = text.index("        if (is_eol(c)) {")
    end = text.index("        if (c == '<')", start)
    text = patch(
        text,
        text[start:end],
        """        if (is_eol(c)) {
            lexer->advance(lexer, false);
            continue;
        }

""",
    )
    text = patch(text, "if (is_alnum(c) || c == '_')", "if (is_alpha(c))")
    start = text.index("    // Implicit (zero-width) template close")
    end = text.index("    skip_ws(lexer);", start)
    return patch(text, text[start:end], "")


def main() -> None:
    """Patch ``grammar.js``, then ``src/scanner.c`` beside it. The argument is the grammar path."""
    path = Path(sys.argv[1])
    path.write_text(patch_grammar(path.read_text()))
    scanner = path.parent / "src/scanner.c"
    scanner.write_text(patch_scanner(scanner.read_text()))


if __name__ == "__main__":
    main()
