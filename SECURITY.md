# Security Policy

Reckon is unreleased research software for trusted local laboratory use. Maintenance and response times require a separate support agreement.

## Reporting a vulnerability

A private security-reporting channel has not yet been confirmed. Do not post credentials, private memory records or exploit details in a public issue.

A useful report identifies the affected revision, gives reproduction steps and explains the likely impact. Remove credentials and private records from any reproduction before sharing it through a confirmed private channel.

## Security Considerations

Reckon is a research library for agent memory management. When using it:

- **Data Privacy**: Memory records may contain sensitive information; implement appropriate access controls
- **Resource Limits**: Validate incoming payload sizes before calling `write()`. The manager refuses a record whose declared or estimated byte cost exceeds `max_bytes` before pruning existing records. Its record accounting does not bound the process’s total memory or the caller’s payload allocations. See [budget enforcement](docs/08-Causal-Memory-Manager-Design.md#budget-enforcement).
- **Input Validation**: Validate external inputs at the interface that consumes them, including payload size and permitted file paths. No single schema validates every record, event stream or API request. Protocol declarations, public Python dataclasses and server request models have different coverage.
- **Logging**: Be mindful of what gets logged in debug/visualization outputs
- **The gRPC daemon**: `reckon-daemon` defaults to `127.0.0.1` and rejects non-loopback addresses. It uses plaintext, has no caller authentication and is for trusted local laboratory use only.
