import { beforeEach, describe, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import { render } from 'vitest-browser-svelte';
import NoteView from './NoteView.svelte';
import type { Note } from '$lib/api/client';

const api = vi.hoisted(() => ({
	updateNote: vi.fn(),
	moveNote: vi.fn(),
	deleteNote: vi.fn(),
	backlinks: vi.fn(async () => ({ links: [] }))
}));

vi.mock('$lib/api/client', async () => {
	const actual = await vi.importActual<typeof import('$lib/api/client')>('$lib/api/client');
	return { ...actual, api };
});

const note: Note = { id: 'projects/homelab', content: '# Homelab\n\nk3s runs on elitedesk' };

function setup(onchanged = vi.fn(async () => {})) {
	return render(NoteView, { note, onchanged, onerror: vi.fn() });
}

beforeEach(() => {
	vi.clearAllMocks();
	api.backlinks.mockResolvedValue({ links: [] });
});

describe('NoteView', () => {
	it('renders markdown content in view mode', async () => {
		await setup();
		// rendered markdown heading (distinct from the page-title heading)
		await expect.element(page.getByRole('heading', { name: 'Homelab', exact: true })).toBeVisible();
		await expect.element(page.getByText('k3s runs on elitedesk')).toBeVisible();
	});

	it('marks the article so wide markdown is contained (wiki-body + table fix)', async () => {
		const { container } = await render(NoteView, {
			note: { id: 'wide', content: '| a | b |\n| - | - |\n| 1 | 2 |\n' },
			onchanged: vi.fn(async () => {}),
			onerror: vi.fn()
		});
		const article = container.querySelector('article');
		expect(article?.classList.contains('wiki-body')).toBe(true);
		expect(article?.querySelector('table')).not.toBeNull();
	});

	it('saves content without navigating when the id is unchanged', async () => {
		api.updateNote.mockResolvedValue({ id: note.id, content: 'edited' });
		const onchanged = vi.fn(async () => {});
		await render(NoteView, { note, onchanged, onerror: vi.fn() });

		await page.getByRole('button', { name: 'Edit' }).click();
		await page.getByRole('textbox', { name: 'Page content' }).fill('edited body');
		await page.getByRole('button', { name: 'Save' }).click();

		await expect.element(page.getByText('edited body')).toBeVisible();
		expect(api.updateNote).toHaveBeenCalledWith(note.id, 'edited body');
		expect(api.moveNote).not.toHaveBeenCalled();
		expect(onchanged).not.toHaveBeenCalled();
	});

	it('renames via move and navigates to the new id', async () => {
		api.updateNote.mockResolvedValue({ id: note.id, content: 'x' });
		api.moveNote.mockResolvedValue({ id: 'shopping', content: 'x' });
		const onchanged = vi.fn(async () => {});
		await render(NoteView, { note, onchanged, onerror: vi.fn() });

		await page.getByRole('button', { name: 'Edit' }).click();
		await page.getByRole('textbox', { name: 'Page id' }).fill('shopping');
		await page.getByRole('button', { name: 'Save' }).click();

		expect(api.moveNote).toHaveBeenCalledWith(note.id, 'shopping');
		expect(onchanged).toHaveBeenCalledWith('shopping');
	});

	it('shows an inline error and stays in edit mode on a rename conflict', async () => {
		api.updateNote.mockResolvedValue({ id: note.id, content: 'x' });
		api.moveNote.mockRejectedValue(new Error('note already exists'));
		const onerror = vi.fn();
		await render(NoteView, { note, onchanged: vi.fn(async () => {}), onerror });

		await page.getByRole('button', { name: 'Edit' }).click();
		await page.getByRole('textbox', { name: 'Page id' }).fill('taken');
		await page.getByRole('button', { name: 'Save' }).click();

		await expect.element(page.getByText('note already exists')).toBeVisible();
		await expect.element(page.getByRole('button', { name: 'Save' })).toBeVisible();
	});

	it('rejects an empty id before calling the API', async () => {
		await setup();
		await page.getByRole('button', { name: 'Edit' }).click();
		await page.getByRole('textbox', { name: 'Page id' }).fill('   ');
		await page.getByRole('button', { name: 'Save' }).click();

		await expect.element(page.getByText('Page id must not be empty.')).toBeVisible();
		expect(api.updateNote).not.toHaveBeenCalled();
	});

	it('deletes after confirmation and reports a null id', async () => {
		api.deleteNote.mockResolvedValue(null);
		const onchanged = vi.fn(async () => {});
		await render(NoteView, { note, onchanged, onerror: vi.fn() });

		await page.getByRole('button', { name: 'Delete' }).click();
		await page.getByRole('button', { name: 'Delete' }).last().click();

		expect(api.deleteNote).toHaveBeenCalledWith(note.id);
		expect(onchanged).toHaveBeenCalledWith(null);
	});
});
