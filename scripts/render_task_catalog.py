"""Render the handbook task table from the catalog, without ML dependencies."""

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from openmolspec_bench.catalog import TASKS


def render():
    lines = ["# 任务目录", "", "此表由 `openmolspec_bench/catalog.py` 自动生成，与命令行和 Studio 使用同一份定义。",
             "", "已接入表示存在评测适配器，仍需对应权重与数据；待接入不会产生占位分数。", "",
             "| ID | 任务 | 谱型 | 数据域 | 适配器 | 指标 |", "| --- | --- | --- | --- | --- | --- |"]
    for task in (t for t in TASKS if t.enabled):
        backend = "待接入" if task.backend == "unavailable" else task.backend
        lines.append(f"| `{task.id}` | {task.title} | {', '.join(task.modalities)} | {task.domain} | {backend} | {', '.join(task.metrics)} |")
    lines.extend(["", "## 任务说明", ""])
    for task in (t for t in TASKS if t.enabled):
        if task.note:
            lines.extend([f"- **{task.id}**：{task.note}", ""])
    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    destination = ROOT / "handbook/tasks.md"
    content = render()
    if args.check:
        if not destination.is_file() or destination.read_text() != content:
            raise SystemExit("Task catalog differs from handbook; run python scripts/render_task_catalog.py")
    else:
        destination.write_text(content)
    print(f"{len(TASKS)} tasks; {sum(t.backend != 'unavailable' for t in TASKS)} evaluation adapters")
