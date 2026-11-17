"""Build bilingual Sphinx documentation with the classic Read the Docs theme.

Notebook outputs must be executed and current before building. Rendering never
executes notebooks or imports the model runtimes. English and Chinese have
separate localized navigation and search indexes, while existing URLs are kept.
"""
import argparse
import hashlib
from html.parser import HTMLParser
import importlib.metadata
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "documentation"
CONFIG = DOCS / "sphinx"


def notebook_evidence_hash(book):
    paths=book.get('metadata',{}).get('openmolspec_evidence_files',[])
    return hashlib.sha256(json.dumps([(p,hashlib.sha256((ROOT/p).read_bytes()).hexdigest()) for p in paths]).encode()).hexdigest()


def validate_notebook(source, evaluation_hash):
    book = json.loads(source.read_text())
    if book.get("metadata", {}).get("mystnb", {}).get("execution_mode", "off") != "off":
        raise ValueError(f"Notebook build-time execution override is not allowed: {source}")
    sources = ["".join(cell.get("source", [])) for cell in book["cells"]]
    execution = book.get("metadata", {}).get("openmolspec_execution", {})
    if execution.get("source_sha256") != hashlib.sha256(json.dumps(sources).encode()).hexdigest():
        raise ValueError(f"Notebook outputs are stale for current source: {source}")
    if execution.get("evaluation_index_sha256") != evaluation_hash:
        raise ValueError(f"Notebook outputs are stale for current evaluation index: {source}")
    if book.get('metadata',{}).get('openmolspec_evidence_files') and execution.get('evidence_sha256') != notebook_evidence_hash(book):
        raise ValueError(f"Notebook outputs are stale for current evidence or plotting code: {source}")
    for cell in book["cells"]:
        if cell["cell_type"] == "code":
            if cell.get("execution_count") is None:
                raise ValueError(f"Unexecuted demonstration: {source}")
            if any(output["output_type"] == "error" for output in cell.get("outputs", [])):
                raise ValueError(f"Notebook execution error: {source}")


def source_locale(path):
    return "zh" if ".zh." in path.name else "en"


def source_relative(path):
    relative = path.relative_to(DOCS)
    return relative.with_name(relative.name.replace(".zh.", "."))


def add_toctree(content, entries):
    """Attach child pages to the page title rather than its final subsection."""
    title = re.search(r"^# [^\n]+(?:\n|$)", content, re.MULTILINE)
    if title is None:
        raise ValueError("A navigation parent must have a top-level page title")
    tree = "\n```{toctree}\n:hidden:\n:maxdepth: 2\n\n" + "\n".join(entries) + "\n```\n\n"
    return content[:title.end()] + tree + content[title.end():].lstrip("\n")


def stage_sources(target, sources, locale):
    sys.path.insert(0,str(ROOT))
    sys.path.insert(0,str(ROOT/'scripts'))
    from documentation_content import GROUPS, group
    from openmolspec_bench.catalog import TASKS
    shutil.copytree(DOCS/'assets',target/'assets',dirs_exist_ok=True)
    for source in sources:
        if source_locale(source) != locale:
            continue
        relative = source_relative(source)
        dest = target / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        if source.suffix == ".ipynb":
            shutil.copyfile(source, dest)
            continue
        content = source.read_text()
        # Both locale trees use the same page names; only the output root differs.
        content = re.sub(r"(?<=\.)zh\.(?=(?:md|ipynb)(?:[)#?]))", "", content)
        if relative.as_posix() == "index.md":
            content = add_toctree(content, ["quickstart", "data/index", "tasks/index", "model-audit", "api", "notebooks/index", "theory/index", "inversion/index", "gallery", "harness", "api-reference/index", "benchmarks", "faq", "contributing", "citations"])
        elif relative.as_posix() == 'api-reference/index.md':
            from build_api_reference import GROUPS as API_GROUPS
            content = add_toctree(content, ['category-'+key for key,_,_ in API_GROUPS])
        elif relative.parent.as_posix()=='api-reference' and relative.stem.startswith('category-'):
            from build_api_reference import category,inventory,slug
            content = add_toctree(content,[slug(row['module']) for row in inventory() if category(row['module'])==relative.stem[len('category-'):]])
        elif relative.as_posix() == 'data/index.md':
            content = add_toctree(content, ['nmr', 'ms', 'vibrational', 'multimodal', 'splits', 'comparison'])
        elif relative.as_posix() == 'theory/index.md':
            content = add_toctree(content, ['nmr', 'ms', 'vibrational'])
        elif relative.as_posix() == 'harness.md':
            content = add_toctree(content, ['harness/'+name for name in ['quickstart','python','cli','mcp','nmr','ms','vibrational','examples']])
        elif relative.as_posix() == 'benchmarks.md':
            content = add_toctree(content, ['benchmarks/'+name for name in ['nmr','ms','vibrational','multimodal','production','training']])
        elif relative.as_posix() == 'tasks/index.md':
            content = add_toctree(content, [key for key,_,_ in GROUPS])
        elif relative.parent.as_posix()=='tasks' and relative.stem in [g[0] for g in GROUPS]:
            content = add_toctree(content,[t.id.replace('.','-') for t in TASKS if group(t)==relative.stem])
        elif relative.as_posix() == "notebooks/index.md":
            children = sorted(source_relative(p).stem for p in sources
                              if p.parent == source.parent and source_locale(p) == locale
                              and source_relative(p).stem != "index")
            content = add_toctree(content, children)
        dest.write_text(content)


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links, self.ids = [], set()

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if values.get('id'):
            self.ids.add(values['id'])
        for key in ('href', 'src'):
            if values.get(key):
                self.links.append(values[key])


