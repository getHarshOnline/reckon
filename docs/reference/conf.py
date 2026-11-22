"""Build reference from the selected checkout and its required native extension."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import reckon  # noqa: E402  # pylint: disable=wrong-import-position

project = "Reckon Python API"
release = reckon.__version__
extensions = ["sphinx.ext.autodoc", "sphinx.ext.napoleon"]
root_doc = "index"
autodoc_member_order = "bysource"
autodoc_typehints = "description"
napoleon_google_docstring = True
napoleon_numpy_docstring = False
napoleon_use_ivar = True
html_theme = "alabaster"
html_show_sourcelink = False
html_copy_source = False
exclude_patterns = []
