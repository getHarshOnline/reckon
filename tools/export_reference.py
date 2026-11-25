"""Export the debugger HTTP schema or compile protocol reference Markdown."""

import argparse
import html
from importlib import import_module
from importlib.metadata import version
import json
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory

from google.protobuf import descriptor_pb2


def cell(value: str) -> str:
    """Keep source comments readable without turning them into table markup."""
    return html.escape(value.strip(), quote=False).replace("|", "&#124;").replace("\n", "<br>")


def anchor(name):
    """Give qualified source names stable, distinct fragment addresses."""
    return name.lstrip(".").lower().replace(".", "-")


def link(name):
    """Link a type to its qualified declaration."""
    return f"[{name.lstrip('.')}](#{anchor(name)})"


def comments(location):
    """Retain comment prose without the source's decorative rulers."""
    if location is None:
        return ""
    parts = [
        *location.leading_detached_comments,
        location.leading_comments,
        location.trailing_comments,
    ]
    prose = (
        "\n".join(line for line in part.splitlines() if not re.fullmatch(r"\s*={3,}\s*", line)).strip()
        for part in parts
    )
    return "\n".join(part for part in prose if part)


def collect(items, prefix):
    """Index nested declarations, including the compiler's map entry types."""
    for item in items:
        name = f"{prefix}.{item.name}"
        yield name, item
        if hasattr(item, "nested_type"):
            yield from collect(item.nested_type, name)
            yield from collect(item.enum_type, name)


def field_type(field, declarations):
    """Render map syntax while linking ordinary message and enum types."""
    if field.type_name:
        item = declarations[field.type_name.lstrip(".")]
        if hasattr(item, "field") and item.options.map_entry:
            key, value = (field_type(part, declarations) for part in item.field)
            return f"map&lt;{key}, {value}&gt;"
        return link(field.type_name)
    # Protobuf constructs these classes dynamically from its bundled descriptor.
    # pylint: disable=no-member
    return descriptor_pb2.FieldDescriptorProto.Type.Name(field.type).removeprefix("TYPE_").lower()
    # pylint: enable=no-member


def presence(field, message, declarations):
    """Distinguish source optional fields from protoc's synthetic oneofs."""
    if field.proto3_optional:
        return "optional"
    if field.HasField("oneof_index"):
        return f"oneof `{message.oneof_decl[field.oneof_index].name}`"
    if field.label == field.LABEL_REPEATED:
        return "map" if "map&lt;" in field_type(field, declarations) else "repeated"
    if field.type == field.TYPE_MESSAGE:
        return "message presence"
    return "implicit"


def message_rows(item, path, locations, declarations):
    """Render the field numbers and presence rules used by a wire decoder."""
    yield "| Field | Number | Type | Presence | Description |"
    yield "| --- | --- | --- | --- | --- |"
    for i, field in enumerate(item.field):
        description = cell(comments(locations.get((*path, 2, i))))
        yield (
            f"| `{field.name}` | {field.number} | {field_type(field, declarations)} | "
            f"{presence(field, item, declarations)} | {description} |"
        )


def enum_rows(item, path, locations):
    """Retain numeric enum values and their source comments."""
    yield "| Value | Number | Description |"
    yield "| --- | --- | --- |"
    for i, value in enumerate(item.value):
        yield (
            f"| `{value.name}` | {value.number} | "
            f"{cell(comments(locations.get((*path, 2, i))))} |"
        )


def service_rows(item, path, locations):
    """Retain request and response types, including streaming direction."""
    yield "| Method | Request | Response | Description |"
    yield "| --- | --- | --- | --- |"
    for i, method in enumerate(item.method):
        request = ("stream " if method.client_streaming else "") + link(method.input_type)
        response = ("stream " if method.server_streaming else "") + link(method.output_type)
        yield (
            f"| `{method.name}` | {request} | {response} | "
            f"{cell(comments(locations.get((*path, 2, i))))} |"
        )


def section(item, name, path, locations, declarations):
    """Render one declared message, enum or service and its nested types."""
    yield from [
        f'<a id="{anchor(name)}"></a>',
        "",
        f"### {name}",
        "",
        cell(comments(locations.get(path))),
        "",
    ]
    if hasattr(item, "field"):
        for i, group in enumerate(item.oneof_decl):
            description = comments(locations.get((*path, 8, i)))
            if description:
                yield f"**oneof `{group.name}`:** {cell(description)}"
                yield ""
        yield from message_rows(item, path, locations, declarations)
        yield ""
        for i, child in enumerate(item.nested_type):
            if not child.options.map_entry:
                yield from section(
                    child, f"{name}.{child.name}", (*path, 3, i), locations, declarations
                )
        for i, child in enumerate(item.enum_type):
            yield from section(
                child, f"{name}.{child.name}", (*path, 4, i), locations, declarations
            )
    elif hasattr(item, "value"):
        yield from enum_rows(item, path, locations)
    else:
        yield from service_rows(item, path, locations)
    yield ""


