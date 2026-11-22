import { expect, test } from 'vitest';
import * as wireTypes from '../../../../generated/reckon/record';
import type { RecordOrigin } from '../types';

test('record origin keeps embedded bytes and field keys across the type rename', () => {
  const wire = Uint8Array.from(
    '521f0a0577726974651201611201621a1030313233343536373839616263646566'
      .match(/../g)!.map(value => parseInt(value, 16))
  );
  const origin: RecordOrigin = {
    sourceOp: 'write', inputIds: ['a', 'b'], hash: '0123456789abcdef',
  };
  const record = wireTypes.MemoryRecord.fromBinary(wire);
  expect(record.provenance).toEqual(origin);
  expect(wireTypes.MemoryRecord.toBinary(record)).toEqual(wire);
  expect(wireTypes.MemoryRecord.toJson(record)).toEqual({ provenance: origin });
  expect(wireTypes.RecordOrigin.typeName).toBe('reckon.RecordOrigin');
  expect(wireTypes).not.toHaveProperty('Provenance');
});
