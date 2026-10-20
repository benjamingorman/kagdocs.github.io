# kagdocs

Generator and frontend for the KAG API reference. Python is a uv project. CSS and the JavaScript tests use Node.

## Tests

Python:

```sh
uv sync
uv run kagdocs-test
```

JavaScript, from this directory:

```sh
node --test js-test/test_search.cjs js-test/test_site.cjs
```

Both:

```sh
uv run kagdocs test
```

The AngelScript parser is built inside the Docker image and is not a lockfile dependency, so the Python tests need that image. From the repository root, `make test` runs both suites there.

## Other commands

```sh
uv run ruff check
uv run ruff format
npm run css
uv run kagdocs build --kag-dir <kag> --output <dir>
```

`make` from the repository root builds the site and serves it.
