"""Reference exports preserve wire distinctions and do not start the debugger."""

import json
from pathlib import Path
import re
import runpy

import pytest

pytest.importorskip("google.protobuf", reason="Install the proto extra for reference export.")

ROOT = Path(__file__).resolve().parents[2]
EXPORT = runpy.run_path(str(ROOT / "tools/export_reference.py"))


def test_protocol_reference_preserves_wire_contract(tmp_path):
    pytest.importorskip("grpc_tools")
    protos = tmp_path / "protos"
    protos.mkdir()
    (protos / "sample.proto").write_text("""syntax = "proto3";
package sample;
// A value with explicit absence and a choice.
message Input {
  // Zero is present; absent is distinct. A | B < C.
  optional double score = 7;
  // Choose either a readable name or opaque data.
  oneof choice { string name = 8; bytes data = 9; }
  map<string, Nested> children = 10;
  message Nested { string value = 1; }
  repeated int64 steps = 11;
  State state = 12;
}
enum State { UNKNOWN = 0; READY = 3; }
service Reader { rpc Read(stream Input) returns (stream Input); }
""")
    reference = EXPORT["protobuf_reference"](tmp_path)
    assert (
        "| `score` | 7 | double | optional | Zero is present; absent is distinct. A &#124; B &lt; C. |"
        in reference
    )
    assert "| `name` | 8 | string | oneof `choice` |" in reference
    assert "| `data` | 9 | bytes | oneof `choice` |" in reference
    assert "map&lt;string, [sample.Input.Nested](#sample-input-nested)&gt; | map |" in reference
    assert "### sample.Input.Nested" in reference
    assert "| `steps` | 11 | int64 | repeated |" in reference
    assert "| `READY` | 3 |" in reference
    assert (
        "| `Read` | stream [sample.Input](#sample-input) | stream [sample.Input](#sample-input) |"
        in reference
    )
    assert "_score" not in reference  # protoc's synthetic oneof is not a source choice.
    assert "**oneof `choice`:** Choose either a readable name or opaque data." in reference
    anchors = re.findall(r'<a id="([^"]+)"', reference)
    assert len(anchors) == len(set(anchors))
    assert set(re.findall(r"\]\(#([^)]*)\)", reference)) <= set(anchors)


def test_openapi_export_uses_real_routes_without_storage(monkeypatch):
    pytest.importorskip("fastapi")
    from reckon.viz import server

    def unexpected_storage():
        pytest.fail("Documentation export started debugger storage")

    monkeypatch.setattr(server, "create_storage", unexpected_storage)
    schema = json.loads(EXPORT["openapi_reference"](ROOT))
    assert schema == server.create_app().openapi()
    assert schema["openapi"] == "3.1.0"
    assert "/v1/runs/import" in schema["paths"]
    assert "/v1/runs/{run_id}/events" in schema["paths"]
    assert "/v1/stream" not in schema["paths"]  # WebSockets are not HTTP operations.


def test_openapi_rejects_missing_or_different_source(tmp_path):
    pytest.importorskip("fastapi")
    from reckon.viz import server

    assert server.create_app  # Reckon is importable and cached in this process.
    with pytest.raises(ValueError, match="Selected Reckon source is missing"):
        EXPORT["openapi_reference"](tmp_path)
    package = tmp_path / "src/reckon"
    (package / "viz").mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (package / "viz/server.py").write_text("raise AssertionError('Must not import this source')")
    with pytest.raises(ValueError, match="not from the selected Reckon source"):
        EXPORT["openapi_reference"](tmp_path)
