import { beforeEach, describe, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import { render } from 'vitest-browser-svelte';
import ImportDialog from './ImportDialog.svelte';

const api = vi.hoisted(() => ({ importNotes: vi.fn() }));
const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }));

vi.mock('$lib/api/client', async () => {
	const actual = await vi.importActual<typeof import('$lib/api/client')>('$lib/api/client');
	return { ...actual, api };
});
vi.mock('svelte-sonner', () => ({ toast }));

function files(count: number, name = (i: number) => `n${i}.md`): File[] {
	return Array.from(
		{ length: count },
		(_, i) => new File(['# x\n'], name(i), { type: 'text/markdown' })
	);
}

function ok(
	created: string[],
	extra: Partial<{ updated: string[]; skipped: string[]; errors: Record<string, string> }> = {}
) {
	return { created, updated: [], skipped: [], errors: {}, ...extra };
}

beforeEach(() => {
	vi.clearAllMocks();
});

describe('import dialog', () => {
	it('reports progress per batch and the result when it finishes', async () => {
		// 60 files → 3 batches of 25/25/10
		api.importNotes.mockImplementation(async (batch: File[]) =>
			ok(batch.map((f) => f.name.replace('.md', '')))
		);

		const onfinished = vi.fn();
		await render(ImportDialog, { files: files(60), overwrite: true, onfinished, onclose: vi.fn() });

		await expect.poll(() => api.importNotes).toHaveBeenCalledTimes(3);
		const sizes = api.importNotes.mock.calls.map((c) => (c[0] as File[]).length);
		expect(sizes).toEqual([25, 25, 10]);
		await expect.element(page.getByText('60 new')).toBeVisible();
		await expect.element(page.getByText('Import finished')).toBeVisible();
		expect(onfinished).toHaveBeenCalled();
	});

	it('lists the files that failed, and still imports the rest', async () => {
		api.importNotes.mockResolvedValue(ok(['good'], { errors: { 'bad.bin': 'not UTF-8 text' } }));

		await render(ImportDialog, {
			files: files(2, (i) => (i === 0 ? 'good.md' : 'bad.bin')),
			overwrite: true,
			onfinished: vi.fn(),
			onclose: vi.fn()
		});

		await expect.element(page.getByText('1 file not imported')).toBeVisible();
		await expect.element(page.getByText('bad.bin')).toBeVisible();
		await expect.element(page.getByText('not UTF-8 text')).toBeVisible();
		await expect.element(page.getByText('1 new, 1 failed')).toBeVisible();
	});

	it('keeps going when a whole batch fails, and names the reason', async () => {
		api.importNotes
			.mockRejectedValueOnce(new Error('too many files: max 250'))
			.mockResolvedValueOnce(ok(['later']));

		await render(ImportDialog, {
			files: files(30),
			overwrite: true,
			onfinished: vi.fn(),
			onclose: vi.fn()
		});

		await expect.poll(() => api.importNotes).toHaveBeenCalledTimes(2);
		await expect.element(page.getByText('25 files not imported')).toBeVisible();
		await expect.element(page.getByText('too many files: max 250').first()).toBeVisible();
		await expect.element(page.getByText('1 new, 25 failed')).toBeVisible();
	});

	it('passes the replacement choice through', async () => {
		api.importNotes.mockResolvedValue(ok([], { skipped: ['one'] }));

		await render(ImportDialog, {
			files: files(1),
			overwrite: false,
			onfinished: vi.fn(),
			onclose: vi.fn()
		});

		await expect.poll(() => api.importNotes).toHaveBeenCalledWith(expect.any(Array), '', false);
		await expect.element(page.getByText('1 skipped')).toBeVisible();
	});
});
