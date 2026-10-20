# King Arthur's Gold API Docs

This repository contains documentation for the AngelScript API in the KAG
engine.
It provides a useful reference for modders who wish to conveniently browse
through all the available functions and methods offered by the engine.

## Build

To build the docs locally in Docker, run:

```sh
$ make
```

Docs will be built in `build/docs` and served via <http://localhost:8080>.

You need to have KAG installed locally. The default install path is `C:/Program Files (x86)/Steam/steamapps/common/King Arthur's Gold` on Windows and `~/.local/share/Steam/steamapps/common/King Arthur's Gold` elsewhere.
Override this with `make KAG_DIR="D:/Steam Library/steamapps/common/King Arthur's Gold"` (forward slashes).
The directory must contain `Manual/interface` and `Base`, and it is mounted read-only.

`docs.local.mk` is gitignored and can be used to configure `KAG_DIR`, `DOCS_PORT`, and `DOCS_CONTEXT`


| Command | What it does |
| --- | --- |
| `make build` | Generate and check docs
| `make host-docs` | Serve built docs |
| `make stop-docs` | Remove local server container |
| `make test` | Python and frontend tests |
| `make check-docs` | Recheck links and assets in `build/docs` |
| `make scaffold SYMBOL=CBlob::getHealth` | Add one empty Markdown template |
| `make scaffold` | Add templates for every Manual symbol that lacks one |


## Writing pages

API prose lives in `docs/api/objects/<Object>/<method>.md`.
Namespaces use `docs/api/namespaces/<Namespace>/`, globals use `docs/api/globals/`, and an object introduction is `_index.md`.
One file covers a whole overload family. Frontmatter needs `kind`, `symbol`, and `signatures` copied exactly from the Manual. `make scaffold` can be used to conveniently write that metadata.

## Code Examples

Code examples from Base are automatically included in the docs.

This works by using Tree-sitter to parse the AngelScript in Base.
A separate resolver matches calls only when the receiver and overload are unambiguous.
Up to three files are shown per signature.

## Publishing

Nothing publishes on push. Build locally, then copy `build/docs` into a separate checkout of the `gh-pages` branch and push that branch.

The workflow in `.github/workflows/pages.yml` has to be on the default branch before it can be run by hand.
In Settings -> Pages, set the source to GitHub Actions, then run "Publish documentation".
The runner deploys the `gh-pages` branch as-is. It does not need a KAG install.

## Credits

* [Kangawa Theme](https://github.com/rebelot/kanagawa.nvim)
* [Lucide](https://lucide.dev/icons/)
* [CaskaydiaMono Font](https://www.nerdfonts.com/font-downloads)

Licenses are in `tools/api_docs/` and are copied into the built site.
