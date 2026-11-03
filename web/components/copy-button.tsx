import { useState } from "react";

export function CopyButton({ value, label }: { value: string; label: string }) {
  const [status, setStatus] = useState("");
  async function copy() {
    try {
      await navigator.clipboard.writeText(value);
      setStatus(label === "复制令牌" ? "令牌已复制" : "配置已复制");
    } catch {
      setStatus("无法访问剪贴板，可手动选择并复制。");
    }
  }
  return (
    <span className="copy-action">
      <button className="button" onClick={() => void copy()}>
        {label}
      </button>
      <span role="status">{status}</span>
    </span>
  );
}
