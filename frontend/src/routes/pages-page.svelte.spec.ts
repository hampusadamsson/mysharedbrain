import { beforeEach, describe, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import { render } from 'vitest-browser-svelte';
import Pages from './+page.svelte';
import type { Directory } from '$lib/api/client';

const api = vi.hoisted(() => ({ browse: vi.fn() }));

vi.mock('$lib/api/client', async () => {
	const actual = await vi.importActual<typeof import('$lib/api/client')>('$lib/api/client');
	return { ...actual, api };
});

vi.mock('svelte-sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

function respond(dir: Partial<Directory> = {}) {
	api.browse.mockResolvedValue({ folders: [], notes: [], ...dir });
}

beforeEach(() => {
	vi.clearAllMocks();
	respond();
});

describe('the Pages view', () => {
	it('browses the vault root instead of offering to create a page', async () => {
		respond({ folders: ['projects', 'admin'], notes: ['Test', 'todo'] });

		await render(Pages);

		// it asks the API for the root, not for a note
		await expect.poll(() => api.browse).toHaveBeenCalledWith('');
		// folders and notes are listed, with links into each
		await expect
			.element(page.getByRole('link', { name: /projects/ }))
			.toHaveAttribute('href', '/p/projects');
		await expect
			.element(page.getByRole('link', { name: /todo/ }))
			.toHaveAttribute('href', '/p/todo');
		await expect.element(page.getByText(/\d+ pages and \d+ folders at the root/)).toBeVisible();
		// and the create prompt is not what greets you
		expect(page.getByText('Select a page, or create one').elements()).toHaveLength(0);
	});

	it('lists a note that is also a folder once, as the folder row', async () => {
		respond({ folders: ['projects'], notes: ['projects', 'projects/homelab'] });

		await render(Pages);

		await expect
			.element(page.getByRole('link', { name: /projects/ }))
			.toHaveAttribute('href', '/p/projects');
		expect(page.getByRole('link', { name: /projects/ }).elements()).toHaveLength(1);
	});

	it('offers to create the first page when the vault is empty', async () => {
		respond();

		await render(Pages);

		await expect.element(page.getByText('Select a page, or create one')).toBeVisible();
		await expect.element(page.getByRole('button', { name: 'Create page' })).toBeVisible();
	});

	it('still offers upload on an empty vault, where import is the whole point', async () => {
		// the controls used to live in the "has pages" branch, so a fresh vault —
		// the one case importing exists for — had no way to import
		respond();

		await render(Pages);

		await expect.element(page.getByRole('button', { name: 'Upload files' })).toBeVisible();
		await expect.element(page.getByRole('button', { name: 'Upload folder' })).toBeVisible();
		await expect
			.element(page.getByText('Nothing here yet — create a page, or import files.'))
			.toBeVisible();
	});

	it('shows the failure instead of an empty vault when the read fails', async () => {
		api.browse.mockRejectedValue(new Error('vault unavailable'));

		await render(Pages);

		await expect.element(page.getByText('vault unavailable')).toBeVisible();
		// an error is not an empty vault: do not invite a first page
		expect(page.getByText('Select a page, or create one').elements()).toHaveLength(0);
	});
});
