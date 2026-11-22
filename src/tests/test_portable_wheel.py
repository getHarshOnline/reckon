"""An SBOM rewrite preserves the wheel and refuses gaps in its source graph."""

import base64
import copy
import csv
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import zipfile

import pytest


@pytest.fixture
def portable():
    path = Path(__file__).resolve().parents[2] / "tools/portable_wheel.py"
    if not path.exists():
        pytest.skip("Wheel preparation requires the complete checkout")
    spec = importlib.util.spec_from_file_location("portable_wheel", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def source(tmp_path):
    root = tmp_path / "source"
    (root / "kernel").mkdir(parents=True)
    return root


@pytest.fixture
def bom(source):
    ref = f"path+{(source / 'kernel').as_uri()}#reckon-kernel@0.1.0"
    target = ref + " bin-target-0"
    dependency = "registry+https://github.com/rust-lang/crates.io-index#example@1.2.3"
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "serialNumber": "urn:uuid:4163a51b-569f-4d3a-a0dc-0a012e0d2356",
        "metadata": {
            "component": {
                "type": "library",
                "name": "reckon-kernel",
                "version": "0.1.0",
                "bom-ref": ref,
                "licenses": [{"expression": "Apache-2.0"}],
                "purl": "pkg:cargo/reckon-kernel@0.1.0?download_url=file://.",
                "components": [
                    {
                        "type": "library",
                        "name": "reckon_kernel",
                        "version": "0.1.0",
                        "bom-ref": target,
                        "purl": "pkg:cargo/reckon-kernel@0.1.0?download_url=file://.#src/lib.rs",
                    }
                ],
            },
            "properties": [{"name": "cdx:rustc:sbom:target:all_targets", "value": "true"}],
        },
        "components": [
            {
                "type": "library",
                "name": "example",
                "version": "1.2.3",
                "bom-ref": dependency,
                "purl": "pkg:cargo/example@1.2.3",
                "scope": "excluded",
                "licenses": [{"expression": "MIT OR Apache-2.0"}],
                "hashes": [{"alg": "SHA-256", "content": "a" * 64}],
            }
        ],
        "dependencies": [
            {"ref": ref, "dependsOn": [dependency]},
            {"ref": target, "dependsOn": [dependency]},
            {"ref": dependency, "dependsOn": []},
        ],
        "compositions": [{"aggregate": "complete", "assemblies": [ref, target]}],
    }


DIST = "reckon-0.1.0.dist-info/"
SBOM = DIST + "sboms/reckon-kernel.cyclonedx.json"
RECORD = DIST + "RECORD"
FILENAME = "reckon-0.1.0-cp39-abi3-macosx_11_0_arm64.whl"


def checksum(data):
    return "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()


def make_wheel(path, bom, extra=None):
    members = {
        "reckon/_rust.abi3.so": b"native fixture\x00/Users/builder/.cargo/source.rs\x00",
        DIST + "METADATA": b"Name: reckon\nVersion: 0.1.0\nLicense: Apache-2.0\n",
        DIST + "licenses/LICENSE": b"retained licence text\n",
        DIST + "WHEEL": b"Wheel-Version: 1.0\nGenerator: fixture\n",
    }
    if bom is not None:
        members[SBOM] = json.dumps(bom).encode()
    members.update(extra or {})
    rows = io.StringIO(newline="")
    writer = csv.writer(rows)
    for name, data in members.items():
        writer.writerow([name, checksum(data), len(data)])
    writer.writerow([RECORD, "", ""])
    members[RECORD] = rows.getvalue().encode()
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return members