def validate(output):
    pages = {}
    for path in output.rglob('*.html'):
        parser = Links()
        parser.feed(path.read_text())
        pages[path.resolve()] = parser
    failures = []
    for source, parsed in pages.items():
        for link in parsed.links:
            url = urlsplit(link)
            if url.scheme or url.netloc:
                continue
            target = (source.parent/unquote(url.path)).resolve() if url.path else source
            if not target.is_relative_to(output.resolve()) or not target.is_file():
                failures.append(f'{source.name}: missing {link}')
            elif url.fragment and target in pages and unquote(url.fragment) not in pages[target].ids:
                failures.append(f'{source.name}: missing anchor {link}')
    if failures:
        raise ValueError('\n'.join(failures))
    return len(pages)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "site")
    parser.add_argument("--strict", action="store_true", help="All builds enforce Sphinx warnings, links and notebook freshness")
    args = parser.parse_args()
    output = args.output.resolve()
    if output == ROOT or output == DOCS or DOCS in output.parents or output in ROOT.parents:
        parser.error("Output must not overwrite the repository or documentation sources")
    sources = sorted([*DOCS.rglob("*.md"), *DOCS.rglob("*.ipynb")])
    evaluation_hash = hashlib.sha256((DOCS / "assets/evaluation_index.json").read_bytes()).hexdigest()
    for source in sources:
        if source.suffix == ".ipynb":
            validate_notebook(source, evaluation_hash)
    with tempfile.TemporaryDirectory(prefix="openmolspec-sphinx-") as temporary:
        scratch = Path(temporary)
        rendered = scratch / "html"
        for locale, sphinx_language in (("en", "en"), ("zh", "zh_CN")):
            source_dir = scratch / ("source-" + locale)
            stage_sources(source_dir, sources, locale)
            destination = rendered if locale == "en" else rendered / "zh"
            env = os.environ.copy()
            env["OPENMOLSPEC_DOCS_LOCALE"] = locale
            subprocess.run([sys.executable, "-m", "sphinx", "-b", "html", "-W", "--keep-going",
                            "-c", str(CONFIG), "-d", str(scratch / ("doctrees-" + locale)),
                            "-D", "language=" + sphinx_language, str(source_dir), str(destination)],
                           env=env, check=True)
        for source in sources:
            if source.suffix == ".ipynb":
                download = rendered / "downloads" / source.relative_to(DOCS)
                download.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, download)
        shutil.copytree(DOCS / "assets", rendered / "assets", dirs_exist_ok=True)
        shutil.copytree(DOCS / "assets", rendered / "zh/assets", dirs_exist_ok=True)
        count = validate(rendered)
        result = {"completed": True, "content_pages": len(sources), "html_pages": count,
                  "notebook_previews": sum(p.suffix == ".ipynb" for p in sources),
                  "languages": ["en", "zh"], "internal_links_verified": True,
                  "notebook_source_and_evaluation_hashes_verified": True,
                  "notebook_execution_during_build": False,
                  "renderer": "Sphinx " + importlib.metadata.version("Sphinx"),
                  "theme": "sphinx_rtd_theme " + importlib.metadata.version("sphinx-rtd-theme"),
                  "search_indexes": ["searchindex.js", "zh/searchindex.js"],
                  "remote_publication_verified": False}
        (rendered / "build-manifest.json").write_text(json.dumps(result, indent=2) + "\n")
        output.mkdir(parents=True, exist_ok=True)
        shutil.copytree(rendered, output, dirs_exist_ok=True)
        print(json.dumps(result))


if __name__ == "__main__":
    main()
