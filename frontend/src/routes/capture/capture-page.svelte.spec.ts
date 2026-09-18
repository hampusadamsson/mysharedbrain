import { beforeEach, describe, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import { render } from 'vitest-browser-svelte';
import Capture from './+page.svelte';
import type { FeedbackEntry } from '$lib/api/client';

const api = vi.hoisted(() => ({
	listCapture: vi.fn(),
	reviewCapture: vi.fn(),
	setCaptureStatus: vi.fn()
}));
const space = vi.hoisted(() => ({ refreshPending: vi.fn(), refreshNotes: vi.fn() }));

vi.mock('$lib/api/client', async () => {
	const actual = await vi.importActual<typeof import('$lib/api/client')>('$lib/api/client');
	return { ...actual, api };
});

vi.mock('$lib/stores/space.svelte', () => space);

function entry(overrides: Partial<FeedbackEntry> = {}): FeedbackEntry {
	return {
		id: 'e1',
		ts: new Date().toISOString(),
		kind: 'question',
		body: 'Unanswered question: what is argo?',
		note_id: '',
		status: 'pending',
		reviewer: '',
		review_note: '',
		automated: true,
		...overrides
	};
}

function respond(entries: FeedbackEntry[], total = entries.length) {
	api.listCapture.mockResolvedValue({ entries, total, limit: 20, offset: 0 });
}

beforeEach(() => {
	vi.clearAllMocks();
	respond([entry()]);
});

describe('capture queue', () => {
	it('labels a question and tags it automated', async () => {
		await render(Capture);

		await expect.element(page.getByText(/^Question$/)).toBeVisible();
		await expect.element(page.getByText(/^automated$/)).toBeVisible();
		await expect.element(page.getByText('Unanswered question: what is argo?')).toBeVisible();
	});

	it('does not tag human feedback as automated', async () => {
		respond([entry({ kind: 'edit', body: 'fix the ip', automated: false })]);

		await render(Capture);

		await expect.element(page.getByText(/^Edit$/)).toBeVisible();
		expect(page.getByText(/^automated$/).elements()).toHaveLength(0);
	});

	it('requests the first page of pending work', async () => {
		await render(Capture);

		await expect.poll(() => api.listCapture).toHaveBeenCalledWith('pending', 20, 0);
	});

	it('offers every state on a resolved entry, not just pending ones', async () => {
		respond([entry({ kind: 'edit', status: 'rejected', automated: false })]);

		await render(Capture);

		const select = page.getByRole('button', { name: 'State for edit entry' });
		expect(select.element().textContent ?? '').toContain('Rejected');
		await select.click();
		// order matters: approved reads before applied
		const options = page
			.getByRole('option')
			.elements()
			.map((el) => el.textContent?.trim() ?? '');
		expect(options).toEqual(['Pending', 'Approved', 'Applied', 'Rejected']);
		// the quick pending-only buttons are gone once it is resolved
		expect(page.getByRole('button', { name: 'Approve', exact: true }).elements()).toHaveLength(0);
	});

	it('offers exactly one action on a pending entry: Approve', async () => {
		respond([entry({ kind: 'edit', status: 'pending', automated: false })]);

		await render(Capture);

		// Approving is the only button; other states go through the State dropdown.
		await expect.element(page.getByRole('button', { name: 'Approve', exact: true })).toBeVisible();
		// exact: the filter row has an 'Applied'/'Rejected' chip each
		expect(page.getByRole('button', { name: 'Apply', exact: true }).elements()).toHaveLength(0);
		expect(page.getByRole('button', { name: 'Reject', exact: true }).elements()).toHaveLength(0);
		expect(page.getByRole('dialog').elements()).toHaveLength(0);

		await page.getByRole('button', { name: 'Approve', exact: true }).click();
		await expect.poll(() => api.reviewCapture).toHaveBeenCalledWith('e1', 'approved');
	});

	it('can still reject through the State dropdown', async () => {
		respond([entry({ kind: 'edit', status: 'pending', automated: false })]);
		api.setCaptureStatus.mockResolvedValue({ id: 'e1', status: 'rejected' });

		await render(Capture);

		await page.getByRole('button', { name: 'State for edit entry' }).click();
		await page.getByRole('option', { name: 'Rejected' }).click();

		await expect.poll(() => api.setCaptureStatus).toHaveBeenCalledWith('e1', 'rejected');
	});

	it('orders the filter buttons approved before applied', async () => {
		await render(Capture);

		const STATUS_LABELS = ['Pending', 'Approved', 'Applied', 'Rejected', 'All'];
		const labels = page
			.getByRole('group', { name: 'Filter by state' })
			.getByRole('button')
			.elements()
			.map((el) => el.textContent?.trim() ?? '');
		expect(labels).toEqual(STATUS_LABELS);
	});

	it('sets a state through the dropdown regardless of the current one', async () => {
		respond([entry({ kind: 'edit', status: 'applied', automated: false })]);
		api.setCaptureStatus.mockResolvedValue({ id: 'e1', status: 'pending' });

		await render(Capture);
		await page.getByRole('button', { name: 'State for edit entry' }).click();
		await page.getByRole('option', { name: 'Pending' }).click();

		await expect.poll(() => api.setCaptureStatus).toHaveBeenCalledWith('e1', 'pending');
		await expect.poll(() => api.listCapture).toHaveBeenCalledTimes(2);
	});

	it('reloads so the dropdown snaps back when the change fails', async () => {
		respond([entry({ kind: 'edit', status: 'applied', automated: false })]);
		api.setCaptureStatus.mockRejectedValue(new Error('entry not found'));

		await render(Capture);
		await page.getByRole('button', { name: 'State for edit entry' }).click();
		await page.getByRole('option', { name: 'Rejected' }).click();

		await expect.poll(() => api.listCapture).toHaveBeenCalledTimes(2);
	});
});
