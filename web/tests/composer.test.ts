import { test } from "node:test";
import assert from "node:assert/strict";
import {
  createMessageInput,
  insertSmiles,
  settleSubmittedDraft,
} from "../lib/composer.ts";
import type { Attachment } from "../lib/types.ts";

const attachment: Attachment = {
  id: "attached-ethanol",
  name: "C2H6O.mol",
  kind: "molecule",
  molecule_id: "saved-ethanol",
  smiles: "CCO",
  size: 100,
};

test("SMILES insertion preserves the question and replaces only the selected range", () => {
  assert.deepEqual(insertSmiles("", "CCO"), { text: "SMILES: CCO", caret: 11 });
  const draft = "请分析这个分子\n旧结构\n并解释可能的官能团";
  const start = draft.indexOf("旧结构");
  const result = insertSmiles(draft, "CCO", { start, end: start + 3 });
  assert.equal(result.text, "请分析这个分子\nSMILES: CCO\n并解释可能的官能团");
  assert.equal(
    result.text.slice(0, result.caret),
    "请分析这个分子\nSMILES: CCO",
  );
});

test("SMILES insertion appends a separate line without overwriting the draft", () => {
  const result = insertSmiles("预测它的红外光谱", "c1ccccc1");
  assert.equal(result.text, "预测它的红外光谱\nSMILES: c1ccccc1");
  assert.equal(result.caret, result.text.length);
});

test("an attachment-only message reaches the Agent with durable references and a neutral request", () => {
  const result = createMessageInput("  ", [attachment]);
  assert.ok(result?.content.trim());
  assert.deepEqual(result?.attachment_ids, [attachment.id]);
  assert.equal(result?.mode, "deep");
  assert.equal(createMessageInput(" ", []), null);
  assert.equal(
    createMessageInput("  分析它  ", [attachment])?.content,
    "分析它",
  );
});

test("a delayed send clears only submitted text and attachments, preserving a follow-up and new attachment", () => {
  const nextAttachment = { ...attachment, id: "new-attachment" };
  const sent = { text: "分析乙醇", attachments: [attachment] };
  assert.deepEqual(
    settleSubmittedDraft(
      { text: "接下来比较苯", attachments: [attachment, nextAttachment] },
      sent,
    ),
    { text: "接下来比较苯", attachments: [nextAttachment] },
  );
  assert.deepEqual(
    settleSubmittedDraft(
      { text: sent.text, attachments: sent.attachments },
      sent,
    ),
    { text: "", attachments: [] },
  );
});

test("reused calculation spectra send saved IDs and a delayed send leaves newer references intact", () => {
  const ir = {
    id: "stored-prediction-ir",
    name: "预测 IR",
    modality: "ir" as const,
  };
  const raman = {
    id: "stored-prediction-raman",
    name: "预测 Raman",
    modality: "raman" as const,
  };
  assert.deepEqual(
    createMessageInput("对比两条光谱", [], [ir, raman])?.context,
    { ir_id: ir.id, raman_id: raman.id },
  );
  assert.deepEqual(
    settleSubmittedDraft(
      { text: "后续问题", attachments: [], spectra: [ir, raman] },
      { text: "分析", attachments: [], spectra: [ir] },
    ).spectra,
    [raman],
  );
});
