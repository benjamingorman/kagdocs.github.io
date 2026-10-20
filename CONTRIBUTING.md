# Contributing

See [README.md](README.md) for Docker setup, local preview, Markdown metadata,
scaffolding, tests, and manual GitHub Pages publication.

Use the vanilla `Manual/interface` as the source of API declarations and vanilla
`Base` for examples. Do not add declarations inferred from other engines or
inspect compiled game binaries. Missing Manual information should remain explicit.

Write prose in `docs/api/objects/<Object>/<method>.md` or the corresponding
namespace/global directory. A file documents the complete named overload family;
`make scaffold SYMBOL=CBlob::getHealth` creates the correct metadata without
overwriting existing work. Object introductions use `_index.md`. Only Maths has
authored API descriptions in the initial rewrite.

Use fenced code blocks (`cpp` for AngelScript), ordinary Markdown links, and
blockquotes for callouts. Guides use `title` and `order` frontmatter and appear in
the Guides category. Keep claims grounded in the Manual and scripts; document
uncertainty rather than inventing implementation details.

After changing the generator or frontend, run `make test`, `make build`, and
`make check-docs`. Check the local preview for search, overload navigation, themes,
source links, and mobile layout. Generated output and game inputs stay out of Git.
The `old/` archive is retained for historical reference and is not built.

Example matching uses the Tree-sitter layer in `tools/api_docs/src/kagdocs/syntax.py`
and the resolver in `tools/api_docs/src/kagdocs/examples.py`. Add fixtures to `tools/api_docs/tests/test_examples.py`
when inference changes. Leave unknown receivers and ambiguous overloads unmatched.
Do not infer types from variable names or add a second tokenizer. After a full Base
build, read `build/docs/example-diagnostics.json`. Parser versions and grammar patches
are in the vendored parser README.
