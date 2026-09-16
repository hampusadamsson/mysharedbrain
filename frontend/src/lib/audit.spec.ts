import { describe, expect, it } from 'vitest';
import { AUDIT_KINDS } from './audit';

describe('AUDIT_KINDS', () => {
	it('offers every kind the backend can report, in one order', () => {
		expect(AUDIT_KINDS.map((k) => k.kind)).toEqual([
			'read',
			'find',
			'write',
			'move',
			'delete',
			'capture',
			'job',
			'other'
		]);
	});

	it('uses human labels, not the raw kind', () => {
		expect(AUDIT_KINDS.find((k) => k.kind === 'find')?.label).toBe('keyword finds');
		expect(AUDIT_KINDS.find((k) => k.kind === 'job')?.label).toBe('agent runs');
		expect(AUDIT_KINDS.every((k) => k.label.length > 0)).toBe(true);
	});
});
