import { beforeEach, describe, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import { render } from 'vitest-browser-svelte';
import { ModeWatcher } from 'mode-watcher';
import TopBar from './TopBar.svelte';

// The top bar talks to the API and the SvelteKit router; both are irrelevant
// here — this test only covers the theme toggle.
vi.mock('$lib/api/client', async () => {
	const actual = await vi.importActual<typeof import('$lib/api/client')>('$lib/api/client');
	return {
		...actual,
		api: { ...actual.api, search: vi.fn(async () => ({ names: [], content: [] })) }
	};
});

vi.mock('$app/navigation', () => ({ goto: vi.fn() }));

const isDark = () => document.documentElement.classList.contains('dark');

async function mount() {
	// ModeWatcher owns the <html> class list and localStorage; TopBar only asks
	// it to flip, so both are always mounted together.
	await render(ModeWatcher, { defaultMode: 'light' });
	await render(TopBar, { onmenu: vi.fn() });
}

beforeEach(() => {
	localStorage.clear();
	document.documentElement.classList.remove('dark');
});

describe('theme toggle', () => {
	it('flips <html> to dark and persists the choice', async () => {
		await mount();
		await page.getByRole('button', { name: 'Switch to dark theme' }).click();

		await expect.poll(isDark).toBe(true);
		expect(localStorage.getItem('mode-watcher-mode')).toBe('dark');
	});

	it('flips back to light and offers the dark icon again', async () => {
		await mount();
		await page.getByRole('button', { name: 'Switch to dark theme' }).click();
		await expect.poll(isDark).toBe(true);

		await page.getByRole('button', { name: 'Switch to light theme' }).click();

		await expect.poll(isDark).toBe(false);
		expect(localStorage.getItem('mode-watcher-mode')).toBe('light');
	});
});
