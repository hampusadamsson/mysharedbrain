// Typed HTTP client for the MySharedBrain REST API. Same-origin in prod
// (backend serves the UI); vite dev server proxies /api + /health to :8000.
// The UI never imports backend code — HTTP JSON only (decoupling contract).

export interface Note {
	id: string;
	content: string;
}

export interface SearchHit {
	id: string;
	excerpts: string[];
}

export interface SearchResult {
	names: string[];
	content: SearchHit[];
}

export type FeedbackKind = 'edit' | 'missing' | 'request' | 'question';
export type FeedbackStatus = 'pending' | 'applied' | 'approved' | 'rejected';
export type ReviewVerdict = 'applied' | 'approved' | 'rejected';

export interface FeedbackEntry {
	id: string;
	ts: string;
	kind: string;
	body: string;
	note_id: string;
	status: FeedbackStatus;
	reviewer: string;
	review_note: string;
	/** Filed by the system (an unanswered question), not by a person. */
	automated: boolean;
}

/** Human labels for the capture kinds. */
export const FEEDBACK_KINDS: { value: FeedbackKind; label: string }[] = [
	{ value: 'edit', label: 'Edit' },
	{ value: 'missing', label: 'Missing info' },
	{ value: 'request', label: 'Request' },
	{ value: 'question', label: 'Question' }
];

/** Every state an entry can be set to, for the state dropdown. */
export const FEEDBACK_STATUSES: { value: FeedbackStatus; label: string }[] = [
	{ value: 'pending', label: 'Pending' },
	{ value: 'approved', label: 'Approved' },
	{ value: 'applied', label: 'Applied' },
	{ value: 'rejected', label: 'Rejected' }
];

export function feedbackKindLabel(kind: string): string {
	return FEEDBACK_KINDS.find((k) => k.value === kind)?.label ?? kind;
}

export interface AuditEntry {
	ts: string;
	actor: string;
	action: string;
	/** Coarse category: read | find | write | move | delete | capture | job | other */
	kind: string;
	note_id: string;
	detail: string;
}

export interface FileStats {
	note_id: string;
	counts: Record<string, number>;
	first_seen: string;
	last_seen: string;
	total: number;
}

export interface FileHistory {
	entries: AuditEntry[];
	total: number;
	limit: number;
	offset: number;
	stats: FileStats;
}

export interface Answer {
	found: boolean;
	question: string;
	note_ids: string[];
	hits: SearchHit[];
	entry_id: string;
	message: string;
}

export interface CaptureList {
	entries: FeedbackEntry[];
	total: number;
	limit: number;
	offset: number;
}

export interface AuditList {
	entries: AuditEntry[];
	total: number;
	limit: number;
	offset: number;
}

export interface ProviderConfig {
	name: string;
	base_url: string;
	api_version: string;
	options: Record<string, string>;
}

export interface AgentConfig {
	model: string;
	provider: ProviderConfig;
	api_key: string;
	api_key_env: string;
	instructions_file: string;
	instructions: string;
	max_steps: number;
	temperature: number | null;
}

/** One selectable provider, as reported by the server. */
export interface ProviderInfo {
	name: string;
	available: boolean;
	/** Constructor parameter that takes a custom endpoint ('' = none). */
	url_param: string;
	api_version_param: string;
	/** Why it is unavailable, or what it needs. */
	hint: string;
}

export interface Providers {
	providers: ProviderInfo[];
	current: string;
	model: string;
}

export interface SchedulerConfig {
	enabled: boolean;
	tick_seconds: number;
	run_on_start: boolean;
}

/** One interactive librarian run per question — shaped like a job, no schedule. */
export interface AskConfig {
	enabled: boolean;
	instructions_file: string | null;
	tools: string[] | null;
	mcp_servers: string[] | null;
	max_steps: number | null;
	/** Cap on one question, in seconds (5–600); the Ask page spins until then. */
	timeout_seconds: number;
}

/** Remote only: a local (stdio) MCP server would be shell access. */
export type McpTransport = 'http' | 'sse';

export interface MCPServerConfig {
	name: string;
	transport: McpTransport;
	url: string;
	headers: Record<string, string>;
	enabled: boolean;
	insecure: boolean;
}

export interface JobSpec {
	id: string;
	name: string;
	description: string;
	enabled: boolean;
	every: string | null;
	cron: string | null;
	instructions: string;
	instructions_file: string | null;
	tools: string[] | null;
	mcp_servers: string[] | null;
	max_steps: number | null;
}

/** Vault administration: templates, prompts and the wiki layout (all markdown). */
export interface AdminConfig {
	dir: string;
	layout_template: string;
	templates: Record<string, string>;
	prompts: Record<string, string>;
}

