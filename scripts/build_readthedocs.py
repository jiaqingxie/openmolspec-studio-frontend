"""Build and strictly validate bilingual HTML and executed notebook previews.

The same command is used locally, in CI, and by Read the Docs. Rendering needs
only Mistune; it never imports a model runtime or launches notebook kernels.
"""
import argparse
from functools import lru_cache
import hashlib
import html
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import posixpath
import re
import shutil
from urllib.parse import unquote, urlsplit

import mistune

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT/'documentation'
NAV = [('index.md', 'Home', '首页'), ('quickstart.md', 'Quick start', '快速开始'),
       ('tasks/index.md', 'Tasks', '任务目录'), ('notebooks/index.md', 'Notebooks', 'Notebook'),
       ('datasets.md', 'Dataset download', '数据下载'), ('protocols.md', 'Evaluation', '评测协议'),
       ('publication.md', 'Publication', '发布状态')]
CSS = '''*{box-sizing:border-box}body{margin:0;color:#243b33;background:#fafbf9;font:16px/1.7 system-ui,sans-serif}header{background:#204c3c;color:white;padding:20px 5%;display:flex;justify-content:space-between;gap:24px}header a{color:white}a{color:#21654c;text-underline-offset:3px}main{display:grid;grid-template-columns:240px minmax(0,920px);gap:48px;max-width:1300px;margin:auto;padding:32px 24px}aside nav a{display:block;padding:6px 0}aside{font-size:14px}article{min-width:0}h1{font-size:2rem;line-height:1.25}h2{margin-top:2em;border-bottom:1px solid #d6e2da;padding-bottom:6px}pre{background:#edf2ee;border:1px solid #d6e2da;padding:18px;overflow:auto;border-radius:6px;font-size:13px;line-height:1.5}code{font-family:ui-monospace,monospace}table{display:block;overflow:auto;border-collapse:collapse;width:100%;font-size:14px}th,td{padding:10px;border:1px solid #d6e2da;vertical-align:top;text-align:left}th{background:#e7eee8}input{width:100%;padding:10px;border:1px solid #bdcfc2;border-radius:4px}ul.task-links{padding-left:18px;max-height:55vh;overflow:auto}.task-links li{margin:8px 0}.cell-label{font-size:12px;color:#5e7168}.output{background:white}footer{padding:24px;text-align:center;color:#5e7168;font-size:13px}@media(max-width:800px){main{grid-template-columns:1fr;gap:20px}aside ul.task-links{max-height:160px}header{padding:16px 24px}h1{font-size:1.6rem}}'''


def language(path):
    return 'zh' if '.zh.' in path.name else 'en'


def translated(path, locale):
    base = path.with_name(path.name.replace('.zh.', '.'))
    candidate = base.with_name(base.stem+'.zh'+base.suffix) if locale == 'zh' else base
    return candidate if candidate.is_file() else base


def output_path(source):
    rel = source.relative_to(DOCS)
    name = rel.name.replace('.zh.', '.')
    result = rel.with_name(name).with_suffix('.html')
    return Path('zh')/result if language(source) == 'zh' else result


def relative(target, current):
    return posixpath.relpath(str(target), str(current.parent))


class Renderer(mistune.HTMLRenderer):
    def __init__(self, source):
        super().__init__(escape=True)
        self.source = source
        self.ids = {}

    def heading(self, text, level, **attrs):
        stem = re.sub(r'[^\w\- ]', '', re.sub('<[^>]+>', '', html.unescape(text))).strip().lower().replace(' ', '-') or 'section'
        count = self.ids.get(stem, 0)
        self.ids[stem] = count+1
        anchor = stem if count == 0 else f'{stem}-{count}'
        return f'<h{level} id="{anchor}">{text}</h{level}>\n'

    def link(self, text, url, title=None):
        parsed = urlsplit(url)
        if not parsed.scheme and not parsed.netloc and parsed.path:
            target = (self.source.parent/unquote(parsed.path)).resolve()
            if target.suffix in ('.md', '.ipynb') and target.is_relative_to(DOCS):
                target = translated(target, language(self.source))
                if not target.is_file():
                    raise ValueError(f'Broken source link: {self.source}: {url}')
                url = relative(output_path(target), output_path(self.source))
                if parsed.fragment:
                    url += '#'+parsed.fragment
        return super().link(text, url, title)


def markdown(source, content):
    return mistune.create_markdown(renderer=Renderer(source), plugins=['table', 'strikethrough'])(content)


