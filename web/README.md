# OpenMolSpec web

The Next.js browser workspace uses the application API exclusively. The repository root launcher starts all three services; use it for the complete product.

```sh
npm ci
npm run dev
```

Development binds `127.0.0.1:3000`. Node >=24.14.1 is required by Ketcher. `OPENMOLSPEC_API_URL` defaults to `http://127.0.0.1:8000` and is read **at request time** by the streaming `/api/*` transport. It can therefore change between deployments without rebuilding browser assets. Provider credentials belong only in the FastAPI application environment.

```sh
npm test
npm run typecheck
npm run build
npm start
```

The production build also emits Next's standalone server. When packaging it directly, copy `public/` and `.next/static/` into the corresponding standalone directories as described in the root deployment instructions.

## Compatibility

Next 16.4.3 uses the Pages Router with React 18.3.1. Ketcher 3.18.0 advertises React 19 compatibility, but its Miew React 0.11 dependency requires React 18; the selected versions satisfy the complete dependency tree without peer overrides. Next 16 supports React 18 with a deprecation notice for the future Next 17 release. Ketcher and 3Dmol load only in the browser. Acorn is pinned explicitly because Paper.js (inside Ketcher) loads it as an optional dependency during bundling.

## Persistence and scientific inputs

Conversation, message, run and calculation state lives in the services, not browser storage. Only the selected conversation ID is remembered locally. Reopening an active conversation replays its persisted event stream; an interrupted connection resumes from the last received event ID. Leaving a conversation releases the stream without cancelling its server run.

The workbench submits resolved molecule/spectrum IDs. A changed SMILES must be resolved again before submitting a prediction. All four operations display actual capabilities and preserve returned method, domain, units, provenance, inputs and errors. Imported spectra and predicted curves are normalized intensities in the theoretical 400–4000 cm⁻¹ domain. No model results, assistant answers or history are seeded.

## Accounts and external Agents

The account card uses the server session to show the current nickname and shared free Credits. In a development deployment with mock SSO enabled, choose a test identity in **使用公司账号登录**. Open **额度与用量** for the available balance, reserved balance, and task history. Open **访问令牌** to create a named token, choose its validity period, or revoke it. Copy the token before closing its one-time display.

A visitor can draft messages, edit molecules, and stage files in the browser. After signing in, select **保存附件** to save staged files to the current account. The open browser tab keeps draft text and attachments when navigating to the guide and back. Drafts associated with a signed-in account are available to that same account for the lifetime of the tab.

**连接外部 Agent** at `/integrations/mcp` is the public configuration guide for Codex, Claude Code, DeepSeek Harness, and WorkBuddy. It reads the local and cloud addresses from deployment configuration and provides a separate copyable format for each client. Verify discovery in the client, then use `inspect_molecule` with `CCO` to check the connection and `get_capabilities` to see which science operations the deployment can run.
