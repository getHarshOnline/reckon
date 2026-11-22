# Export observations from a local run

The daemon keeps a shared in-memory record store and a separate, bounded account of each named run's observations. Supply `run_id` on `Write` and `Retrieve` from the first operation that belongs to a run. IDs contain 1–128 ASCII letters, digits, dots, underscores or hyphens. An empty ID keeps the operation unattributed; supplying a name later cannot recover its earlier history. A successful named retrieval can establish an empty run.

Reusing an episode context requires the same run ID, including whether it was omitted. `Observe` obtains its run from that context. A mismatched context is refused before retrieval, access counts or attribution change. Run identity distinguishes observations; it is not caller authentication. All clients of this trusted, loopback-only daemon share its authority and store.

Each successful named write or retrieval increments the run's revision and saves the records as that operation observed them. An observation with retrieved records increments it again and saves the resulting utilities for records still present. The latest observation of each record replaces that run's earlier snapshot; membership separately remembers whether the run wrote or retrieved it. A retrieval snapshot matches the returned record, before that retrieval increments its access count. Later writes, reads, credit updates or pruning outside that run do not alter its retained snapshots. This is an account of what the run last observed, not a current store snapshot or a complete event history.

Call `ExportRun` with the original ID and an explicit `record_scope`:

- `WRITTEN` includes records that this run wrote.
- `RETRIEVED` includes records returned to this run.
- `TOUCHED` is their union, once per record.
- `NONE` omits the record attachment. An empty selection in any other supported scope returns the JSON array `[]`.

The daemon refuses `ALL`, `UNSPECIFIED` and unknown scopes. It filters membership before ordering by record ID and applying `max_records`; zero means all selected records, and a negative limit is invalid. The response preserves `run_id` and supplies `source_revision`. Pass that value as `expected_revision` to refuse an export after the run changes. Older revisions are not retained. Repeated exports of the same revision, scope and limit have identical snapshot bytes, including deterministic tag ordering.

`records_snapshot_json` is a UTF-8 array of the generated Rust `Record` serialization: camelCase field names, numeric enum values, byte arrays for payloads, and nullable optional fields. It is not protobuf JSON. The schema retains nested records, costs, utility and score fields; the generated `TagValue` serialization nests its oneof under `value`. Written string and list tags and ordered links, including their metadata bytes, survive storage, retrieval, credit updates and export.

No task, configuration, finish time, metric or performance result is invented: `summary` is absent. Events, metric CSV and archive flags each return `UNIMPLEMENTED`; unrequested attachments remain absent or empty according to their protobuf presence. `Probe` also remains unimplemented until a runner measures both comparison arms. This record-only export is not yet a complete debugger run bundle.

`--max-runs` defaults to 1,000 and `--max-run-bytes` to 67,108,864. Both must be positive. The byte limit counts each retained run ID, record ID, encoded JSON snapshot and two membership flags; it is a retained-data budget, not a bound on allocator overhead, temporary copies or process memory. A full budget refuses the operation before changing records or attribution. The daemon does not evict another run to make room. Snapshots survive record pruning but last only until the process exits; there is no persistence, automatic expiry or run deletion API. Save the export before ending the daemon.

## Records and queries

The generated `reckon.core.v1.Record` is the daemon's stored record and response type. Its fields come from [types.proto](../protos/reckon/core/v1/types.proto); [record.rs](src/record.rs) supplies initialization and scoring helpers without another field definition. This model keeps typed tags and explicit links separate from the laboratory model's tag list and origin.

`Write` retains the declared payload bytes and kind, typed tag map, ordered links and initial utility. The daemon assigns identity, episode, timestamp and costs; compression, encoding, metadata and creation sequence keep their existing defaults because `WriteRequest` does not accept those fields. Link metadata bytes are retained without parsing or rewriting their JSON.

Tag queries require every requested key and its exact typed value. A string differs from a list containing that string; list order and repeated entries matter. Empty strings, empty lists and a present tag with no selected value stay distinct from one another and from a missing key. A list predicate is never discarded to broaden a query. ID and utility queries return the same complete record representation, with the existing retrieval and context behavior.

The [repository guide](../README.md#the-grpc-daemon-is-a-local-tool) covers startup and record/context limits. The [Python wire guide](../protos/README.md) and [TypeScript client](../sdks/typescript/README.md) provide the generated request and response types.
