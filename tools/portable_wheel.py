#!/usr/bin/env python3
"""Prepare portable Cargo SBOM references without changing a wheel's payload.

The input wheel is retained. This changes identifiers, not component rights or
dependency coverage. SBOM portability and whole-wheel path checks are separate.
"""

from __future__ import annotations

import argparse
import base64
import copy
import csv
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import sys
from typing import Any
from urllib.parse import parse_qsl, unquote, urlsplit
import zipfile

LOCAL_PATH = re.compile(
    r"(?<![\w-])file:|(?<![\w.])/(?:Users|home|tmp|private/var|var/folders)/|(?<!\w)[A-Za-z]:[\\/]",
    re.IGNORECASE,
)
SOURCE_DIRECTORY = "reckon:source:directory"
SOURCE_PATH = "reckon:source:path"


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def read_json(data):
    def reject_constant(value):
        raise ValueError(f"invalid JSON constant: {value}")

    return json.loads(data, object_pairs_hook=unique_object, parse_constant=reject_constant)


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, child in value.items():
            yield key
            yield from strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from strings(child)


def has_signature_field(value):
    """CycloneDX 1.5 envelopes use a signature field, not a component name."""
    if isinstance(value, dict):
        return "signature" in value or any(has_signature_field(child) for child in value.values())
    if isinstance(value, list):
        return any(has_signature_field(child) for child in value)
    return False


def has_local_path(value, source_root=None):
    for _ in range(3):
        if LOCAL_PATH.search(value) or (source_root and str(source_root) in value):
            return True
        decoded = unquote(value)
        if decoded == value:
            break
        value = decoded
    return False


def components(bom):
    def descend(items):
        for item in items:
            yield item
            yield from descend(item.get("components", []))

    root = bom.get("metadata", {}).get("component")
    yield from descend(([root] if root else []) + bom.get("components", []))


def validate_bom(bom, portable=False, source_root=None):
    if (
        not isinstance(bom, dict)
        or bom.get("bomFormat") != "CycloneDX"
        or bom.get("specVersion") != "1.5"
    ):
        raise ValueError("expected a CycloneDX 1.5 SBOM")
    if type(bom.get("version", 1)) is not int or bom.get("version", 1) < 1:
        raise ValueError("invalid SBOM version")
    if has_signature_field(bom):
        raise ValueError("signed SBOMs cannot be rewritten")
    refs = [item.get("bom-ref") for item in components(bom)]
    if not refs or any(not isinstance(ref, str) or not ref for ref in refs):
        raise ValueError("every component must have a nonempty bom-ref")
    if len(refs) != len(set(refs)):
        raise ValueError("duplicate component reference")
    defined = set(refs)
    for dependency in bom.get("dependencies", []):
        used = [
            dependency["ref"],
            *dependency.get("dependsOn", []),
            *dependency.get("provides", []),
        ]
        if any(ref not in defined for ref in used):
            raise ValueError("unresolved dependency reference")
    for composition in bom.get("compositions", []):
        if any(
            ref not in defined
            for key in ("assemblies", "dependencies")
            for ref in composition.get(key, [])
        ):
            raise ValueError("unresolved composition reference")
    if portable and any(has_local_path(value, source_root) for value in strings(bom)):
        raise ValueError("SBOM still contains a local path or file URL")


def local_component(ref, source_root):
    base, marker, target = ref.partition(" bin-target-")
    if marker and not target.isdigit():
        raise ValueError("unrecognised Cargo target reference")
    location = urlsplit(base.removeprefix("path+"))
    if location.scheme != "file" or location.netloc or not location.fragment:
        raise ValueError("unrecognised local Cargo reference")
    directory = Path(unquote(location.path))
    if not directory.is_absolute():
        raise ValueError("local Cargo reference must name an absolute source directory")
    try:
        relative = directory.resolve().relative_to(source_root)
    except ValueError as error:
        raise ValueError("local source is outside the explicit repository root") from error
    identifier = f"local:{relative.as_posix()}#{location.fragment}"
    if marker:
        identifier += f"/target/{target}"
    return directory, relative.as_posix(), identifier


