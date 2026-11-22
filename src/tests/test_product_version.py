"""Package metadata and runtime surfaces must report the same product version."""

import asyncio
import importlib.metadata
import importlib.util
import json
from pathlib import Path
import shutil
import sys

import pytest

import reckon
from reckon import _rust
from reckon.cli import main
from reckon.viz.server import create_app

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def version_sync():
    """Repository maintenance tests need the standalone tool's Python version."""
    if sys.version_info < (3, 11):
        pytest.skip("Version synchronization requires Python 3.11 or newer")
    path = ROOT / "tools/sync_version.py"
    if not path.exists():
        pytest.skip("Version synchronization requires the complete checkout")
    spec = importlib.util.spec_from_file_location("sync_version", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_installed_version_reaches_cli_and_debugger(capsys):
    assert reckon.__version__ == _rust.__version__ == importlib.metadata.version("reckon")
    with pytest.raises(SystemExit) as result:
        main(["--version"])
    assert result.value.code == 0
    assert capsys.readouterr().out.strip() == f"reckon {reckon.__version__}"
    app = create_app()
    assert app.openapi()["info"]["version"] == reckon.__version__
    app.state.live_error = None
    health = next(route.endpoint for route in app.routes if getattr(route, "path", "") == "/health")
    assert asyncio.run(health())["version"] == reckon.__version__


def test_version_sync_preserves_dependencies_and_refuses_drift(tmp_path, monkeypatch, version_sync):
    for relative in (
        "kernel/Cargo.toml",
        "daemon/Cargo.toml",
        "pyproject.toml",
        *version_sync.JSON_MANIFESTS,
    ):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    target = tmp_path / "sdks/typescript/package.json"
    original = json.loads(target.read_text())
    changed = dict(original, version="9.8.7")
    target.write_text(json.dumps(changed, indent=2) + "\n")
    before = target.read_bytes()
    monkeypatch.setattr(version_sync, "ROOT", tmp_path)
    assert version_sync.main([]) == 1
    assert target.read_bytes() == before
    assert version_sync.main(["--write"]) == 0
    assert json.loads(target.read_text()) == original
    assert version_sync.main([]) == 0


def test_static_python_version_is_refused_before_projection(tmp_path, version_sync):
    (tmp_path / "kernel").mkdir()
    shutil.copyfile(ROOT / "kernel/Cargo.toml", tmp_path / "kernel/Cargo.toml")
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "9.8.7"\n')
    with pytest.raises(ValueError, match="must read the kernel version"):
        version_sync.projections(tmp_path)
