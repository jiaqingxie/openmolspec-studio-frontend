import unittest

from openmolspec_ui.chemistry import (
    molecule_3d_html,
    molecule_from_smiles,
    molecule_svg,
    smiles_png,
    smiles_svg,
)


class ChemistryTests(unittest.TestCase):
    def test_smiles_generates_a_reproducible_conformer(self):
        molecule = molecule_from_smiles("CCO")
        self.assertEqual(molecule.formula, "C2H6O")
        self.assertEqual(molecule.mol.GetNumConformers(), 1)
        self.assertIn("<svg", molecule_svg(molecule))

    def test_molecule_generates_an_interactive_3d_view(self):
        drawing = molecule_3d_html(molecule_from_smiles("CCO"))
        self.assertIn("3dmolviewer_", drawing)
        self.assertIn("addModel", drawing)
        self.assertIn("zoomTo", drawing)

    def test_invalid_smiles_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "SMILES"):
            molecule_from_smiles("C(")

    def test_smiles_svg_renders_valid_structure(self):
        drawing = smiles_svg("CCO")
        self.assertIsNotNone(drawing)
        self.assertIn("<svg", drawing)

    def test_smiles_svg_returns_none_for_invalid_structure(self):
        self.assertIsNone(smiles_svg("C("))

    def test_smiles_png_renders_valid_structure(self):
        drawing = smiles_png("CCO")
        self.assertIsNotNone(drawing)
        self.assertTrue(drawing.startswith(b"\x89PNG\r\n\x1a\n"))

    def test_smiles_png_returns_none_for_invalid_structure(self):
        self.assertIsNone(smiles_png("C("))


if __name__ == "__main__":
    unittest.main()
