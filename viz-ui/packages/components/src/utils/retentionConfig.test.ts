import { expect, test } from 'vitest';
import { MemoryManagerConfig, RetentionPolicyType } from '../../../../generated/reckon/budget';

test('retention names preserve wire numbers and use current JSON keys', () => {
  const wire = Uint8Array.from(
    '100419000000000000e83f'.match(/../g)!.map(value => parseInt(value, 16))
  );
  const config = MemoryManagerConfig.fromBinary(wire);
  expect(config.retentionPolicy).toBe(RetentionPolicyType.EVIDENCE_PER_BYTE);
  expect(config.evidenceWeight).toBe(0.75);
  expect(MemoryManagerConfig.toBinary(config)).toEqual(wire);
  const document = {
    retentionPolicy: 'RETENTION_POLICY_TYPE_EVIDENCE_PER_BYTE', evidenceWeight: 0.75,
  };
  expect(MemoryManagerConfig.toJson(config)).toEqual(document);
  expect(MemoryManagerConfig.toBinary(MemoryManagerConfig.fromJson(document))).toEqual(wire);
  expect(RetentionPolicyType).not.toHaveProperty('CAUSAL');
  expect(config).not.toHaveProperty('causalWeight');
});
