const token = "MOLSPEC_MCP_TOKEN";
const authorization = "Bearer ${MOLSPEC_MCP_TOKEN}";
const json = (value: unknown) => JSON.stringify(value, null, 2);

export const mcpClients = [
  {
    id: "codex",
    name: "Codex",
    version: "CLI 0.166.0（文档参考版本）",
    docs: "https://developers.openai.com/codex/mcp",
    steps: [
      "将 MolSpec 令牌注入启动 Codex 的环境变量 MOLSPEC_MCP_TOKEN。",
      "把 TOML 段加入 ~/.codex/config.toml。保留其他服务器和设置。若已有同名段，只更新该段的 URL 和令牌字段。",
      "重新启动 Codex，运行 /mcp 确认 MolSpec 的工具可见。codex mcp list 可用于核对已登记的配置。",
    ],
    troubleshooting:
      "能列出配置但工具不可见时，检查 Codex 进程是否继承了变量，以及配置是否使用 HTTP URL。",
    config: (url: string) => [
      {
        name: "config.toml",
        value: `[mcp_servers.molspec]\nurl = ${JSON.stringify(url)}\nbearer_token_env_var = "${token}"`,
      },
    ],
  },
  {
    id: "claude",
    name: "Claude Code",
    version: "CLI 2.1.317（文档参考版本）",
    docs: "https://code.claude.com/docs/en/mcp",
    steps: [
      "将 MolSpec 令牌注入启动 Claude Code 的环境变量 MOLSPEC_MCP_TOKEN。",
      "在当前项目的 .mcp.json 中把 molspec 加入已有 mcpServers 对象。保留其他条目。项目未配置 MCP 时可使用整个示例。",
      "重新打开项目，批准可信的项目 MCP 配置。运行 /mcp 查看连接状态，再请求调用一个 MolSpec 工具。",
    ],
    troubleshooting:
      "若 /mcp 显示未连接，检查项目是否批准该服务器、变量是否存在以及 type 是否为 http。",
    config: (url: string) => [
      {
        name: ".mcp.json",
        value: json({
          mcpServers: {
            molspec: {
              type: "http",
              url,
              headers: { Authorization: authorization },
            },
          },
        }),
      },
    ],
  },
  {
    id: "dsh",
    name: "DeepSeek Harness（DSH）",
    version: "0.2.1-rc.5（文档参考版本）",
    docs: "https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/mcp/mcp-client/README.md",
    steps: [
      "将 MolSpec 令牌注入启动 dsh 的环境变量 MOLSPEC_MCP_TOKEN。当前 CLI 已随附 dsh-mcp-client。",
      "把 insert 段追加到所用配置的 YAML 列表，例如 $DSH_HOME/profiles/web/cordis.patch.yml。保留已有的 patch 条目，并确保 mcp-molspec 只定义一次。",
      "重新启动 dsh web。检查启动日志，确认 Agent 可以调用 mcp__molspec__inspect_molecule。",
    ],
    troubleshooting:
      "若启动成功却没有工具，查看 MCP 插件连接日志，检查 YAML 缩进、配置档案及 streamable-http 字段。",
    config: (url: string) => [
      {
        name: "cordis.patch.yml",
        value:
          "- insert:\n    - id: mcp-molspec\n      name: '@deepseek-ai/dsh-mcp-client'\n" +
          `      config:\n        serverName: molspec\n        transport: streamable-http\n        url: ${JSON.stringify(url)}\n` +
          "        headers:\n          Authorization: !!js '`Bearer ${process.env.MOLSPEC_MCP_TOKEN}`'",
      },
    ],
  },
  {
    id: "workbuddy",
    name: "WorkBuddy",
    version: "4.23.0+（开放平台 Token 连接器）",
    docs: "https://open.workbuddy.cn/docs/connector",
    steps: [
      "按官方开放平台规范创建 MolSpec 专用连接器目录，将下列三个文件保存到该目录，并按官方文档的提交与发布章节附上 icon.svg；如需补充工具使用说明，可加入 skills/。已有 MolSpec 连接器时只合并对应字段。每个连接器配置一个服务器。",
      "先用 WorkBuddy 的连接器测试流程。打开连接凭据表单，在密码字段填入 MolSpec 令牌。连接器会将该字段注入 HTTP 请求头。本地回环地址能否在你的 WorkBuddy 版本使用仍待实测。",
      "确认连接器能列出工具，再在会话中请求 WorkBuddy 调用 MolSpec 检查分子。",
    ],
    troubleshooting:
      "若界面缺少 Token 认证表单，检查客户端版本和连接器加载方式。云端执行器须能访问该 URL；开放平台发布校验要求远程地址使用 HTTPS。",
    config: (url: string) => [
      {
        name: "connector-meta.json",
        value: json({
          name: "MolSpec",
          name_en: "MolSpec",
          description: "Inspect molecules and explore theoretical spectra.",
          source: "molspec",
          description_zh: "检查分子并探索理论光谱。",
          description_en: "Inspect molecules and explore theoretical spectra.",
          type: "mcp",
          auth_mode: "token",
          minWorkbuddyVersion: "4.23.0",
          version: "1.0.0",
          examples_zh: ["用 MolSpec 检查乙醇（CCO）并报告分子式。"],
          examples_en: [
            "Inspect ethanol (CCO) with MolSpec and report its formula.",
          ],
        }),
      },
      {
        name: "mcp.json",
        value: json({
          mcpServers: {
            molspec: {
              type: "streamableHttp",
              url,
              headers: { Authorization: authorization },
            },
          },
        }),
      },
      {
        name: "token-schema.json",
        value: json({
          title: "MolSpec 访问凭据",
          description: "填写 MolSpec 账户页面生成的访问令牌。",
          docUrl: "https://open.workbuddy.cn/docs/connector",
          docLabel: "WorkBuddy 连接器配置指南",
          fields: [
            {
              key: token,
              label: "MolSpec 访问令牌",
              type: "password",
              required: true,
            },
          ],
        }),
      },
    ],
  },
] as const;

export const clientVerification: Partial<
  Record<(typeof mcpClients)[number]["id"], { status: string; detail: string }>
> = {
  codex: {
    status: "已验证连接",
    detail:
      "2026-11-03 · CLI 0.166.0-alpha.5.1 使用环境变量令牌完成连接和工具发现。客户端工具调用待验证。",
  },
  claude: {
    status: "已验证连接",
    detail:
      "2026-11-03 · CLI 2.1.141 使用环境变量令牌通过 claude mcp list 检查连接。客户端工具调用待验证。",
  },
  dsh: {
    status: "工具发现未通过",
    detail:
      "2026-11-03 · CLI 0.2.1-rc.5 使用有效令牌。服务拒绝 2026-07-28 协议的发现请求，并接受 2025-11-25 的初始化请求。客户端仍未列出工具。",
  },
};