export interface BrainConfigDoc {
	agent: AgentConfig;
	admin: AdminConfig;
	ask: AskConfig;
	scheduler: SchedulerConfig;
	tools: Record<string, { enabled: boolean }>;
	mcp_servers: MCPServerConfig[];
	jobs: JobSpec[];
}

export interface JobStatus {
	id: string;
	name: string;
	enabled: boolean;
	schedule: string;
	next_run: string;
	last_run: string;
	last_status: string;
}

export interface ToolInfo {
	name: string;
	description: string;
	enabled: boolean;
}

export interface McpCheck {
	name: string;
	ok: boolean;
	detail: string;
	tools: string[];
}

/** One shape for every connection check: MCP servers and the model provider. */
export type CheckResult = McpCheck;

export interface Settings {
	config: BrainConfigDoc;
	jobs: JobStatus[];
	tools: ToolInfo[];
	/** Seed file, read only — the document itself is in the database. */
	config_path: string;
	/** Where the settings come from: database | file | defaults. */
	config_source: string;
	api_key_env: string;
	api_key_configured: boolean;
}

export interface JobRun {
	id: number;
	job_id: string;
	started_at: string;
	finished_at: string;
	status: string;
	detail: string;
}

export interface Directory {
	folders: string[];
	notes: string[];
}

export interface ImportResult {
	created: string[];
	updated: string[];
	skipped: string[];
	errors: Record<string, string>;
}

export class ApiError extends Error {
	status: number;
	constructor(status: number, detail: string) {
		super(detail);
		this.name = 'ApiError';
		this.status = status;
	}
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
	const res = await fetch(path, {
		...init,
		headers: { 'Content-Type': 'application/json', ...init?.headers }
	});
	if (res.status === 204) return null as T;
	if (!res.ok) {
		let detail = res.statusText;
		try {
			const body = await res.json();
			if (typeof body?.detail === 'string') detail = body.detail;
		} catch {
			/* keep statusText */
		}
		throw new ApiError(res.status, detail);
	}
	return (await res.json()) as T;
}

const get = <T>(path: string) => req<T>(path);
const post = <T>(path: string, body: unknown) =>
	req<T>(path, { method: 'POST', body: JSON.stringify(body) });
const put = <T>(path: string, body: unknown) =>
	req<T>(path, { method: 'PUT', body: JSON.stringify(body) });

