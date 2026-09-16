import { describe, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import { render } from 'vitest-browser-svelte';
import Pagination from './Pagination.svelte';

describe('Pagination', () => {
	it('shows the visible range and disables Previous on the first page', async () => {
		await render(Pagination, {
			total: 137,
			limit: 20,
			offset: 0,
			count: 20,
			label: 'entry',
			labelPlural: 'entries',
			onchange: vi.fn()
		});
		await expect.element(page.getByText('Showing 1–20 of 137 entries')).toBeVisible();
		await expect.element(page.getByRole('button', { name: 'Previous' })).toBeDisabled();
		await expect.element(page.getByRole('button', { name: 'Next' })).toBeEnabled();
	});

	it('reports the next and previous offsets', async () => {
		const onchange = vi.fn();
		await render(Pagination, { total: 137, limit: 20, offset: 40, count: 20, onchange });

		await page.getByRole('button', { name: 'Next' }).click();
		expect(onchange).toHaveBeenLastCalledWith(60);
		await page.getByRole('button', { name: 'Previous' }).click();
		expect(onchange).toHaveBeenLastCalledWith(20);
	});

	it('clamps the last page and disables Next', async () => {
		await render(Pagination, {
			total: 45,
			limit: 20,
			offset: 40,
			count: 5,
			label: 'change',
			labelPlural: 'changes',
			onchange: vi.fn()
		});
		await expect.element(page.getByText('Showing 41–45 of 45 changes')).toBeVisible();
		await expect.element(page.getByRole('button', { name: 'Next' })).toBeDisabled();
	});

	it('handles an empty result without a range', async () => {
		await render(Pagination, { total: 0, limit: 20, offset: 0, count: 0, onchange: vi.fn() });
		await expect.element(page.getByText('Showing 0–0 of 0 items')).toBeVisible();
		await expect.element(page.getByRole('button', { name: 'Next' })).toBeDisabled();
	});

	it('uses the singular noun for a single row', async () => {
		await render(Pagination, {
			total: 1,
			limit: 20,
			offset: 0,
			count: 1,
			label: 'entry',
			labelPlural: 'entries',
			onchange: vi.fn()
		});
		await expect.element(page.getByText('Showing 1–1 of 1 entry')).toBeVisible();
	});

	it('disables both buttons while loading', async () => {
		await render(Pagination, {
			total: 137,
			limit: 20,
			offset: 20,
			count: 20,
			disabled: true,
			onchange: vi.fn()
		});
		await expect.element(page.getByRole('button', { name: 'Previous' })).toBeDisabled();
		await expect.element(page.getByRole('button', { name: 'Next' })).toBeDisabled();
	});

	it('never renders NaN when the server does not report a total', async () => {
		// Version skew: an older backend returns no `total`. Degrade to the window.
		await render(Pagination, {
			limit: 20,
			offset: 0,
			count: 7,
			label: 'entry',
			labelPlural: 'entries',
			onchange: vi.fn()
		});

		await expect.element(page.getByText('Showing 1–7')).toBeVisible();
		expect(page.getByText(/NaN/).elements()).toHaveLength(0);
		// a short page cannot promise more
		await expect.element(page.getByRole('button', { name: 'Next' })).toBeDisabled();
	});

	it('assumes more pages when a full page arrives without a total', async () => {
		await render(Pagination, { limit: 20, offset: 20, count: 20, onchange: vi.fn() });

		await expect.element(page.getByText('Showing 21–40')).toBeVisible();
		await expect.element(page.getByRole('button', { name: 'Next' })).toBeEnabled();
		await expect.element(page.getByRole('button', { name: 'Previous' })).toBeEnabled();
	});

	it('ignores a non-numeric total instead of showing NaN', async () => {
		await render(Pagination, {
			total: Number.NaN,
			limit: 20,
			offset: 0,
			count: 3,
			onchange: vi.fn()
		});

		await expect.element(page.getByText('Showing 1–3')).toBeVisible();
		expect(page.getByText(/NaN/).elements()).toHaveLength(0);
	});
});