def add_property(component, name, value):
    properties = component.setdefault("properties", [])
    previous = [item["value"] for item in properties if item["name"] == name]
    if previous and previous != [value]:
        raise ValueError(f"conflicting source property: {name}")
    if not previous:
        properties.append({"name": name, "value": value})


def preserve_local_source(component, directory, relative, root_directory):
    purl = component.get("purl")
    add_property(component, SOURCE_DIRECTORY, relative)
    if purl is None:
        return
    parsed = urlsplit(purl)
    qualifiers = parse_qsl(parsed.query, keep_blank_values=True)
    if len(qualifiers) != 1 or qualifiers[0][0] != "download_url":
        raise ValueError("unaccounted qualifiers on local source PURL")
    download = qualifiers[0][1]
    if (
        not download.startswith("file://")
        or parsed.scheme != "pkg"
        or not parsed.path.startswith("cargo/")
    ):
        raise ValueError("local source PURL is not a Cargo file location")
    source = Path(unquote(download[len("file://") :]))
    if not source.is_absolute():
        source = root_directory / source
    if source.resolve() != directory.resolve():
        raise ValueError("local PURL disagrees with its component source directory")
    add_property(component, "reckon:source:package", unquote(parsed.path))
    if parsed.fragment:
        subpath = PurePosixPath(unquote(parsed.fragment))
        if subpath.is_absolute() or ".." in subpath.parts or "\\" in str(subpath):
            raise ValueError("unconfined target source path")
        add_property(component, SOURCE_PATH, (PurePosixPath(relative) / subpath).as_posix())
    del component["purl"]


def normalize_bom(original, source_root):
    """Remap known local Cargo identities through one bijection, retaining data."""
    validate_bom(original)
    bom = copy.deepcopy(original)
    items = list(components(bom))
    local = {}
    for component in items:
        ref = component["bom-ref"]
        if ref.startswith("path+file:"):
            local[ref] = local_component(ref, source_root)
    root_ref = bom.get("metadata", {}).get("component", {}).get("bom-ref")
    if local and root_ref not in local:
        raise ValueError("local sources require the root Cargo component's directory")
    root_directory = local[root_ref][0] if local else source_root
    mapping = {ref: value[2] for ref, value in local.items()}
    final_refs = [mapping.get(item["bom-ref"], item["bom-ref"]) for item in items]
    if len(set(final_refs)) != len(final_refs):
        raise ValueError("portable component reference collision")
    for component in items:
        ref = component["bom-ref"]
        if ref in local:
            directory, relative, _ = local[ref]
            preserve_local_source(component, directory, relative, root_directory)

    def replace(value: Any) -> Any:
        if isinstance(value, dict):
            return {key: replace(child) for key, child in value.items()}
        if isinstance(value, list):
            return [replace(child) for child in value]
        if isinstance(value, str):
            return mapping.get(value, value)
        return value

    bom = replace(bom)
    if bom != original:
        bom["version"] = bom.get("version", 1) + 1
    validate_bom(bom, portable=True, source_root=source_root)
    return bom


def digest(data, algorithm="sha256"):
    if algorithm not in {"sha256", "sha384", "sha512"}:
        raise ValueError("unsupported wheel RECORD hash")
    encoded = base64.urlsafe_b64encode(hashlib.new(algorithm, data).digest()).rstrip(b"=")
    return algorithm + "=" + encoded.decode("ascii")


