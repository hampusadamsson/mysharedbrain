import { describe, expect, it } from 'vitest';
import { page } from 'vitest/browser';
import { render } from 'vitest-browser-svelte';
import ConnectionStatus from './ConnectionStatus.svelte';
import type { CheckResult } from '$lib/api/client';

function result(over: Partial<CheckResult> = {}): CheckResult {
	return { name: 'x', ok: true, detail: 'answered in 12 ms: ok', tools: [], ...over };
}

describe('ConnectionStatus', () => {
	it('renders nothing before a check has run', async () => {
		const { container } = await render(ConnectionStatus, { checking: false });

		expect(container.textContent?.trim()).toBe('');
	});

	it('shows a spinner and the caller`s wording while checking', async () => {
		const { container } = await render(ConnectionStatus, {
			checking: true,
			checkingText: 'Asking the model…'
		});

		await expect.element(page.getByText('Asking the model…')).toBeVisible();
		expect(container.querySelector('.animate-spin')).not.toBeNull();
	});

	it('shows a green ok with the detail', async () => {
		const { container } = await render(ConnectionStatus, {
			checking: false,
			result: result()
		});

		await expect.element(page.getByText(/ok · answered in 12 ms/)).toBeVisible();
		expect(container.querySelector('.text-emerald-600')).not.toBeNull();
	});

	it('appends what a server offers when the check found anything', async () => {
		await render(ConnectionStatus, {
			checking: false,
			result: result({ detail: '2 tools', tools: ['search', 'fetch'] })
		});

		await expect.element(page.getByText('ok · 2 tools · search, fetch')).toBeVisible();
	});

	it('shows a red failure with the error', async () => {
		const { container } = await render(ConnectionStatus, {
			checking: false,
			result: result({ ok: false, detail: 'RuntimeError: refused' })
		});

		await expect.element(page.getByText('failed · RuntimeError: refused')).toBeVisible();
		expect(container.querySelector('.text-destructive')).not.toBeNull();
	});

	it('prefers the spinner over a stale result while re-checking', async () => {
		const { container } = await render(ConnectionStatus, {
			checking: true,
			result: result({ ok: false, detail: 'stale failure' })
		});

		expect(container.querySelector('.animate-spin')).not.toBeNull();
		expect(container.textContent).not.toContain('stale failure');
	});
});
