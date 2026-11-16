import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('docs_build',ROOT/'scripts/build_readthedocs.py')
builder=importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class DocumentationBuildTests(unittest.TestCase):
    def test_changed_notebook_source_cannot_reuse_old_outputs(self):
        notebook=json.loads((ROOT/'documentation/notebooks/nmr-assignment.ipynb').read_text())
        next(c for c in notebook['cells'] if c['cell_type']=='code')['source']=['print("changed example")']
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'changed.ipynb'
            path.write_text(json.dumps(notebook))
            with self.assertRaisesRegex(ValueError,'stale'):
                builder.notebook_html(path,'irrelevant')

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