export const api = {
	health: () => get<{ status: string }>('/health'),

	listNotes: (prefix = '', limit?: number, offset = 0) => {
		const q = new URLSearchParams({ prefix, offset: String(offset) });
		if (limit !== undefined) q.set('limit', String(limit));
		return get<{ notes: string[] }>(`/api/notes?${q}`);
	},
	createNote: (id: string, content = '') => post<Note>('/api/notes', { id, content }),
	readNote: (id: string) => get<Note>(`/api/notes/${encodeURIComponent(id)}`),
	updateNote: (id: string, content: string) =>
		req<Note>(`/api/notes/${encodeURIComponent(id)}`, {
			method: 'PUT',
			body: JSON.stringify({ content })
		}),
	deleteNote: (id: string) =>
		req<null>(`/api/notes/${encodeURIComponent(id)}`, { method: 'DELETE' }),
	restoreNote: (id: string) => post<Note>(`/api/notes/${encodeURIComponent(id)}/restore`, {}),
	moveNote: (id: string, to: string) =>
		post<Note>(`/api/notes/${encodeURIComponent(id)}/move`, { to }),
	appendNote: (id: string, content: string) =>
		post<Note>(`/api/notes/${encodeURIComponent(id)}/append`, { content }),
	patchNote: (id: string, heading: string, content: string, mode = 'replace') =>
		req<Note>(`/api/notes/${encodeURIComponent(id)}`, {
			method: 'PATCH',
			body: JSON.stringify({ heading, content, mode })
		}),
	readBatch: (note_ids: string[]) =>
		post<{ notes: Note[]; missing: string[] }>('/api/notes/batch', { note_ids }),
	/** Upload files or a whole folder: each file becomes a note (FormData). */
	importNotes: async (files: File[], prefix = '', overwrite = true): Promise<ImportResult> => {
		const form = new FormData();
		for (const f of files) {
			const rel = (f as File & { webkitRelativePath?: string }).webkitRelativePath || f.name;
		form.append('files', f, rel);
		}
		form.append('prefix', prefix);
		form.append('overwrite', String(overwrite));
		const res = await fetch('/api/notes/import', { method: 'POST', body: form });
		if (!res.ok) {
			let detail = res.statusText;
			try {
				const body = await res.json();
				if (typeof body?.detail === 'string') detail = body.detail;
			} catch {
				/* keep statusText */
			}
			throw new ApiError(res.status, detail);
		}
		return (await res.json()) as ImportResult;
	},
	browse: (prefix = '') => get<Directory>(`/api/browse?prefix=${encodeURIComponent(prefix)}`),
	frontmatter: (id: string) =>
		get<Record<string, unknown>>(`/api/notes/${encodeURIComponent(id)}/meta`),
	setFrontmatter: (id: string, updates: Record<string, unknown>) =>
		req<Note>(`/api/notes/${encodeURIComponent(id)}/meta`, {
			method: 'PUT',
			body: JSON.stringify({ updates })
		}),
	outgoing: (id: string) =>
		get<{ links: string[] }>(`/api/notes/${encodeURIComponent(id)}/outgoing`),
	backlinks: (id: string) =>
		get<{ links: string[] }>(`/api/notes/${encodeURIComponent(id)}/backlinks`),
	byTag: (tag: string) => get<{ notes: string[] }>(`/api/tags/${encodeURIComponent(tag)}`),
	search: (q: string, limit = 20, offset = 0, track = true) => {
		const p = new URLSearchParams({
			q,
			limit: String(limit),
			offset: String(offset),
			track: String(track)
		});
		return get<SearchResult>(`/api/search?${p}`);
	},

	giveFeedback: (kind: FeedbackKind, body: string, note_id = '') =>
		post<{ id: string; status: FeedbackStatus }>('/api/feedback', { kind, body, note_id }),
	listCapture: (status?: FeedbackStatus, limit = 50, offset = 0) => {
		const p = new URLSearchParams({ limit: String(limit), offset: String(offset) });
		if (status) p.set('status', status);
		return get<CaptureList>(`/api/capture?${p}`);
	},
	reviewCapture: (
		entry_id: string,
		verdict: ReviewVerdict,
		reviewer = 'ui',
		content?: string | null,
		review_note = ''
	) =>
		post<{ id: string; status: FeedbackStatus }>(
			`/api/capture/${encodeURIComponent(entry_id)}/review`,
			{ verdict, reviewer, content, review_note }
		),
	/** Override an entry's state outright — any state, no vault change. */
	setCaptureStatus: (entry_id: string, status: FeedbackStatus, review_note = '') =>
		put<{ id: string; status: FeedbackStatus }>(
			`/api/capture/${encodeURIComponent(entry_id)}/status`,
			{ status, reviewer: 'ui', review_note }
		),

	ask: (question: string) => post<Answer>('/api/request', { question }),
	audit: (limit = 50, offset = 0, kind?: string) => {
		const p = new URLSearchParams({ limit: String(limit), offset: String(offset) });
		if (kind) p.set('kind', kind);
		return get<AuditList>(`/api/audit?${p}`);
	},

	/** Every logged interaction with one note, with per-kind counts. */
	noteHistory: (id: string, kind?: string, limit = 20, offset = 0) => {
		const p = new URLSearchParams({ limit: String(limit), offset: String(offset) });
		if (kind) p.set('kind', kind);
		return get<FileHistory>(`/api/notes/${encodeURIComponent(id)}/history?${p}`);
	},

	getSettings: () => get<Settings>('/api/settings'),
	/** Model providers this install can reach, and what each needs. */
	modelProviders: () => get<Providers>('/api/settings/providers'),
	updateSettings: (config: BrainConfigDoc) => put<Settings>('/api/settings', { config }),
	/** The effective config (defaults+file+saved settings), as YAML, token masked. */
	exportSettings: async () => {
		const res = await fetch('/api/settings/export');
		if (!res.ok) throw new ApiError(res.status, res.statusText);
		return res.text();
	},
	/** Replace the whole config from pasted/uploaded YAML — same shape as export. */
	importSettings: (text: string) => put<Settings>('/api/settings/import', { yaml: text }),
	runJob: (job_id: string) =>
		post<JobRun>(`/api/settings/jobs/${encodeURIComponent(job_id)}/run`, {}),
	jobRuns: (job_id: string, limit = 20) =>
		get<{ runs: JobRun[] }>(`/api/settings/jobs/${encodeURIComponent(job_id)}/runs?limit=${limit}`),
	/** Try to connect to an MCP server; reports its tools or why it failed. */
	testMcpServer: (server: MCPServerConfig) => post<McpCheck>('/api/settings/mcp/test', server),
	/** Ask the configured model for a one-word answer, and time it. */
	testModel: (agent: AgentConfig) => post<CheckResult>('/api/settings/model/test', agent)
};
