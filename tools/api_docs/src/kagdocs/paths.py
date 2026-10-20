"""Checkout locations used by the generator and the container tasks.

An editable install keeps this file inside ``tools/api_docs/src``. Walking
parents is more reliable than counting them, including when the image working
directory is ``/app``.
"""

from pathlib import Path


def project_dir() -> Path:
    """Directory that holds ``pyproject.toml`` and the static site assets."""
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "pyproject.toml").is_file() and (candidate / "js" / "site.js").is_file():
            return candidate
    raise RuntimeError("kagdocs project directory not found")


def repository_root() -> Path:
    """Repository root, which contains authored ``docs/`` and the Makefile."""
    root = project_dir().parents[1]
    if not (root / "docs").is_dir():
        raise RuntimeError(f"Authored docs not found beside {project_dir()}")
    return root