def read_wheel(path):
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        names = [item.filename for item in infos]
        if len(names) != len(set(names)):
            raise ValueError("duplicate wheel member")
        for item in infos:
            member = PurePosixPath(item.filename)
            if (
                item.is_dir()
                or member.is_absolute()
                or ".." in member.parts
                or "\\" in item.filename
                or str(member) != item.filename
            ):
                raise ValueError("unconfined or unsupported wheel member")
            if (item.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError("wheel contains a symbolic link")
        if any(name.endswith(("/RECORD.jws", "/RECORD.p7s")) for name in names):
            raise ValueError("signed wheels cannot be rewritten")
        records = [name for name in names if name.endswith(".dist-info/RECORD")]
        if len(records) != 1:
            raise ValueError("expected one wheel RECORD")
        record = records[0]
        data = {name: archive.read(name) for name in names}
    rows = list(csv.reader(io.StringIO(data[record].decode("utf-8"))))
    if any(len(row) != 3 for row in rows):
        raise ValueError("malformed wheel RECORD")
    if len(rows) != len(data) or {row[0] for row in rows} != set(data):
        raise ValueError("wheel RECORD does not cover each member exactly once")
    for name, checksum, size in rows:
        if name == record:
            if checksum or size:
                raise ValueError("wheel RECORD must not hash itself")
        elif (
            not checksum
            or digest(data[name], checksum.split("=", 1)[0]) != checksum
            or str(len(data[name])) != size
        ):
            raise ValueError(f"wheel RECORD mismatch: {name}")
    sboms = [name for name in names if name.startswith(record.removesuffix("RECORD") + "sboms/")]
    if not sboms:
        raise ValueError("wheel has no SBOM; use an SBOM-enabled build")
    return infos, data, record, sboms


def check_wheel(path, source_root=None, all_members=False):
    """Check SBOM structure/paths and RECORD; optionally scan every payload."""
    _, data, _, sboms = read_wheel(path)
    for name in sboms:
        validate_bom(read_json(data[name]), portable=True, source_root=source_root)
    if all_members:
        leaking = [
            name
            for name, raw in data.items()
            if has_local_path(raw.decode("utf-8", errors="replace"), source_root)
        ]
        if leaking:
            raise ValueError("local paths remain in wheel members: " + ", ".join(leaking))


def prepare_wheel(path, output, source_root):
    source_root = source_root.resolve(strict=True)
    if not source_root.is_dir():
        raise ValueError("source root must be a repository directory")
    if path.resolve() == output.resolve() or output.exists():
        raise ValueError("output must be a new path; the input is never overwritten")
    if output.name != path.name:
        raise ValueError("output must preserve the wheel filename in a separate directory")
    infos, data, record, sboms = read_wheel(path)
    for name in sboms:
        original = read_json(data[name])
        normalized = normalize_bom(original, source_root)
        if normalized != original:
            data[name] = (json.dumps(normalized, indent=2, ensure_ascii=False) + "\n").encode()
    rows = io.StringIO(newline="")
    writer = csv.writer(rows, lineterminator="\n")
    for info in infos:
        name = info.filename
        writer.writerow(
            [
                name,
                "" if name == record else digest(data[name]),
                "" if name == record else len(data[name]),
            ]
        )
    data[record] = rows.getvalue().encode("utf-8")
    prepared = io.BytesIO()
    with zipfile.ZipFile(prepared, "w") as archive:
        for info in infos:
            archive.writestr(copy.copy(info), data[info.filename])
    check_wheel(io.BytesIO(prepared.getvalue()), source_root)
    with output.open("xb") as stream:
        stream.write(prepared.getvalue())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare", help="prepare SBOMs in a separate unsigned wheel")
    prepare.add_argument("wheel", type=Path)
    prepare.add_argument("--source-root", type=Path, required=True)
    prepare.add_argument("--output", type=Path, required=True)
    check = commands.add_parser("check", help="check SBOM portability and wheel RECORD")
    check.add_argument("wheel", type=Path)
    check.add_argument("--source-root", type=Path)
    check.add_argument(
        "--all-members", action="store_true", help="also scan native and other payloads"
    )
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            prepare_wheel(args.wheel, args.output, args.source_root)
            print("Prepared portable SBOMs; native and other payload bytes are unchanged.")
        else:
            root = args.source_root.resolve() if args.source_root else None
            check_wheel(args.wheel, root, args.all_members)
            print(
                "SBOM and RECORD checks passed."
                if not args.all_members
                else "SBOM, RECORD and whole-wheel path checks passed."
            )
    except (ValueError, OSError, KeyError, TypeError, zipfile.BadZipFile) as error:
        print(f"Wheel check failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
