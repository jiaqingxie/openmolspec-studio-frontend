import importlib.util
import hashlib
import json
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('docs_build',ROOT/'scripts/build_readthedocs.py')
builder=importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class DocumentationBuildTests(unittest.TestCase):
    def test_child_pages_belong_to_page_not_references_or_deferred_section(self):
        from sphinx.application import Sphinx
        from sphinx import addnodes
        from docutils import nodes

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'source'
            source.mkdir()
            (source / 'conf.py').write_text("extensions = ['myst_parser']\nmaster_doc = 'index'\n")
            parents = [('data', '数据', '参考文献'),
                       ('tasks', 'Tasks', '暂不推进'),
                       ('benchmarks', 'Benchmarks', 'References')]
            (source / 'index.md').write_text(builder.add_toctree('# Manual\n', [p[0] for p in parents]))
            for name, title, final_section in parents:
                content = f'# {title}\n\nIntroduction.\n\n## {final_section}\n\nSection contents.\n'
                (source / f'{name}.md').write_text(builder.add_toctree(content, [name + '-child']))
                (source / f'{name}-child.md').write_text('# Child page\n')
            warnings = io.StringIO()
            app = Sphinx(str(source), str(source), str(root / 'html'), str(root / 'doctrees'),
                         'dummy', status=io.StringIO(), warning=warnings, freshenv=True)
            app.build(force_all=True)
            self.assertEqual(warnings.getvalue(), '')
            for name, title, final_section in parents:
                document = app.env.get_doctree(name)
                tree, = list(document.findall(addnodes.toctree))
                page_section = next(node for node in document.children if isinstance(node, nodes.section))
                section = tree.parent
                while not isinstance(section, nodes.section):
                    section = section.parent
                self.assertIs(section, page_section)
                self.assertEqual(section[0].astext(), title)

    def test_changed_evidence_rejects_saved_notebook_outputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            evidence = root / 'evidence.json'
            evidence.write_text('{"prediction": 1}')
            notebook = {
                'cells': [{'cell_type': 'code', 'source': ['print(1)'],
                           'execution_count': 1, 'outputs': []}],
                'metadata': {'openmolspec_evidence_files': ['evidence.json']},
            }
            with patch.object(builder, 'ROOT', root):
                notebook['metadata']['openmolspec_execution'] = {
                    'source_sha256': hashlib.sha256(json.dumps(['print(1)']).encode()).hexdigest(),
                    'evaluation_index_sha256': 'index',
                    'evidence_sha256': builder.notebook_evidence_hash(notebook),
                }
                path = root / 'example.ipynb'
                path.write_text(json.dumps(notebook))
                builder.validate_notebook(path, 'index')
                evidence.write_text('{"prediction": 2}')
                with self.assertRaisesRegex(ValueError, 'stale for current evidence'):
                    builder.validate_notebook(path, 'index')

    def test_notebook_cannot_enable_execution_during_publication(self):
        notebook=json.loads((ROOT/'documentation/notebooks/nmr-assignment.ipynb').read_text())
        notebook['metadata']['mystnb']={'execution_mode':'force'}
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'override.ipynb'
            path.write_text(json.dumps(notebook))
            with self.assertRaisesRegex(ValueError,'execution override'):
                builder.validate_notebook(path,'irrelevant')

    def test_changed_notebook_source_cannot_reuse_old_outputs(self):
        notebook=json.loads((ROOT/'documentation/notebooks/nmr-assignment.ipynb').read_text())
        next(c for c in notebook['cells'] if c['cell_type']=='code')['source']=['print("changed example")']
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'changed.ipynb'
            path.write_text(json.dumps(notebook))
            with self.assertRaisesRegex(ValueError,'stale'):
                builder.validate_notebook(path,'irrelevant')

    def test_html_validation_checks_both_files_and_fragments(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            (root/'index.html').write_text('<a href="missing.html">Broken</a>')
            with self.assertRaisesRegex(ValueError,'missing'):
                builder.validate(root)
            (root/'index.html').write_text('<a href="other.html#bad">Broken fragment</a>')
            (root/'other.html').write_text('<h1 id="good">Good</h1>')
            with self.assertRaisesRegex(ValueError,'anchor'):
                builder.validate(root)
            (root/'index.html').write_text('<a href="other.html#good">Valid</a>')
            self.assertEqual(builder.validate(root),2)


if __name__=='__main__':unittest.main()
