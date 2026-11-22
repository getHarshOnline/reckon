/** Node.js gRPC client for the trusted-local laboratory daemon. */
import {
  createClient,
  type Client,
  type Interceptor,
} from "@connectrpc/connect";
import { createGrpcTransport } from "@connectrpc/connect-node";
import { CausalMemoryService } from "./gen/reckon/core/v1/service_connect.js";

export interface ReckonClientOptions {
  /** Address of the gRPC daemon, for example http://127.0.0.1:50051. */
  baseUrl: string;
  /** Default deadline in milliseconds; individual calls may override it. */
  timeout?: number;
  /** Metadata attached to each call. The daemon does not authenticate callers. */
  headers?: Record<string, string>;
}

type ServiceClient = Client<typeof CausalMemoryService>;

/**
 * Send protobuf messages over HTTP/2 and preserve gRPC errors and trailers.
 * Request objects may omit fields with protobuf defaults. Byte fields stay
 * Uint8Array, int64 fields stay bigint, and absent optional fields stay undefined.
 */
export class ReckonClient {
  readonly write: ServiceClient["write"];
  readonly retrieve: ServiceClient["retrieve"];
  readonly observe: ServiceClient["observe"];
  /** The Rust daemon currently returns Code.Unimplemented. */
  readonly probe: ServiceClient["probe"];
  /** The Rust daemon currently returns Code.Unimplemented. */
  readonly exportRun: ServiceClient["exportRun"];

  constructor(options: ReckonClientOptions) {
    const headers = new Headers(options.headers);
    const metadata: Interceptor = (next) => (request) => {
      headers.forEach((value, name) => request.header.set(name, value));
      return next(request);
    };
    const client = createClient(
      CausalMemoryService,
      createGrpcTransport({
        baseUrl: options.baseUrl.replace(/\/$/, ""),
        httpVersion: "2",
        defaultTimeoutMs: options.timeout ?? 30_000,
        interceptors: [metadata],
      }),
    );
    this.write = client.write;
    this.retrieve = client.retrieve;
    this.observe = client.observe;
    this.probe = client.probe;
    this.exportRun = client.exportRun;
  }
}

/** Create the Node.js client; timeout and metadata apply to every method. */
export function createReckonClient(
  baseUrl: string,
  options?: Omit<ReckonClientOptions, "baseUrl">,
): ReckonClient {
  return new ReckonClient({ baseUrl, ...options });
}
