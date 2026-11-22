"""Project the kernel's product version into package manifests.

Run with Python 3.11 or newer. Check mode reports drift without writing files.
Schema versions, dependency requirements and historical results are independent.
"""

import argparse
import json
from pathlib import Path
import re
import tomllib

ROOT = Path(__file__).resolve().parents[1]
JSON_MANIFESTS = (
    "viz-ui/package.json",
    "viz-ui/packages/components/package.json",
    "viz-ui/packages/debugger/package.json",
    "sdks/typescript/package.json",
)


def projections(root: Path) -> dict[Path, str]:
    """Validate version sources and return changed manifest text only."""
    kernel = tomllib.loads((root / "kernel/Cargo.toml").read_text())
    version = kernel["package"]["version"]
    if not isinstance(version, str) or not version:
        raise ValueError("kernel/Cargo.toml needs a product version")
    project = tomllib.loads((root / "pyproject.toml").read_text())["project"]
    if "version" in project or "version" not in project.get("dynamic", []):
        raise ValueError("pyproject.toml must read the kernel version through maturin")

    changes = {}
    for relative in ("daemon/Cargo.toml", *JSON_MANIFESTS):
        path = root / relative
        source = path.read_text()
        if path.suffix == ".toml":
            current = tomllib.loads(source)["package"]["version"]
            pattern = rf'(?m)^(version\s*=\s*)"{re.escape(current)}"'
        else:
            current = json.loads(source)["version"]
            pattern = rf'(?m)^(  "version":\s*)"{re.escape(current)}"'
        if current == version:
            continue
        updated, count = re.subn(pattern, lambda match: match[1] + json.dumps(version), source)
        if count != 1:
            raise ValueError(f"Expected one top-level version in {relative}")
        changes[path] = updated
    return changes


def main(arguments=None) -> int:
    """Check by default; --write updates only product-version projections."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="update manifest projections")
    args = parser.parse_args(arguments)
    changes = projections(ROOT)
    for path, contents in changes.items():
        print(f"{'Updating' if args.write else 'Version differs:'} {path.relative_to(ROOT)}")
        if args.write:
            path.write_text(contents)
    return 0 if args.write or not changes else 1


if __name__ == "__main__":
    raise SystemExit(main())
