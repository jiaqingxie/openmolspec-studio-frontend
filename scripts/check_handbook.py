"""Check handbook navigation and local links without requiring MkDocs."""

from pathlib import Path
import re
import sys

import yaml

ROOT = Path(__file__).resolve().parents[1]
config = yaml.safe_load((ROOT / "mkdocs.yml").read_text())
directory = ROOT / config["docs_dir"]
failures = []


def navigation(items):
    for item in items:
        for _, target in item.items():
            if isinstance(target, list):
                yield from navigation(target)
            else:
                yield target


for name in navigation(config["nav"]):
    if not (directory / name).is_file():
        failures.append(f"Missing navigation page: {name}")
for page in directory.glob("*.md"):
    for link in re.findall(r"\[[^\]]*\]\(([^)]+)\)", page.read_text()):
        if re.match(r"^[a-z]+:", link) or link.startswith("#"):
            continue
        destination = (page.parent / link.split("#")[0]).resolve()
        if not destination.exists():
            failures.append(f"Broken local link in {page.name}: {link}")
if failures:
    print("\n".join(failures), file=sys.stderr)
    raise SystemExit(1)
print(f"Handbook navigation and links passed: {len(list(directory.glob('*.md')))} pages")
