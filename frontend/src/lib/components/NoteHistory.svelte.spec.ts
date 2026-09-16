import { beforeEach, describe, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import { render } from 'vitest-browser-svelte';
import NoteHistory from './NoteHistory.svelte';

const api = vi.hoisted(() => ({ noteHistory: vi.fn() }));

vi.mock('$lib/api/client', async () => {
	const actual = await vi.importActual<typeof import('$lib/api/client')>('$lib/api/client');
	return { ...actual, api };
});

beforeEach(() => {
	vi.clearAllMocks();
	api.noteHistory.mockResolvedValue({
		entries: [
			{
				ts: new Date().toISOString(),
				actor: 'curator',
				action: 'read',
				kind: 'read',
				note_id: 'projects/homelab',
				detail: ''
			}
		],
		total: 1,
		limit: 20,
		offset: 0,
		stats: {
			note_id: 'projects/homelab',
			counts: { read: 1 },
			first_seen: new Date().toISOString(),
			last_seen: new Date().toISOString(),
			total: 1
		}
	});
});

describe('NoteHistory (file scope)', () => {
	it('scopes the shared log to this file', async () => {
		await render(NoteHistory, { noteId: 'projects/homelab' });

		await expect.element(page.getByText('FILE LOG')).toBeVisible();
		await expect
			.poll(() => api.noteHistory)
			.toHaveBeenCalledWith('projects/homelab', undefined, 20, 0);
	});

	it('passes the chosen kind through and refetches on a new version', async () => {
		const { rerender } = await render(NoteHistory, {
			noteId: 'projects/homelab',
			version: 0
		});
		await page.getByRole('button', { name: '1 reads' }).click();
		await expect
			.poll(() => api.noteHistory)
			.toHaveBeenLastCalledWith('projects/homelab', 'read', 20, 0);

		api.noteHistory.mockClear();
		await rerender({ noteId: 'projects/homelab', version: 1 });

		await expect.poll(() => api.noteHistory).toHaveBeenCalled();
	});
});
