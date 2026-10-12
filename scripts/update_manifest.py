#!/usr/bin/env python3
"""Generate or check the deterministic list of distributable skill files."""
import argparse
import hashlib
from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--check", action="store_true")
args = parser.parse_args()
lines = []
for path in sorted((root / "skills").rglob("*")):
    if path.is_symlink():
        raise SystemExit("Symlinks are not distributable: " + str(path))
    if not path.is_file():
        continue
    relative = path.relative_to(root).as_posix()
    if not re.fullmatch(r"skills/[a-z0-9]+(?:-[a-z0-9]+)*/[A-Za-z0-9_./-]+", relative):
        raise SystemExit("Unsupported path: " + relative)
    if any(part in (".", "..") or part.startswith("-") for part in relative.split("/")):
        raise SystemExit("Unsafe path: " + relative)
    lines.append(hashlib.sha256(path.read_bytes()).hexdigest() + "  " + relative + "\n")
if not lines:
    raise SystemExit("No skill files found")
result = "".join(lines)
manifest = root / "manifest.sha256"
if args.check:
    if not manifest.exists() or manifest.read_text() != result:
        raise SystemExit("Manifest is out of date. Run python3 scripts/update_manifest.py")
    print("Manifest OK")
else:
    manifest.write_text(result)
    print("Updated manifest.sha256")
