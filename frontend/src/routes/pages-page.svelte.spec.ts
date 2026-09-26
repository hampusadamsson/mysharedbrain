import { beforeEach, describe, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import { render } from 'vitest-browser-svelte';
import Pages from './+page.svelte';
import type { Directory } from '$lib/api/client';

const api = vi.hoisted(() => ({ browse: vi.fn(), importNotes: vi.fn() }));
const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }));

vi.mock('$lib/api/client', async () => {
	const actual = await vi.importActual<typeof import('$lib/api/client')>('$lib/api/client');
	return { ...actual, api };
});

vi.mock('svelte-sonner', () => ({ toast }));

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

	it('toggles listing order between A–Z and Z–A', async () => {
		respond({ folders: [], notes: ['b-note', 'a-note'] });

		await render(Pages);

		const links = () =>
			page
				.getByRole('link', { name: /-note/ })
				.elements()
				.map((el) => el.getAttribute('href'));
		await expect.poll(links).toEqual(['/p/a-note', '/p/b-note']);
		await expect.element(page.getByRole('button', { name: 'Sort Z to A' })).toBeVisible();

		await page.getByRole('button', { name: 'Sort Z to A' }).click();
		await expect.poll(links).toEqual(['/p/b-note', '/p/a-note']);
		await expect.element(page.getByRole('button', { name: 'Sort A to Z' })).toBeVisible();
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

	it('imports the chosen files with replacement on by default', async () => {
		respond();
		api.importNotes.mockResolvedValue({ created: ['one'], updated: [], skipped: [], errors: {} });

		const { container } = await render(Pages);

		const picker = container.querySelector(
			'input[type=file]:not([webkitdirectory])'
		) as HTMLInputElement;
		const data = new DataTransfer();
		data.items.add(new File(['# One\n'], 'one.md', { type: 'text/markdown' }));
		picker.files = data.files;
		picker.dispatchEvent(new Event('change', { bubbles: true }));

		await expect.poll(() => api.importNotes).toHaveBeenCalled();
		const [, prefix, overwrite] = api.importNotes.mock.calls.at(-1) as [File[], string, boolean];
		expect(prefix).toBe('');
		expect(overwrite).toBe(true);
		await expect.element(page.getByText('1 new')).toBeVisible();
	});

	it('leaves existing pages alone when replacement is switched off', async () => {
		respond();
		api.importNotes.mockResolvedValue({ created: [], updated: [], skipped: ['one'], errors: {} });

		const { container } = await render(Pages);

		await page.getByRole('checkbox', { name: 'Replace pages that already exist' }).click();
		await expect
			.element(page.getByRole('checkbox', { name: 'Replace pages that already exist' }))
			.not.toBeChecked();

		const picker = container.querySelector(
			'input[type=file]:not([webkitdirectory])'
		) as HTMLInputElement;
		const data = new DataTransfer();
		data.items.add(new File(['# One\n'], 'one.md', { type: 'text/markdown' }));
		picker.files = data.files;
		picker.dispatchEvent(new Event('change', { bubbles: true }));

		await expect.poll(() => api.importNotes).toHaveBeenCalled();
		expect((api.importNotes.mock.calls.at(-1) as [File[], string, boolean])[2]).toBe(false);
		// a skip is reported as a skip, not as "nothing imported"
		await expect.element(page.getByText('1 skipped')).toBeVisible();
	});

	it('reports a failed file alongside the ones that landed', async () => {
		respond();
		api.importNotes.mockResolvedValue({
			created: ['one'],
			updated: [],
			skipped: [],
			errors: { 'bad.bin': 'not UTF-8 text' }
		});

		const { container } = await render(Pages);

		const picker = container.querySelector(
			'input[type=file]:not([webkitdirectory])'
		) as HTMLInputElement;
		const data = new DataTransfer();
		data.items.add(new File(['x'], 'one.md'));
		picker.files = data.files;
		picker.dispatchEvent(new Event('change', { bubbles: true }));

		await expect.element(page.getByText('1 new, 1 failed')).toBeVisible();
		await expect.element(page.getByText('bad.bin')).toBeVisible();
		await expect.element(page.getByText('not UTF-8 text')).toBeVisible();
	});

	it('refuses an oversized selection out loud instead of doing nothing', async () => {
		respond();

		const { container } = await render(Pages);

		const picker = container.querySelector(
			'input[type=file]:not([webkitdirectory])'
		) as HTMLInputElement;
		const data = new DataTransfer();
		for (let i = 0; i < 251; i++) data.items.add(new File(['x'], `n${i}.md`));
		picker.files = data.files;
		picker.dispatchEvent(new Event('change', { bubbles: true }));

		await expect
			.poll(() => toast.error)
			.toHaveBeenCalledWith(expect.stringContaining('the limit is 250 per import'));
		// and nothing was sent
		expect(api.importNotes).not.toHaveBeenCalled();
	});

	it('opens the import dialog and refreshes when it finishes', async () => {
		respond();
		api.importNotes.mockResolvedValue({ created: ['one'], updated: [], skipped: [], errors: {} });
		respond({ notes: ['one'] });

		const { container } = await render(Pages);

		const picker = container.querySelector(
			'input[type=file]:not([webkitdirectory])'
		) as HTMLInputElement;
		const data = new DataTransfer();
		data.items.add(new File(['# One\n'], 'one.md', { type: 'text/markdown' }));
		picker.files = data.files;
		picker.dispatchEvent(new Event('change', { bubbles: true }));

		await expect.element(page.getByText('Import finished')).toBeVisible();
		await expect.element(page.getByText('1 new')).toBeVisible();
		// the listing reloaded, so the new page is there behind the dialog
		await expect.poll(() => api.browse.mock.calls.length).toBeGreaterThan(1);
		await expect.element(page.getByRole('link', { name: /one/ })).toBeVisible();
	});

	it('shows the failure instead of an empty vault when the read fails', async () => {
		api.browse.mockRejectedValue(new Error('vault unavailable'));

		await render(Pages);

		await expect.element(page.getByText('vault unavailable')).toBeVisible();
		// an error is not an empty vault: do not invite a first page
		expect(page.getByText('Select a page, or create one').elements()).toHaveLength(0);
	});
});
