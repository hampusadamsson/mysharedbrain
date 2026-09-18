import { beforeEach, describe, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import { render } from 'vitest-browser-svelte';
import Ask from './+page.svelte';

const api = vi.hoisted(() => ({
	ask: vi.fn(),
	getSettings: vi.fn()
}));
const space = vi.hoisted(() => ({ refreshPending: vi.fn(), refreshNotes: vi.fn() }));

vi.mock('$lib/api/client', async () => {
	const actual = await vi.importActual<typeof import('$lib/api/client')>('$lib/api/client');
	return { ...actual, api };
});

vi.mock('$lib/stores/space.svelte', () => ({ space, ...space }));

function settings(enabled: boolean) {
	api.getSettings.mockResolvedValue({ config: { ask: { enabled } } });
}

beforeEach(() => {
	vi.clearAllMocks();
	settings(true);
	api.ask.mockResolvedValue({
		found: true,
		question: 'k3s?',
		note_ids: ['homelab'],
		hits: [],
		entry_id: '',
		message: 'homelab runs k3s.'
	});
});

describe('ask the librarian', () => {
	it('asks and shows the answer with its evidence', async () => {
		await render(Ask);

		await page.getByPlaceholder('What do you want to know?').fill('k3s?');
		await page.getByRole('button', { name: 'Ask' }).click();

		await expect.poll(() => api.ask).toHaveBeenCalledWith('k3s?');
		await expect.element(page.getByText('homelab runs k3s.')).toBeVisible();
		await expect.element(page.getByRole('link', { name: 'homelab' })).toBeVisible();
	});

	it('shows a signpost instead of the form when asking is disabled', async () => {
		settings(false);
		await render(Ask);

		await expect.element(page.getByText(/Asking is disabled in the settings/)).toBeVisible();
		expect(page.getByPlaceholder('What do you want to know?').elements()).toHaveLength(0);
		expect(api.ask).not.toHaveBeenCalled();
	});
});
