"""Sphinx configuration for service-trocr-preprocess documentation."""

import sys
from pathlib import Path

# Add src/ to path so autodoc can find the package
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from app import __version__

project = "service-trocr-preprocess"
copyright = "2026, Jonas Widmer, Dana Rebecca Meyer"
author = "Jonas Widmer, Dana Rebecca Meyer"
release = __version__

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.napoleon",
    "sphinx.ext.intersphinx",
    "sphinx.ext.viewcode",
    "myst_parser",
]

autosummary_generate = True

exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

autodoc_member_order = "bysource"
autodoc_typehints = "description"

# This project's docstrings are Google-style (Args/Returns/Raises).
napoleon_google_docstring = True
napoleon_numpy_docstring = False

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
}

html_theme = "sphinx_rtd_theme"
html_show_sphinx = False

source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}

# ── FastAPI reference ──────────────────────────────────────────────────
# docs/_extra/api-reference.html is a hand-written static Redoc page; docs/
# generate_openapi.py writes the matching openapi.json into the same folder.
# Both get copied verbatim into the built site's root.
html_extra_path = ["_extra"]
