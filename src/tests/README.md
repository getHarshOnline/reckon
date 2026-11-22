# Run and extend the tests

<a id="reckon-test-suite"></a> <a id="purpose"></a>

Run the Python suite when changing the public API, retention behavior or Rust bindings. It checks core types, memory operations and their integration with the compiled extension.

<a id="test-requirements"></a>

## Prepare the environment

Complete [installation](../../docs/01a-Installation.md#set-up-the-environment), including the extension import check. Install the `dev` extra before running the suite. If you followed the wheel setup, run this from the repository root with the same environment active:

```bash
pip install -e ".[dev]"
```

After Rust changes, rebuild using the [kernel procedure](../../kernel/README.md#python-extension). An old installed extension can hide a source/binding mismatch.

For the generated wire messages and RPC tests, use Python 3.10+ and install `.[dev,proto]`. The [wire guide](../../protos/README.md) explains generation and the opt-in daemon check. The base suite stays usable on Python 3.9; missing optional protocol dependencies produce explicit skips.

<a id="running-tests"></a> <a id="all-tests"></a> <a id="specific-module"></a> <a id="with-coverage"></a> <a id="property-tests-only"></a>

## Run the suite

From the repository root, choose the scope you need:

:::code-group

```bash All tests
pytest src/tests/ -v
```

```bash Memory behavior
pytest src/tests/test_memory.py -v
```

```bash Property cases
pytest src/tests/test_properties.py -v
```

```bash Coverage report
pytest src/tests/ --cov=reckon --cov-report=html
```

:::

Pytest reports passing, failing and skipped cases. The coverage command also writes an HTML report. Inspect a failure against the source and extension revision actually loaded by that environment.

<a id="test-structure"></a> <a id="test-categories"></a>

<a id="unit-tests"></a> <a id="integration-tests"></a> <a id="property-based-tests"></a>

## Find the relevant tests

| File | What it exercises |
| --- | --- |
| `test_core.py` | Resource values, memory budgets and influence-relation types |
| `test_memory.py` | Records, manager operations and retention policies |
| `test_properties.py` | Generated numeric and resource inputs |
| `test_transitivity.py` | Diagnostics on supplied relation pairs |

The suite covers write/read/prune and logger integration. The relation tests diagnose supplied paths; they do not infer missing influence edges.

<a id="key-invariants-tested"></a>

<a id="writing-new-tests"></a> <a id="naming-convention"></a> <a id="fixtures"></a> <a id="property-test-pattern"></a>

## Add a regression case

Use `test_<module>.py` for a test file and `test_<feature>_<scenario>()` for a test function. Construct the task, budget and manager explicitly. The current core and memory tests create them in the test methods; there is no shared `conftest.py` supplying them.

For retention changes, include the incoming payload's cost and the expected records after the write. Test both byte and slot overflow when the change affects both. Verify that a record larger than `max_bytes` leaves existing records and logs unchanged. Token and operation-rate limits have separate cases; extend those cases when changing token admission, window expiry or episode resets. See [budget enforcement](../../docs/08-Causal-Memory-Manager-Design.md#budget-enforcement).

For relation diagnostics, distinguish an untested endpoint pair from a measured value below its threshold. Both can appear as a missing link in the report.

Use Hypothesis when varied inputs help explore the behavior. State the property for the operation under test, including which budget it checks.

<a id="further-reading"></a>

## Related guides

- [Architecture](../../ARCHITECTURE.md): component boundaries and build dependencies.
- [Memory API](../reckon/memory/README.md): record lifecycle and current enforcement.
- [Hypothesis](https://hypothesis.readthedocs.io/): strategies and property-based testing.
