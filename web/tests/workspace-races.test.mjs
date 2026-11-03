// Deferred-response harness from the read-only molspec interface review.
// This deliberately isolates Workspace's event handlers: useChat/network and React
// hooks are mocked, child components are opaque JSX nodes, and effects are skipped.
// It does not exercise browser layout, actual React scheduling, SSE or useChat.
// Uses the actual component handlers with deferred network boundaries. Browser QA covers rendering.
import fs from "node:fs";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import path from "node:path";
import vm from "node:vm";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
const root = fileURLToPath(new URL("../../", import.meta.url));
const require = createRequire(path.join(root, "web/package.json"));
const ts = require("typescript");
const compile = (source) =>
  ts.transpileModule(source, {
    compilerOptions: {
      jsx: ts.JsxEmit.ReactJSX,
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022,
    },
  }).outputText;
const code = compile(
  fs.readFileSync(path.join(root, "web/components/workspace.tsx"), "utf8"),
);
// Load the actual current composer helpers, including the new settlement helper.
const composerContext = { exports: {} };
vm.runInNewContext(
  compile(fs.readFileSync(path.join(root, "web/lib/composer.ts"), "utf8")),
  composerContext,
);
const composerHelpers = composerContext.exports;
function harness() {
  const cells = [];
  let cursor = 0;
  let sendResolve;
  let uploadResolve;
  const sent = [];
  const chat = {
    history: [{ id: "B", title: "Other conversation" }],
    conversationId: "A",
    state: { messages: [], tools: [], stage: "", terminal: false },
    loading: false,
    busy: false,
    connection: "idle",
    error: null,
    setError() {},
    newConversation() {
      this.conversationId = null;
    },
    openConversation(id) {
      this.conversationId = id;
    },
    async send(input) {
      sent.push(input);
      return new Promise((resolve) => {
        sendResolve = resolve;
      });
    },
  };
  const jsx = (type, props) => ({ type, props: props || {} });
  const react = {
    useState(initial) {
      const i = cursor++;
      if (!(i in cells))
        cells[i] = typeof initial === "function" ? initial() : initial;
      return [
        cells[i],
        (v) => {
          cells[i] = typeof v === "function" ? v(cells[i]) : v;
        },
      ];
    },
    useRef(initial) {
      const i = cursor++;
      if (!(i in cells)) cells[i] = { current: initial };
      return cells[i];
    },
    useEffect() {},
  };
  const imports = {
    react,
    "react/jsx-runtime": { jsx, jsxs: jsx },
    "next/dynamic": { default: () => "MoleculeComposer" },
    "@/lib/use-chat": { useChat: () => chat },
    "@/lib/api": {
      api: {
        upload: () =>
          new Promise((resolve) => {
            uploadResolve = resolve;
          }),
      },
      errorMessage: (error) => error.message,
    },
    "@/lib/composer": composerHelpers,
    "@/lib/science": { toolLabels: {} },
    "@phosphor-icons/react": {},
    "react-markdown": {},
    "remark-gfm": {},
    "./attachment-card": { AttachmentCard: "AttachmentCard" },
    "./attachment-preview": { AttachmentPreview: "AttachmentPreview" },
    "./calculation-results": { CalculationResults: "CalculationResults" },
    "./spectrum-upload": { SpectrumUpload: "SpectrumUpload" },
    "./spectrum-chart": { SpectrumChart: "SpectrumChart" },
    "./status-dialog": { StatusDialog: "StatusDialog" },
    "./dialog": { Dialog: "Dialog" },
    "./account-session": { useAccount: () => ({}) },
    "./sidebar-account": { SidebarAccount: "SidebarAccount" },
    "./brand": { MolspecMark: "MolspecMark" },
  };
  const context = {
    exports: {},
    require: (name) => {
      if (!(name in imports)) throw new Error("Unexpected import " + name);
      return imports[name];
    },
    requestAnimationFrame() {},
    window: {},
    document: {},
  };
  vm.runInNewContext(code, context);
  let composer = { text: "", attachments: [] };
  function render() {
    cursor = 0;
    return context.exports.Workspace({
      userId: "test-user",
      composer,
      setComposer: (value) => {
        composer = typeof value === "function" ? value(composer) : value;
      },
    });
  }
  function nodes(node) {
    if (!node || typeof node !== "object") return [];
    if (Array.isArray(node)) return node.flatMap(nodes);
    return [node, ...nodes(node.props?.children)];
  }
  function find(tree, predicate) {
    const result = nodes(tree).find(predicate);
    if (!result) throw new Error("Missing node");
    return result;
  }
  return {
    render,
    find,
    nodes,
    chat,
    sent,
    resolveSend: () => sendResolve(true),
    resolveUpload: () =>
      uploadResolve({
        id: "attachment-A",
        name: "research-A.xyz",
        kind: "molecule",
        molecule_id: "molecule-A",
        size: 1,
      }),
  };
}
const tick = () => new Promise((resolve) => setImmediate(resolve));
test("pending send preserves an unsent follow-up typed before the POST response", async () => {
  const h = harness();
  let t = h.render();
  h.find(t, (n) => n.type === "textarea").props.onChange({
    target: { value: "Original question" },
  });
  t = h.render();
  h.find(t, (n) => n.type === "form").props.onSubmit({ preventDefault() {} });
  t = h.render();
  h.find(t, (n) => n.type === "textarea").props.onChange({
    target: { value: "Unsent follow-up" },
  });
  h.resolveSend();
  await tick();
  t = h.render();
  assert.equal(h.sent[0].content, "Original question");
  assert.equal(
    h.find(t, (n) => n.type === "textarea").props.value,
    "Unsent follow-up",
  );
});

for (const destination of ["new", "other"])
  test(`late upload cannot enter a ${destination} conversation`, async () => {
    const h = harness();
    let t = h.render();
    h.find(
      t,
      (n) => n.type === "input" && n.props.type === "file",
    ).props.onChange({
      target: { files: [{ name: "research-A.csv", size: 1 }], value: "file" },
    });
    t = h.render();
    h.find(t, (n) => n.type === "SpectrumUpload").props.onSubmit({
      axis_unit: "cm^-1",
      intensity_unit: "a.u.",
      domain: "theoretical",
      axis_mode: "explicit",
    });
    t = h.render();
    h.find(
      t,
      (n) =>
        n.props.className ===
        (destination === "new" ? "new-chat" : "history-link"),
    ).props.onClick();
    h.resolveUpload();
    await tick();
    t = h.render();
    assert.equal(h.chat.conversationId, destination === "new" ? null : "B");
    assert.equal(
      h.nodes(t).filter((n) => n.type === "AttachmentCard").length,
      0,
    );
  });

test("the four scientific presets edit the draft without submitting a message", () => {
  const h = harness();
  let t = h.render();
  const presets = h.find(t, (n) => n.props.className === "composer-presets");
  const buttons = h.nodes(presets).filter((n) => n.type === "button");
  assert.deepEqual(
    buttons.map((button) => button.props.children),
    [
      "预测分子光谱",
      "根据光谱检索分子",
      "根据光谱推测结构",
      "根据光谱估算能隙",
    ],
  );
  buttons[1].props.onClick();
  t = h.render();
  const textarea = h.find(t, (n) => n.type === "textarea");
  assert.match(textarea.props.value, /检索候选分子/);
  textarea.props.onChange({ target: { value: "我的自定义问题" } });
  assert.equal(
    h.find(h.render(), (n) => n.type === "textarea").props.value,
    "我的自定义问题",
  );
  assert.equal(h.sent.length, 0);
});
