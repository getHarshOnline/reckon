import { PayloadType, type MemoryRecord, type LaboratoryRecord } from '@rtepl/reckon-components';

// protobuf-ts exposes int64 fields as decimal strings. Derive the adapter's
// input from the view, keeping this conversion separate from the wire schema.
type DecimalIntegers<T, K extends keyof T> = Omit<T, K> & { [P in K]: string };
type WireRecord = Omit<MemoryRecord,
  'timestamp' | 'cost' | 'utility' | 'causalScore' | 'createdAtStep' | 'createdAtSequence'> & {
  timestamp: string;
  cost?: DecimalIntegers<MemoryRecord['cost'], 'bytes' | 'tokens'>;
  utility?: DecimalIntegers<MemoryRecord['utility'], 'lastUsed'>;
  causalScore?: DecimalIntegers<MemoryRecord['causalScore'], 'lastEvaluated'>;
  createdAtStep?: string;
  createdAtSequence?: string;
};

function exactInteger(value: string, field: string): number {
  const number = Number(value);
  if (!Number.isSafeInteger(number) || BigInt(number) !== BigInt(value)) {
    throw new RangeError(`${field} exceeds the viewer's exact integer range`);
  }
  return number;
}

/** Adapt a decoded laboratory record for the viewer without rounding int64 values. */
export function laboratoryWireRecord(value: WireRecord): MemoryRecord {
  const { cost, utility, causalScore, createdAtStep, createdAtSequence, ...fields } = value;
  if (!cost || !utility || !causalScore) {
    throw new Error('Laboratory records require cost, utility and causalScore messages');
  }
  return {
    ...fields,
    timestamp: exactInteger(value.timestamp, 'timestamp'),
    cost: {
      ...cost,
      bytes: exactInteger(cost.bytes, 'cost.bytes'),
      tokens: exactInteger(cost.tokens, 'cost.tokens'),
    },
    utility: { ...utility, lastUsed: exactInteger(utility.lastUsed, 'utility.lastUsed') },
    causalScore: {
      ...causalScore,
      lastEvaluated: exactInteger(causalScore.lastEvaluated, 'causalScore.lastEvaluated'),
    },
    ...(createdAtStep === undefined ? {} : { createdAtStep: exactInteger(createdAtStep, 'createdAtStep') }),
    ...(createdAtSequence === undefined ? {} : { createdAtSequence: exactInteger(createdAtSequence, 'createdAtSequence') }),
  };
}

/** Project the generated Rust JSON model; no int64 passes through JSON numbers. */
export function laboratoryRecord(value: LaboratoryRecord): MemoryRecord {
  const { createdAtStep, createdAtSequence, provenance, ...fields } = value;
  const kinds: Record<string, PayloadType> = {
    unspecified: PayloadType.UNSPECIFIED, observation: PayloadType.OBSERVATION,
    action: PayloadType.ACTION, reward: PayloadType.REWARD, cue: PayloadType.CUE,
    trace: PayloadType.TRACE, representation: PayloadType.REPRESENTATION, custom: PayloadType.CUSTOM,
  };
  const payloadType = kinds[value.payloadType];
  if (payloadType === undefined) throw new Error(`Unsupported payload type: ${value.payloadType}`);
  return {
    ...fields, payloadType,
    timestamp: exactInteger(value.timestamp, 'timestamp'),
    payload: new Uint8Array(value.payload), metadata: new Uint8Array(value.metadata),
    cost: { ...value.cost, bytes: exactInteger(value.cost.bytes, 'cost.bytes'),
      tokens: value.cost.tokens === null ? null : exactInteger(value.cost.tokens, 'cost.tokens') },
    utility: { ...value.utility, lastUsed: exactInteger(value.utility.lastUsed, 'utility.lastUsed') },
    causalScore: { ...value.causalScore, lastEvaluated: exactInteger(value.causalScore.lastEvaluated, 'causalScore.lastEvaluated') },
    ...(provenance === null ? {} : { provenance }),
    ...(createdAtStep === null ? {} : { createdAtStep: exactInteger(createdAtStep, 'createdAtStep') }),
    ...(createdAtSequence === null ? {} : { createdAtSequence: exactInteger(createdAtSequence, 'createdAtSequence') }),
  };
}