def test_prepare_preserves_payload_coverage_licences_and_graph(portable, source, bom, tmp_path):
    original = copy.deepcopy(bom)
    wheel = tmp_path / FILENAME
    before_members = make_wheel(wheel, bom)
    before = wheel.read_bytes()
    output = tmp_path / "prepared" / FILENAME
    output.parent.mkdir()
    portable.prepare_wheel(wheel, output, source)
    assert wheel.read_bytes() == before
    with zipfile.ZipFile(output) as archive:
        after = {name: archive.read(name) for name in archive.namelist()}
    assert set(after) == set(before_members)
    assert all(
        after[name] == data for name, data in before_members.items() if name not in {SBOM, RECORD}
    )
    result = json.loads(after[SBOM])
    assert bom == original
    root = result["metadata"]["component"]
    assert root["licenses"] == bom["metadata"]["component"]["licenses"]
    assert result["components"] == bom["components"]
    assert result["metadata"]["properties"] == bom["metadata"]["properties"]
    assert root["bom-ref"] == "local:kernel#reckon-kernel@0.1.0"
    target = root["components"][0]
    assert target["bom-ref"] == root["bom-ref"] + "/target/0"
    assert "purl" not in root and "purl" not in target
    assert {p["name"]: p["value"] for p in target["properties"]} == {
        "reckon:source:directory": "kernel",
        "reckon:source:package": "cargo/reckon-kernel@0.1.0",
        "reckon:source:path": "kernel/src/lib.rs",
    }
    assert result["dependencies"] == [
        {"ref": root["bom-ref"], "dependsOn": [result["components"][0]["bom-ref"]]},
        {"ref": target["bom-ref"], "dependsOn": [result["components"][0]["bom-ref"]]},
        bom["dependencies"][2],
    ]
    assert result["compositions"][0]["assemblies"] == [root["bom-ref"], target["bom-ref"]]
    assert result["version"] == 2 and result["serialNumber"] == bom["serialNumber"]
    assert portable.normalize_bom(result, source) == result
    for name, hashed, size in csv.reader(io.StringIO(after[RECORD].decode())):
        assert (hashed, size) == (
            ("", "") if name == RECORD else (checksum(after[name]), str(len(after[name])))
        )
    portable.check_wheel(output, source)
    with pytest.raises(ValueError, match="local paths remain.*_rust"):
        portable.check_wheel(output, source, all_members=True)


def test_mapping_is_independent_of_checkout_location(portable, source, bom, tmp_path):
    other = tmp_path / "another checkout"
    (other / "kernel").mkdir(parents=True)
    relocated = json.loads(json.dumps(bom).replace(source.as_uri(), other.as_uri()))
    assert portable.normalize_bom(bom, source) == portable.normalize_bom(relocated, other)


@pytest.mark.parametrize("name", ["signature", "signatures"])
def test_unsigned_signature_named_components_are_preserved(portable, source, bom, name):
    component = bom["components"][0]
    component["name"] = name
    component["properties"] = [{"name": "signature", "value": "signatures"}]
    result = portable.normalize_bom(bom, source)
    assert result["components"][0] == component


@pytest.mark.parametrize("location", ["bom", "component", "nested-component", "composition"])
def test_actual_signature_objects_are_refused(portable, source, bom, location):
    owner = {
        "bom": bom,
        "component": bom["components"][0],
        "nested-component": bom["metadata"]["component"]["components"][0],
        "composition": bom["compositions"][0],
    }[location]
    owner["signature"] = {"algorithm": "RS256", "value": "signed-bytes"}
    with pytest.raises(ValueError, match="signed SBOM"):
        portable.normalize_bom(bom, source)


