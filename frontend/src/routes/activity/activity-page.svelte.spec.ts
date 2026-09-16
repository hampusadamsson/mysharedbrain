import { beforeEach, describe, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import { render } from 'vitest-browser-svelte';
import Activity from './+page.svelte';

const api = vi.hoisted(() => ({ audit: vi.fn() }));

vi.mock('$lib/api/client', async () => {
	const actual = await vi.importActual<typeof import('$lib/api/client')>('$lib/api/client');
	return { ...actual, api };
});

function respond(kindCounts: Record<string, number> = { read: 3, write: 1, job: 2 }) {
	const total = Object.values(kindCounts).reduce((a, b) => a + b, 0);
	api.audit.mockResolvedValue({
		entries: [
			{
				ts: new Date().toISOString(),
				actor: 'librarian',
				action: 'job-ok',
				kind: 'job',
				note_id: '',
				detail: 'job:sweep'
			}
		],
		total,
		limit: 25,
		offset: 0,
		stats: {
			note_id: '',
			counts: kindCounts,
			first_seen: new Date().toISOString(),
			last_seen: new Date().toISOString(),
			total
		}
	});
}

beforeEach(() => {
	vi.clearAllMocks();
	respond();
});

describe('Activity', () => {
	it('uses the same per-kind counters as the file log', async () => {
		await render(Activity);

		await expect.element(page.getByRole('button', { name: 'All 6' })).toBeVisible();
		await expect.element(page.getByRole('button', { name: '3 reads' })).toBeVisible();
		await expect.element(page.getByRole('button', { name: '1 edits' })).toBeVisible();
		await expect.element(page.getByRole('button', { name: '2 agent runs' })).toBeVisible();
	});

	it('filters the whole log by kind', async () => {
		await render(Activity);

		await page.getByRole('button', { name: '2 agent runs' }).click();

		await expect.poll(() => api.audit).toHaveBeenLastCalledWith(25, 0, 'job');
	});

	it('shows librarian activity and its metadata', async () => {
		await render(Activity);

		await expect.element(page.getByText(/^Librarian$/)).toBeVisible();
		await expect.element(page.getByText(/^job$/)).toBeVisible();
		await expect.element(page.getByText('job-ok')).toBeVisible();
	});

	it('paginates the log', async () => {
		respond({ read: 60 });
		api.audit.mockResolvedValue({
			entries: [
				{
					ts: new Date().toISOString(),
					actor: 'api',
					action: 'read',
					kind: 'read',
					note_id: 'a',
					detail: ''
				}
			],
			total: 60,
			limit: 25,
			offset: 0,
			stats: {
				note_id: '',
				counts: { read: 60 },
				first_seen: new Date().toISOString(),
				last_seen: new Date().toISOString(),
				total: 60
			}
		});
		await render(Activity);

		await page.getByRole('button', { name: 'Next' }).click();

		await expect.poll(() => api.audit).toHaveBeenLastCalledWith(25, 25, undefined);
	});

	it('reloads without losing the filter', async () => {
		await render(Activity);
		await page.getByRole('button', { name: '1 edits' }).click();
		await expect.poll(() => api.audit).toHaveBeenLastCalledWith(25, 0, 'write');

		const before = api.audit.mock.calls.length;
		await page.getByRole('button', { name: 'Reload' }).click();

		await expect.poll(() => api.audit.mock.calls.length).toBeGreaterThan(before);
		expect(api.audit).toHaveBeenLastCalledWith(25, 0, 'write');
	});
});
