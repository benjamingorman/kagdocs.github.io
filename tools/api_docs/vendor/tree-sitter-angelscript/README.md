# AngelScript parser provenance

Upstream: [Relrin/tree-sitter-angelscript](https://github.com/Relrin/tree-sitter-angelscript),
revision `4595504ef9ae3fc7d597a14fd09d9aebc5eaf8e6`, under the included BSD-3-Clause
license. `provenance.json` records SHA-256 hashes of the unmodified upstream files;
the test suite verifies them. `binding.c` and `setup.py` are this project's small
Python adapter, not upstream files.

Docker copies this directory into an isolated build stage. `patch_grammar.py`
applies checked substitutions to that copy, then Tree-sitter CLI **0.25.10**
regenerates the C parser. The final image installs its wheel and Python
**tree-sitter 0.25.2**. Compilers and the CLI stay in the build stage. The runtime
pin follows a full-Base scan: 0.26.0 exhibited a native crash during that scan;
0.25.2 completed it. Recheck the full corpus when changing the runtime or grammar.

The compatibility patches add:

- AngelScript's `not` unary operator.
- Empty class-body declarations, including semicolons after method bodies.
- Typed template/array constructions (`array<T>()`, `T[]()`, `T[][]()`), preserving
  primitive constructor calls (`float(value)`).
- Batch-oriented template scanning: require actual closing delimiters, allow
  multiline type arguments, and reject numeric tokens as type names. Upstream's
  optimistic end-of-line completion is useful in an editor but misparses valid
  multiline comparisons in KAG scripts.

No generated C is patched by hand. Substitutions fail if their expected upstream
text changes. To update the dependency, replace the upstream files and provenance
hashes, review each patch, run `make test`, and rebuild against the full installed
Base. Inspect `example-diagnostics.json` and compare example coverage before
accepting the change. Do not modify game inputs to conceal parse errors.
