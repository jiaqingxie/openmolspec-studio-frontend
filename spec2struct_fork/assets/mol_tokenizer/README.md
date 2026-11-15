# Vib2Mol molecular tokenizer assets

`vocab.json`, `merges.txt`, `tokenizer_config.json`, and
`special_tokens_map.json` were copied from the local `vib2mol-public` checkout's
`models/MolTokenizer` directory. They are distributed under the Apache 2.0
license in `LICENSE`. The pinned upstream checkout used by `openSpec-alpha`
was unavailable in this workspace, so its asset hashes have not been compared.

`spec2struct.molecule_tokenizer` loads this vocabulary and appends six SMILES
symbols at runtime to represent stereochemistry and other patent notation in
the existing isomeric SMILES dataset. It remaps BOS and PAD IDs to retain the
repository's model tensor convention.
