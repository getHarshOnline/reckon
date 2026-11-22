# Reckon laboratory repository guidance

Reckon is a library and laboratory for testing resource-limited memory, with a Rust record store, Python benchmarks and a run debugger. Start with the [overview](README.md) and [architecture map](ARCHITECTURE.md). Follow the shared working contract reached through the machine’s global agent entry. Read the accepted role, contract, stage, rights and release decisions supplied with the task. The laboratory runs locally; shared cases, evaluation services and decision records are planned. Every learned model, skill or policy promotion requires a curated shared case, Reckon’s evaluation and Harsh’s decision recorded by Reckon. Ordinary work and changes Harsh authors remain independent; Reckon’s absence holds new learned promotions. Ecosystem calls reach Reckon through Pale; native type dependencies establish compile-time wiring.

## Follow the component owner

| Work boundary | Read first |
| --- | --- |
| Environment and sibling dependency | [Getting started](README.md#getting-started), then `setup.sh` |
| Laboratory record model and generated descriptions | `kernel/src/record.rs` and [complete laboratory records](kernel/README.md#complete-laboratory-records) |
| Historical wire messages and RPC | `protos/reckon/*.proto` and `protos/buf.gen.yaml` |
| Rust kernel and Python extension | [Kernel](kernel/README.md) and `kernel/Cargo.toml` |
| Python API or memory manager | [Python library](src/reckon/README.md) and [memory manager](src/reckon/memory/README.md) |
| Notebook modes, adapters and optional dependencies | [Notebooks](notebooks/README.md) |
| Debugger and frontend packages | [Visualization UI](viz-ui/README.md) and `viz-ui/package.json` |
| Theory, metrics or vocabulary | [Manual index](docs/00-Index.md), [math core](docs/03-Math-Core.md) and [glossary](docs/13-Glossary.md) as relevant |

Read the changed component and its direct consumers. Follow the owning sources instead of treating this entry as a second setup or feature manual.

## Establish an environment when the task needs one

An authorised build or test task follows the [installation guide](docs/01a-Installation.md#set-up-the-environment), which selects its interpreter explicitly, or uses the optional `setup.sh` helper when the `python3` on the path is a supported interpreter. The helper is meant to be sourced. It creates `.venv` if it is missing, installs the declared `dev,viz` extras and attempts the Rust extension build; `--full` also installs the optional Gymnasium, MiniGrid and TextWorld environments, `--vscode` opts into editor configuration, and `--check` inspects the environment. Read `setup.sh` for its current effects before invoking it. The overview owns the source and interpreter requirements.

Setup can warn and continue after a failed extension build. Verify the required import before reporting an environment ready.

Activate the project environment for Python commands. `reckon._rust` is required; there is no pure-Python fallback. Run `maturin develop` after Rust changes when testing the Python extension: `cargo build` alone does not refresh that extension. The kernel guide owns build details. Dependency sources remain `pyproject.toml`, `kernel/Cargo.toml`, `viz-ui/package.json` and `protos/buf.gen.yaml`.

## Preserve the native contracts

- Edit the Rust laboratory model or the owning historical proto source, then use its configured generation route. Do not manually define or edit generated types.
- Keep the Rust extension required and preserve component boundaries.
- Update the closest README and relevant architecture/manual page when behavior or interfaces change. Use repository-relative references.
- Preserve unrelated worktree and stashed work.

## Verification commands

Choose the checks relevant to the changed boundary and report what ran. These are native invocations, not an instruction to build every component:

| Boundary | Existing invocation |
| --- | --- |
| Python tests | `pytest src/tests/` |
| Python lint | `pylint src/reckon/ --score=yes` with the retained 10.00 target |
| Python types | `pyright src/reckon/` with no errors |
| Rust checks | `cargo check` from the owning crate |
| Debugger build | `pnpm build` from `viz-ui/` |

By default, Cargo builds disable incremental compilation through `.cargo/config.toml`. Keep each working copy’s target directory separate: reusing one across copies can run stale binaries when Cargo considers their source timestamps unchanged.

Check pyright and cargo check before a code commit. Confirm the selected tool is available in the task's environment; this entry does not install it. The component guides own server, benchmark and notebook run commands.

Change this entry when repository structure, build entry points or top-level components change. Feature details stay with the component owner.

<!-- BEGIN shared repository rules -->

- Review a source file above 1,000 lines and split it by concern before 1,500.
- Keep Rust tests under `tests/`; keep Go's `_test.go` files beside their package.
- Finish a goal with the codebase the same size or smaller unless a requested feature requires growth. Preserve the behaviour, tests, cases and examples.
- Every engine must build from a fresh clone on Linux and macOS.
- Keep generated API reference and build output out of Git; change their source or generator.
- Write comments and API documentation for the code's reader. A crate or module comment first says what it is for in the system, what it builds on and what builds on it, then its purpose, inputs, results and useful edge cases, with the purpose written problem-first in the present tense: the problem it solves and what solves it today. One plain line after that opening says what is not built yet, as the problem now in front of it, and a negative appears only where a reader would expect the opposite: a limit stated as a property of what exists stays ("it runs on loopback with no caller authentication"), while a negative measured against the finished design is a hedge. Keep them self-contained, with links inside the repository.
- Push each repository as one commit whose whole message is `init`, with Harsh as author and committer under the account the folder uses and no `Co-Authored-By` or `Claude-Session` trailers; later commits stay short and plain.
- Describe the present design and research. The repository neither links nor ships lineage: earlier papers, predecessor versions, history tags and the commits behind them.
- Public repository files, including generated text, link within the repository or to public addresses their readers can open.
- A README is the repository's front door: it carries the product account for the technical reader who arrives there, opening with the product's plain name and the problem it solves, in the words its published pages use.
- Name every operation, command, tool, type, field and variable so a reader without its author's context can tell what it does, what it enables and when to use it; docstrings say the same. Keep full-field record schemas for the engine's consistency, named in plain words like everything else, and author each surface's schemas separately, one per intent, in its caller's terms: SDKs and APIs, the command line, the language server and the agent protocols (MCP, A2A, ACP) are different surfaces with different callers, and the agent protocols compose intents over the operations the others expose.
- Write each Markdown paragraph on one source line. Run the repository's formatter with `proseWrap: never` on changed Markdown.

<!-- END shared repository rules -->
