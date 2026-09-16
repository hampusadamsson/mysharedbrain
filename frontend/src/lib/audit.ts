// Shared vocabulary + display labels for the audit kinds. The backend derives
// the kind from the action (see mysharedbrain/audit.py); this is how the UI
// names and orders them, in one place so Activity and the per-file log agree.
export const AUDIT_KINDS: { kind: string; label: string }[] = [
	{ kind: 'read', label: 'reads' },
	{ kind: 'find', label: 'keyword finds' },
	{ kind: 'write', label: 'edits' },
	{ kind: 'move', label: 'moves' },
	{ kind: 'delete', label: 'deletes' },
	{ kind: 'capture', label: 'feedback' },
	{ kind: 'job', label: 'agent runs' },
	{ kind: 'other', label: 'other' }
];
