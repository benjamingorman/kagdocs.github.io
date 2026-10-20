"""Command line for generating, checking, and testing the reference."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path, PurePosixPath, PureWindowsPath

from kagdocs.paths import project_dir


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="kagdocs")
    commands = parser.add_subparsers(dest="command", required=True)

    build = commands.add_parser("build", help="generate the static site")
    build.add_argument("--kag-dir", type=Path, required=True)
    build.add_argument("--output", type=Path, required=True)
    build.add_argument("--host-root", help="host path of the checkout, when output is a host path")
    build.add_argument("--context-lines", type=int, default=5)
    build.add_argument("--skip-css", action="store_true")

    check = commands.add_parser("check", help="validate an existing site")
    check.add_argument("--output", type=Path, required=True)
    check.add_argument("--host-root")

    scaffold = commands.add_parser("scaffold", help="create empty Markdown templates")
    scaffold.add_argument("--kag-dir", type=Path, required=True)
    scaffold.add_argument("--symbol", default="*")

    commands.add_parser("test", help="run the Python and frontend tests")

    args = parser.parse_args(argv)
    if args.command == "test":
        raise SystemExit(run_tests())
    if args.command == "scaffold":
        scaffold_docs(args.kag_dir, args.symbol)
        return
    output = located_output(args.output, args.host_root)
    if args.command == "check":
        check_site(output)
        return
    build_site(args.kag_dir, output, args.context_lines, args.skip_css)


def located_output(output: Path, host_root: str | None) -> Path:
    """Map a host ``DOCS_DIR`` onto the container's ``/workspace`` mount.

    The directory must sit below the checkout's ``build/`` directory. The
    output directory itself may be a bind mount, so callers must not delete it.
    """
    if not host_root:
        return output
    kind = PureWindowsPath if PureWindowsPath(host_root).drive else PurePosixPath
    root = kind(host_root)
    target = kind(output)
    if not target.is_absolute():
        target = root / target
    try:
        relative = target.relative_to(root)
    except ValueError:
        raise SystemExit("DOCS_DIR must be below the repository build/ directory") from None
    resolved = Path("/workspace").joinpath(*relative.parts).resolve()
    build = Path("/workspace").resolve() / "build"
    if resolved == build or not resolved.is_relative_to(build):
        raise SystemExit("DOCS_DIR must be an absolute path below the repository build/ directory")
    return resolved


def build_site(kag_dir: Path, output: Path, context_lines: int, skip_css: bool) -> None:
    import json

    # Kept local so `kagdocs test` and `--help` do not import the parser.
    from kagdocs.inputs import read_installation
    from kagdocs.render import render

    data = read_installation(kag_dir)
    output.parent.mkdir(parents=True, exist_ok=True)
    # Validate on the container filesystem. Checking thousands of links through
    # a Windows bind mount is slow; only the finished site is copied across.
    with tempfile.TemporaryDirectory(prefix="kagdocs-") as stage:
        staged = Path(stage)
        report = render(data, staged, context_lines)
        if not skip_css:
            npm = shutil.which("npm.cmd") or shutil.which("npm")
            if not npm:
                raise SystemExit(
                    "Node.js/npm is required (use make build for the Docker toolchain)"
                )
            subprocess.run(
                [npm, "run", "css", "--", "-o", str((staged / "api.css").resolve())],
                cwd=project_dir(),
                check=True,
            )
            from kagdocs.check import check

            print(json.dumps(check(staged), indent=2))
        _replace_output(output, staged)
    print(json.dumps(report, indent=2))
    print(f"Wrote {output.resolve() / 'index.html'}")


def scaffold_docs(kag_dir: Path, symbol: str) -> None:
    from kagdocs.catalogue import load_vanilla
    from kagdocs.content import scaffold
    from kagdocs.inputs import read_installation
    from kagdocs.paths import repository_root

    data = read_installation(kag_dir)
    for path in scaffold(repository_root() / "docs", load_vanilla(data["files"]), symbol):
        print(path)


def check_site(output: Path) -> None:
    import json

    from kagdocs.check import check

    # Copy first so link checks do not walk a Windows bind mount.
    with tempfile.TemporaryDirectory(prefix="kagdocs-check-") as temp:
        shutil.copytree(output, temp, dirs_exist_ok=True)
        print(json.dumps(check(Path(temp)), indent=2))


def python_tests() -> None:
    """Run the Python unittest suite."""
    raise SystemExit(_python_tests())


def _python_tests() -> int:
    suite = unittest.defaultTestLoader.discover(str(project_dir() / "tests"), pattern="test_*.py")
    return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1


def run_tests() -> int:
    python_ok = _python_tests() == 0
    frontend = subprocess.run(
        ["node", "--test", "js-test/test_search.cjs", "js-test/test_site.cjs"],
        cwd=project_dir(),
        check=False,
    )
    return 0 if python_ok and frontend.returncode == 0 else 1


def _replace_output(output: Path, staged: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    for child in output.iterdir():
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child)
        else:
            child.unlink()
    shutil.copytree(staged, output, dirs_exist_ok=True)


if __name__ == "__main__":
    main()