def compile_protocols(source):
    """Use protoc's descriptors and source locations, never a second proto parser."""
    proto_root = source / "protos"
    sources = sorted(proto_root.rglob("*.proto"))
    if not sources:
        raise ValueError("No protocol sources found")
    with TemporaryDirectory(prefix="reckon-reference-") as temporary:
        descriptor = Path(temporary) / "protocol.pb"
        subprocess.run(
            [
                sys.executable,
                "-m",
                "grpc_tools.protoc",
                f"-I{proto_root}",
                "--include_source_info",
                "--include_imports",
                f"--descriptor_set_out={descriptor}",
                *map(str, sources),
            ],
            check=True,
        )
        # pylint: disable=no-member
        return descriptor_pb2.FileDescriptorSet.FromString(descriptor.read_bytes())
        # pylint: enable=no-member


def protobuf_reference(source: Path) -> str:
    """Compile the selected schemas into a connected Markdown reference."""
    schema = compile_protocols(source)
    declarations = {}
    for file in schema.file:
        if file.syntax != "proto3":
            raise ValueError(f"Only proto3 reference is supported: {file.name}")
        for items in (file.message_type, file.enum_type, file.service):
            declarations.update(collect(items, file.package))
    output = [
        "# Reckon protocol reference",
        "",
        "Compiled from the protocol sources. Field numbers, explicit optional presence, "
        "oneof membership and map types are part of the wire contract. A declared RPC "
        "does not establish its implementation; the daemon guide describes supported calls.",
        "",
    ]
    for file in schema.file:
        output.append(f"- [{file.name}](#{anchor(file.name.replace('/', '.'))})")
    output.append("")
    for file in schema.file:
        locations = {tuple(loc.path): loc for loc in file.source_code_info.location}
        output.extend(
            [
                f'<a id="{anchor(file.name.replace("/", "."))}"></a>',
                "",
                f"## {file.name}",
                "",
                f"Package: `{file.package}`. Syntax: `{file.syntax}`.",
                "",
                cell(comments(locations.get((12,)))),
                "",
            ]
        )
        for field, items in ((4, file.message_type), (5, file.enum_type), (6, file.service)):
            for i, item in enumerate(items):
                output.extend(
                    section(
                        item, f"{file.package}.{item.name}", (field, i), locations, declarations
                    )
                )
    return "\n".join(output).rstrip() + "\n"


def check_import_origins(package_root: Path) -> None:
    """Refuse cached or imported Reckon modules from another checkout or installation."""
    for name, module in tuple(sys.modules.items()):
        if name != "reckon" and not name.startswith("reckon."):
            continue
        origin = getattr(module, "__file__", None)
        if origin is None or not Path(origin).resolve().is_relative_to(package_root):
            raise ValueError(f"Module {name} is not from the selected Reckon source")


def openapi_reference(source: Path) -> str:
    """Read the real app's routes without starting its storage or event workers."""
    package_root = (source / "src/reckon").resolve()
    for relative in ("__init__.py", "viz/server.py"):
        if not (package_root / relative).is_file():
            raise ValueError(f"Selected Reckon source is missing {relative}")
    check_import_origins(package_root)
    sys.path.insert(0, str(package_root.parent))
    server = import_module("reckon.viz.server")
    check_import_origins(package_root)
    return json.dumps(server.create_app().openapi(), indent=2, sort_keys=True) + "\n"


def main() -> None:
    """Export one new artifact from the selected checkout or captured source."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--version",
        action="version",
        version="Reckon reference exporter 1; "
        + "; ".join(
            f"{package} {version(package)}"
            for package in ("grpcio-tools", "protobuf", "fastapi", "pydantic")
        ),
    )
    parser.add_argument("kind", choices=("protobuf", "openapi"))
    parser.add_argument(
        "--source",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Selected checkout or captured repository root",
    )
    parser.add_argument("--output", type=Path, required=True, help="New output file")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output already exists; choose a new file")
    export = protobuf_reference if args.kind == "protobuf" else openapi_reference
    content = export(args.source.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        handle.write(content)


if __name__ == "__main__":
    main()