def notebook_html(source, evaluation_hash):
    book = json.loads(source.read_text())
    sources = [''.join(cell.get('source', [])) for cell in book['cells']]
    execution = book.get('metadata', {}).get('openmolspec_execution', {})
    if execution.get('source_sha256') != hashlib.sha256(json.dumps(sources).encode()).hexdigest():
        raise ValueError(f'Notebook outputs are stale for current source: {source}')
    if execution.get('evaluation_index_sha256') != evaluation_hash:
        raise ValueError(f'Notebook outputs are stale for current evaluation index: {source}')
    fragments = []
    for cell, content in zip(book['cells'], sources):
        if cell['cell_type'] == 'markdown':
            fragments.append(markdown(source, content))
        elif cell['cell_type'] == 'code':
            if cell.get('execution_count') is None:
                raise ValueError(f'Unexecuted demonstration: {source}')
            fragments.append(f'<p class="cell-label">In [{cell["execution_count"]}]</p><pre><code>{html.escape(content)}</code></pre>')
            for result in cell.get('outputs', []):
                if result['output_type'] == 'error':
                    raise ValueError(f'Notebook execution error: {source}')
                text = result.get('text', result.get('data', {}).get('text/plain', []))
                fragments.append('<pre class="output">'+html.escape(''.join(text))+'</pre>')
    return '\n'.join(fragments)


@lru_cache(maxsize=None)
def task_heading(source):
    return source.read_text().splitlines()[0].lstrip('# ')


def page(source, body, sources):
    current = output_path(source)
    locale = language(source)
    other = translated(source, 'en' if locale == 'zh' else 'zh')
    title_match = re.search(r'<h1[^>]*>(.*?)</h1>', body, re.S)
    title = re.sub('<[^>]+>', '', title_match.group(1)) if title_match else source.stem
    nav = ''.join(f'<a href="{relative(output_path(translated(DOCS/path,locale)),current)}">{zh if locale=="zh" else en}</a>' for path,en,zh in NAV)
    tasks = []
    for task in sources:
        if task.parent == DOCS/'tasks' and language(task) == locale and task.stem not in ('index','index.zh'):
            heading = task_heading(task)
            tasks.append(f'<li><a href="{relative(output_path(task),current)}">{html.escape(heading)}</a></li>')
    download = ''
    if source.suffix == '.ipynb':
        raw = Path('downloads')/source.relative_to(DOCS)
        download = f'<p><a download href="{relative(raw,current)}">Download notebook / 下载 notebook</a></p>'
    return f'''<!doctype html><html lang="{locale}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(html.unescape(title))} · OpenMolSpec</title><link rel="stylesheet" href="{relative(Path('assets/docs.css'),current)}"></head><body>
<header><strong>OpenMolSpec · Spectroscopy Workbench</strong><a aria-label="Switch language" href="{relative(output_path(other),current)}">{'English' if locale=='zh' else '简体中文'}</a></header>
<main><aside><nav aria-label="Documentation">{nav}</nav><hr><label for="filter">{'查找任务' if locale=='zh' else 'Find a task'}</label><input id="filter" type="search"><ul class="task-links">{''.join(tasks)}</ul></aside><article>{download}{body}</article></main>
<footer>OpenMolSpec · Frozen inference and recorded evaluation · <a href="https://github.com/jiaqingxie/openmolspec-studio-frontend">Source</a></footer>
<script>document.getElementById('filter').addEventListener('input',function(){{let q=this.value.toLowerCase();document.querySelectorAll('.task-links li').forEach(x=>x.hidden=!x.textContent.toLowerCase().includes(q));}});</script></body></html>'''


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
    parser.add_argument('--output', type=Path, default=ROOT/'site')
    parser.add_argument('--strict', action='store_true', help='All builds validate links and notebook freshness')
    args = parser.parse_args()
    output = args.output.resolve()
    if output == DOCS or output == ROOT or DOCS in output.parents:
        parser.error('Output must not overwrite documentation sources')
    output.mkdir(parents=True, exist_ok=True)
    sources = sorted([*DOCS.rglob('*.md'), *DOCS.rglob('*.ipynb')])
    index_hash = hashlib.sha256((DOCS/'assets/evaluation_index.json').read_bytes()).hexdigest()
    for source in sources:
        rendered = notebook_html(source,index_hash) if source.suffix=='.ipynb' else markdown(source,source.read_text())
        target = output/output_path(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(page(source,rendered,sources))
        if source.suffix == '.ipynb':
            raw = output/'downloads'/source.relative_to(DOCS)
            raw.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(source,raw)
    shutil.copytree(DOCS/'assets',output/'assets',dirs_exist_ok=True)
    (output/'assets/docs.css').write_text(CSS)
    count = validate(output)
    result = {'completed': True, 'html_pages': count,
              'notebook_previews': sum(p.suffix=='.ipynb' for p in sources),
              'languages': ['en','zh'], 'internal_links_verified': True,
              'notebook_source_and_evaluation_hashes_verified': True,
              'renderer': f'mistune {mistune.__version__}', 'remote_publication_verified': False}
    (output/'build-manifest.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
