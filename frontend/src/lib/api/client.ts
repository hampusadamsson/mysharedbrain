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

export type FeedbackKind = 'edit' | 'missing' | 'request';
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
}

export interface AuditEntry {
	ts: string;
	actor: string;
	action: string;
	note_id: string;
	detail: string;
}

export interface Answer {
	found: boolean;
	question: string;
	note_ids: string[];
	hits: SearchHit[];
	entry_id: string;
	message: string;
}

export interface Directory {
	folders: string[];
	notes: string[];
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
	search: (q: string, limit = 20, offset = 0) => {
		const p = new URLSearchParams({ q, limit: String(limit), offset: String(offset) });
		return get<SearchResult>(`/api/search?${p}`);
	},

	giveFeedback: (kind: FeedbackKind, body: string, note_id = '') =>
		post<{ id: string; status: FeedbackStatus }>('/api/feedback', { kind, body, note_id }),
	listCapture: (status?: FeedbackStatus) =>
		get<{ entries: FeedbackEntry[] }>(status ? `/api/capture?status=${status}` : '/api/capture'),
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

	ask: (question: string) => post<Answer>('/api/request', { question }),
	audit: (limit = 50) => get<{ entries: AuditEntry[] }>(`/api/audit?limit=${limit}`)
};
