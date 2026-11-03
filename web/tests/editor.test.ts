import { test } from "node:test";
import assert from "node:assert/strict";
import { EventEmitter } from "node:events";
import { createRequire } from "node:module";
import { setEditorMolecule } from "../lib/editor.ts";

// Exercise the installed Ketcher runner, including its swallowed parse errors.
const require = createRequire(import.meta.url);
const {
  runAsyncAction,
} = require("ketcher-core/dist/utilities/runAsyncAction.js");

test("Ketcher's resolved promise after a parse FAILURE must not permit the old canvas to be exported", async () => {
  const eventBus = new EventEmitter();
  const editor = {
    eventBus,
    setMolecule: () =>
      runAsyncAction(async () => {
        throw new Error("invalid ring");
      }, eventBus),
  };
  let exported = false;
  await assert.rejects(async () => {
    await setEditorMolecule(editor, "C1(");
    exported = true;
  }, /SMILES.*无效/);
  assert.equal(exported, false);
  assert.equal(eventBus.listenerCount("FAILURE"), 0);
});

test("valid editor imports succeed and do not leave temporary failure listeners", async () => {
  const eventBus = new EventEmitter();
  let imported = "";
  const editor = {
    eventBus,
    setMolecule: (value: string) =>
      runAsyncAction(async () => {
        imported = value;
      }, eventBus),
  };
  await setEditorMolecule(editor, "CCO");
  assert.equal(imported, "CCO");
  assert.equal(eventBus.listenerCount("FAILURE"), 0);
});
