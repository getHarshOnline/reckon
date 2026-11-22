# Build the API references

The Sphinx sources in this directory select the core and memory modules. Autodoc reads their actual signatures and docstrings, and Napoleon renders the existing argument and return descriptions. The authored [laboratory manual](../00-Index.md) keeps worked integrations, design reasoning and experiment limits; reference generation does not replace those explanations.

Use Python 3.11 or newer for Sphinx 8.2.3, with the selected Reckon checkout's dependencies and compiled extension available. Follow [installation](../01a-Installation.md) first, then install the pinned documentation dependency:

```bash
python -m pip install 'Sphinx==8.2.3'
```

The same dependency is declared by the `docs` extra. From the repository root, choose a new output directory and run:

```bash
python -m sphinx -W --keep-going -b json docs/reference build/reference-json
```

Use the selected environment's Python. Configuration puts this checkout's `src/` first and imports its real native extension for the version; a missing extension is a build failure, not a reason to mock the API. `-W` treats documentation warnings as errors. Use a fresh output directory when retaining an earlier build: the JSON builder refuses overwriting its copied environment file under the strict warning policy.

The navigation source is [index.rst](index.rst), followed by [core.rst](core.rst) and [memory.rst](memory.rst). Assembly consumes the complete JSON-builder directory as `sphinx-json`, including its page contexts, global/search contexts, object inventory and static companions. Keep the generated directory under ignored `build/`; commit docstrings, this configuration and navigation instead. Inspect the assembled reference's signatures, examples and links as a separate step from a successful Sphinx build.

Kernel API documentation belongs in Rust library comments, built with `cargo doc --manifest-path kernel/Cargo.toml --no-deps`. The separate daemon's crate comments belong in `daemon/src/main.rs`, built with `cargo doc --manifest-path daemon/Cargo.toml --no-deps`. Those outputs stay under their ignored target directories.

## Protocol and HTTP references

Install the `proto` and `viz` extras in the selected environment. The [reference exporter](../../tools/export_reference.py) compiles all `.proto` sources through the pinned `grpcio-tools` compiler and renders its descriptors as Markdown. It preserves qualified type names, field numbers, map types, explicit optional presence, oneof membership, enum values, RPC streaming directions and source comments. Laboratory messages in `reckon` and daemon messages in `reckon.core.v1` remain separate. The exporter does not regenerate Python or TypeScript bindings.

```bash
python tools/export_reference.py protobuf --output build/protobuf-reference/index.md
python tools/export_reference.py openapi --output build/debugger-openapi.json
```

The HTTP export requires the selected checkout's package, server and compiled extension. It refuses missing source or Reckon modules loaded from another checkout or installation, then calls the actual `create_app().openapi()` without entering the application's lifespan, so it starts no storage, fixtures, event workers or listening server. The schema covers HTTP routes; WebSocket messages remain in the [debugger guide](../../src/reckon/viz/README.md). A schema declaration does not prove an endpoint works or that a daemon RPC is implemented: `Probe` and the daemon's event, metrics and archive export attachments remain unsupported as described in the [daemon guide](../../daemon/README.md).

For assembly, run the same exporter over the captured repository with `--source <input-root>` and a new output file. Select the Markdown file as `markdown`, and the JSON file as `openapi-json`. Select both the compiler and debugger dependencies in the generator environment; `--version` reports their installed versions. Existing outputs are refused. Keep generated files under ignored `build/` and reuse a completed artifact when only its assembly changes. The provider build and rendered reading experience still need their own checks.
