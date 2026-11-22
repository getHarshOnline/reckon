/** Use a caller-supplied transport, including a separately configured web gateway. */
import { createClient, type Transport } from "@connectrpc/connect";
import { CausalMemoryService } from "./gen/reckon/core/v1/service_connect.js";

export function createReckonClient(transport: Transport) {
  return createClient(CausalMemoryService, transport);
}

export { CausalMemoryService };
export { Code, ConnectError } from "@connectrpc/connect";
export * from "./types.js";