@pytest.mark.parametrize(
    "failure",
    [
        "outside",
        "duplicate",
        "collision",
        "missing-edge",
        "purl-source",
        "target-escape",
        "signature",
        "hidden-path",
    ],
)
def test_unresolved_identity_or_source_is_refused(portable, source, bom, failure):
    root = bom["metadata"]["component"]
    if failure == "outside":
        old = root["bom-ref"]
        changed = old.replace((source / "kernel").as_uri(), source.parent.as_uri())
        bom = json.loads(json.dumps(bom).replace(old, changed))
    elif failure == "duplicate":
        bom["components"].append(copy.deepcopy(bom["components"][0]))
    elif failure == "collision":
        bom["components"].append(
            {"type": "library", "name": "collision", "bom-ref": "local:kernel#reckon-kernel@0.1.0"}
        )
    elif failure == "missing-edge":
        bom["dependencies"][0]["dependsOn"].append("absent-component")
    elif failure == "purl-source":
        root["purl"] = root["purl"].replace("file://.", "file://../other")
    elif failure == "target-escape":
        root["components"][0]["purl"] += "/../../escape.rs"
    elif failure == "signature":
        bom["signature"] = {"value": "must not invalidate"}
    else:
        root["description"] = "file%253A%252F%252F%252FUsers%252Fbuilder%252Fprivate"
    with pytest.raises(ValueError):
        portable.normalize_bom(bom, source)


@pytest.mark.parametrize(
    "failure",
    ["missing-sbom", "signature", "traversal", "duplicate", "record-drift", "existing-output"],
)
def test_bad_wheel_leaves_input_and_destination_untouched(portable, source, bom, tmp_path, failure):
    wheel = tmp_path / FILENAME
    extra = {}
    if failure == "signature":
        extra[DIST + "RECORD.jws"] = b"signed"
    if failure == "traversal":
        extra["../outside"] = b"bad member"
    make_wheel(wheel, None if failure == "missing-sbom" else bom, extra)
    if failure in {"duplicate", "record-drift"}:
        with zipfile.ZipFile(wheel, "a") as archive:
            if failure == "duplicate":
                with pytest.warns(UserWarning, match="Duplicate name"):
                    archive.writestr(SBOM, json.dumps(bom))
            else:
                archive.writestr("unrecorded", b"not in RECORD")
    before = wheel.read_bytes()
    output = tmp_path / "prepared" / FILENAME
    output.parent.mkdir()
    if failure == "existing-output":
        output.write_bytes(b"keep this")
    with pytest.raises(ValueError):
        portable.prepare_wheel(wheel, output, source)
    assert wheel.read_bytes() == before
    assert output.read_bytes() == b"keep this" if output.exists() else failure != "existing-output"


def test_in_place_and_duplicate_json_are_refused(portable, source, bom, tmp_path):
    wheel = tmp_path / FILENAME
    make_wheel(wheel, bom)
    with pytest.raises(ValueError, match="never overwritten"):
        portable.prepare_wheel(wheel, wheel, source)
    with pytest.raises(ValueError, match="duplicate JSON"):
        portable.read_json(b'{"version":1,"version":2}')


@pytest.mark.parametrize(
    "value",
    [
        "https://example.org/source",
        "pkg:cargo/example@1.0",
        "local:kernel#reckon-kernel@0.1.0",
        "License-File: LICENSE",
        "Build profile: release",
    ],
)
def test_public_and_relative_identifiers_are_not_machine_paths(portable, value):
    assert not portable.has_local_path(value)


@pytest.mark.parametrize(
    "value",
    [
        "C:\\Users\\builder\\source",
        "D:/build/source",
        "/home/builder/source",
        "file%253A%252F%252Fprivate",
    ],
)
def test_path_check_catches_encoded_and_windows_paths(portable, value):
    assert portable.has_local_path(value)


def test_cli_reports_only_the_check_it_performs(portable, source, bom, tmp_path, capsys):
    wheel = tmp_path / FILENAME
    make_wheel(wheel, bom)
    output = tmp_path / "prepared" / FILENAME
    output.parent.mkdir()
    assert (
        portable.main(
            ["prepare", str(wheel), "--source-root", str(source), "--output", str(output)]
        )
        == 0
    )
    assert "native and other payload bytes are unchanged" in capsys.readouterr().out
    assert portable.main(["check", str(output)]) == 0
    assert capsys.readouterr().out.strip() == "SBOM and RECORD checks passed."
    assert portable.main(["check", str(output), "--all-members"]) == 1
    assert "local paths remain" in capsys.readouterr().err
