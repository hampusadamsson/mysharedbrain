import { describe, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import { render } from 'vitest-browser-svelte';
import InteractionLog from './InteractionLog.svelte';
import type { AuditEntry, FileStats } from '$lib/api/client';

function entry(action: string, kind: string, detail = '', actor = 'curator'): AuditEntry {
	return {
		ts: new Date(Date.now() - 60_000).toISOString(),
		actor,
		action,
		kind,
		note_id: 'projects/homelab',
		detail
	};
}

function stats(counts: Record<string, number>, noteId = ''): FileStats {
	const now = new Date().toISOString();
	return {
		note_id: noteId,
		counts,
		first_seen: now,
		last_seen: now,
		total: Object.values(counts).reduce((a, b) => a + b, 0)
	};
}

function loader(
	overrides: Partial<{ entries: AuditEntry[]; total: number; stats: FileStats }> = {}
) {
	return vi.fn(async () => ({
		entries: overrides.entries ?? [entry('update', 'write'), entry('read', 'read')],
		total: overrides.total ?? 2,
		stats: overrides.stats ?? stats({ read: 1, write: 1 })
	}));
}

describe('InteractionLog', () => {
	it('renders the per-kind counts as filter chips', async () => {
		await render(InteractionLog, { load: loader() });

		await expect.element(page.getByRole('button', { name: 'All 2' })).toBeVisible();
		await expect.element(page.getByRole('button', { name: '1 reads' })).toBeVisible();
		await expect.element(page.getByRole('button', { name: '1 edits' })).toBeVisible();
		// kinds with no entries are not offered
		expect(page.getByRole('button', { name: /moves/ }).elements()).toHaveLength(0);
	});

	it('summarises the first and last sighting', async () => {
		await render(InteractionLog, { load: loader() });

		await expect.element(page.getByText(/first .*last /)).toBeVisible();
	});

	it('lists the interactions with their file, actor and kind', async () => {
		await render(InteractionLog, { load: loader() });

		await expect.element(page.getByText('update')).toBeVisible();
		const items = page.getByRole('list', { name: 'Interactions' }).getByRole('listitem');
		await expect.element(items.first()).toBeVisible();
		expect(items.elements()).toHaveLength(2);
	});

	it('filters by kind and resets to the first page', async () => {
		const load = loader({ entries: [entry('read', 'read')], total: 1 });
		await render(InteractionLog, { load });

		await page.getByRole('button', { name: '1 reads' }).click();

		await expect.poll(() => load).toHaveBeenLastCalledWith('read', 20, 0);
	});

	it('paginates with the loader', async () => {
		const load = loader({ total: 45, stats: stats({ read: 45 }) });
		await render(InteractionLog, { load });

		await page.getByRole('button', { name: 'Next' }).click();

		await expect.poll(() => load).toHaveBeenLastCalledWith(null, 20, 20);
	});

	it('marks librarian interactions', async () => {
		const load = loader({
			entries: [entry('job-ok', 'job', 'job:sweep — 1 request(s)', 'librarian')],
			total: 1,
			stats: stats({ job: 1 })
		});
		await render(InteractionLog, { load });

		await expect.element(page.getByText(/^Librarian$/)).toBeVisible();
		await expect.element(page.getByText('job-ok')).toBeVisible();
		await expect.element(page.getByText(/^librarian$/)).toBeVisible();
	});

	it('explains an empty scope', async () => {
		await render(InteractionLog, {
			load: loader({ entries: [], total: 0, stats: stats({}) }),
			emptyText: 'No activity recorded yet.'
		});

		await expect.element(page.getByText('No activity recorded yet.')).toBeVisible();
	});

	it('refetches when the caller bumps refreshKey, keeping the filter', async () => {
		const load = loader({ total: 45, stats: stats({ read: 45 }) });
		const { rerender } = await render(InteractionLog, { load, refreshKey: 0 });
		await page.getByRole('button', { name: '45 reads' }).click();
		await expect.poll(() => load).toHaveBeenLastCalledWith('read', 20, 0);
		const calls = load.mock.calls.length;

		await rerender({ load, refreshKey: 1 });

		await expect.poll(() => load.mock.calls.length).toBeGreaterThan(calls);
		expect(load).toHaveBeenLastCalledWith('read', 20, 0);
	});
});
