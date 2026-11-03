import { test } from "node:test";
import assert from "node:assert/strict";
import http from "node:http";
import { once } from "node:events";
import { loadAttachment } from "../lib/attachments.ts";
import type { Attachment, Molecule } from "../lib/types.ts";

// An uploaded coordinate input, not an inference result. Deliberately translated
// away from the origin so coordinate regeneration cannot pass unnoticed.
const saved: Molecule = {
  id: "saved-water-conformer",
  smiles: "O",
  formula: "H2O",
  molecular_weight: 18.015,
  atom_count: 3,
  inchi_key: "XLYOFNOQVPJJNP-UHFFFAOYSA-N",
  molblock: "uploaded-coordinate-input",
  xyz: "3\nuploaded water\nO 10.0 20.0 30.0\nH 10.0 20.0 31.0\nH 10.0 21.0 30.0\n",
  svg: '<svg xmlns="http://www.w3.org/2000/svg"/>',
};
const attachment: Attachment = {
  id: "upload-xyz",
  name: "water.xyz",
  kind: "molecule",
  molecule_id: saved.id,
  smiles: "O",
  size: 90,
};

test("new and historical XYZ attachments load the exact stored molecule by ID over HTTP, without resolving SMILES", async () => {
  const paths: string[] = [];
  const server = http.createServer((req, res) => {
    paths.push(`${req.method} ${req.url}`);
    if (req.method === "GET" && req.url === `/api/molecules/${saved.id}`) {
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify(saved));
    } else {
      res.writeHead(405);
      res.end("Coordinate regeneration is not allowed");
    }
  });
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  const address = server.address();
  if (!address || typeof address === "string")
    throw new Error("No TCP address");
  const origin = `http://127.0.0.1:${address.port}`;
  const realFetch = globalThis.fetch;
  globalThis.fetch = (input, init) =>
    realFetch(
      typeof input === "string" && input.startsWith("/")
        ? `${origin}${input}`
        : input,
      init,
    );
  try {
    for (const input of [
      attachment,
      JSON.parse(JSON.stringify(attachment)) as Attachment,
    ]) {
      const loaded = await loadAttachment(input);
      assert.equal(loaded.kind, "molecule");
      if (loaded.kind === "molecule") {
        assert.equal(loaded.molecule.id, saved.id);
        assert.equal(loaded.molecule.xyz, saved.xyz);
        assert.equal(loaded.molecule.molblock, saved.molblock);
      }
    }
    assert.deepEqual(paths, [
      `GET /api/molecules/${saved.id}`,
      `GET /api/molecules/${saved.id}`,
    ]);
    await assert.rejects(
      loadAttachment({ ...attachment, molecule_id: undefined }),
      /保存.*结构/,
    );
    assert.equal(paths.length, 2);
  } finally {
    globalThis.fetch = realFetch;
    server.closeAllConnections();
    await new Promise<void>((resolve) => server.close(() => resolve()));
  }
});
