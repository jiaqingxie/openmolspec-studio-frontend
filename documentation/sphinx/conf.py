"""Classic Read the Docs presentation for the two independently built locales."""
import os
from pathlib import PurePosixPath, Path
import posixpath
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))

project = "OpenMolSpec"
author = "OpenMolSpec contributors"
copyright = "2026, OpenMolSpec contributors"
release = "1.0"
extensions = ["myst_nb", "sphinx.ext.autodoc", "sphinx.ext.napoleon", "sphinx.ext.mathjax"]
mathjax_path = 'mathjax/tex-mml-chtml.js'
mathjax3_config = {'chtml': {'displayAlign': 'left'}}
autodoc_typehints = 'description'
source_suffix = {".md": "myst-nb", ".ipynb": "myst-nb"}
root_doc = "index"
exclude_patterns = [".ipynb_checkpoints/**"]
myst_enable_extensions = ["colon_fence", "dollarmath", "amsmath"]
myst_heading_anchors = 6
nb_execution_mode = "off"
nb_scroll_outputs = True
nb_ipywidgets_js = {}
html_theme = "sphinx_rtd_theme"
html_title = "OpenMolSpec v1.0"
html_logo = str(Path(__file__).resolve().parents[1] / 'assets/brand/openmolspec-dark.svg')
html_favicon = str(Path(__file__).resolve().parents[1] / 'assets/brand/mark.svg')
html_static_path = ["_static"]
html_css_files = ["openmolspec.css"]
html_js_files = [("openmolspec-viewer.js", {"defer": "defer"})]
templates_path = ["_templates"]
html_theme_options = {
    "navigation_depth": 3,
    "collapse_navigation": True,
    "sticky_navigation": True,
    "prev_next_buttons_location": "bottom",
    "version_selector": True,
    "language_selector": False,
}
locale = os.environ.get("OPENMOLSPEC_DOCS_LOCALE", "en")
html_baseurl = os.environ.get("READTHEDOCS_CANONICAL_URL", "https://openmolspec.readthedocs.io/en/latest/")
if locale == "zh":
    html_baseurl = html_baseurl.rstrip("/") + "/zh/"
html_context = {"locale": locale}


def page_context(app, pagename, templatename, context, doctree):
    if pagename == "index":
        # Keep the document title plain for breadcrumbs, search and navigation.
        context["body"] = context["body"].replace(
            "<h1>OpenMolSpec", '<h1><img src="assets/brand/mark.svg" class="oms-home-logo" alt=""> OpenMolSpec', 1)
    current = PurePosixPath("zh" if locale == "zh" else ".") / (pagename + ".html")
    translated = PurePosixPath("." if locale == "zh" else "zh") / (pagename + ".html")
    context["translation_url"] = posixpath.relpath(str(translated), str(current.parent))
    context["translation_label"] = "English" if locale == "zh" else "简体中文"
    if pagename.startswith("notebooks/") and pagename != "notebooks/index":
        suffix = ".zh.ipynb" if locale == "zh" else ".ipynb"
        download = PurePosixPath("downloads") / (pagename + suffix)
        context["notebook_download_url"] = posixpath.relpath(str(download), str(current.parent))
        context["notebook_download_label"] = "下载 notebook" if locale == "zh" else "Download notebook"


def setup(app):
    app.connect("html-page-context", page_context)
