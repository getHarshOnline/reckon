"""Check every optional wire field against the independent protobuf runtime."""

import importlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

pytest.importorskip("betterproto2", reason="Install the proto extra on Python 3.10+.")
pytest.importorskip("grpc_tools", reason="Install the proto extra to compile the schema oracle.")
from google.protobuf import descriptor_pb2, descriptor_pool, message_factory


def generated_type(name):
    package, type_name = name.lstrip(".").rsplit(".", 1)
    return getattr(importlib.import_module("reckon.generated." + package), type_name)


def optional_values(field):
    if field.type == field.TYPE_MESSAGE:
        return [None, generated_type(field.type_name)()]
    if field.type == field.TYPE_ENUM:
        enum = generated_type(field.type_name)
        return [None, enum(0), enum(1)]
    if field.type == field.TYPE_STRING:
        return [None, "", "record-1"]
    if field.type == field.TYPE_BYTES:
        return [None, b"", b"\x00test"]
    if field.type in (field.TYPE_DOUBLE, field.TYPE_FLOAT):
        return [None, 0.0, -0.25]
    return [None, 0, 7]


def test_all_optional_fields_preserve_presence(tmp_path):
    root = Path(__file__).resolve().parents[2] / "protos"
    descriptor_path = tmp_path / "schema.pb"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "grpc_tools.protoc",
            f"-I{root}",
            "--include_imports",
            f"--descriptor_set_out={descriptor_path}",
            *map(str, sorted((root / "reckon").rglob("*.proto"))),
        ],
        check=True,
    )
    schema = descriptor_pb2.FileDescriptorSet.FromString(descriptor_path.read_bytes())
    pool = descriptor_pool.DescriptorPool()
    for source in schema.file:
        pool.Add(source)
    cases = 0
    for source in schema.file:
        for message in source.message_type:
            name = source.package + "." + message.name
            cls = generated_type(name)
            oracle_cls = message_factory.GetMessageClass(pool.FindMessageTypeByName(name))
            for field in message.field:
                if not field.proto3_optional:
                    continue
                for value in optional_values(field):
                    label = (name, field.name, value)
                    original = cls(**{field.name: value})
                    wire = bytes(original)
                    oracle = oracle_cls.FromString(wire)
                    assert oracle.HasField(field.name) == (value is not None), label
                    assert getattr(cls.parse(wire), field.name) == value, label
                    document = original.to_json()
                    assert (field.json_name in json.loads(document)) == (value is not None), label
                    assert getattr(cls.from_json(document), field.name) == value, label
                    cases += 1
    assert cases > 0, "The descriptor walk must reach the actual optional fields."
