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

function settings(enabled: boolean, timeoutSeconds = 60) {
	api.getSettings.mockResolvedValue({
		config: { ask: { enabled, timeout_seconds: timeoutSeconds } }
	});
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

	it('renders the answer as markdown', async () => {
		api.ask.mockResolvedValue({
			found: true,
			question: 'k3s?',
			note_ids: [],
			hits: [],
			entry_id: '',
			message:
				'## Answer\n\nThe node is **elitedesk**:\n\n- runs k3s\n- see [the note](/p/Test)\n\n```bash\nkubectl get nodes\n```'
		});
		await render(Ask);

		await page.getByPlaceholder('What do you want to know?').fill('k3s?');
		await page.getByRole('button', { name: 'Ask' }).click();

		await expect.element(page.getByRole('heading', { name: 'Answer' })).toBeVisible();
		await expect.element(page.getByText('elitedesk').first()).toBeVisible();
		await expect.element(page.getByRole('listitem').first()).toHaveTextContent('runs k3s');
		await expect
			.element(page.getByRole('link', { name: 'the note' }))
			.toHaveAttribute('href', '/p/Test');
		// fenced code becomes a real block, not a raw paragraph
		expect(document.querySelector('article.wiki-body pre code')).not.toBeNull();
	});

	it('sanitises the answer before rendering it', async () => {
		api.ask.mockResolvedValue({
			found: true,
			question: 'x',
			note_ids: [],
			hits: [],
			entry_id: '',
			message: 'ok <script>window.__pwned = true</script> [x](javascript:alert(1))'
		});
		await render(Ask);

		await page.getByPlaceholder('What do you want to know?').fill('x?');
		await page.getByRole('button', { name: 'Ask' }).click();

		await expect.element(page.getByText(/ok/).first()).toBeVisible();
		const article = document.querySelector('article.wiki-body');
		expect(article?.querySelector('script')).toBeNull();
		expect(article?.innerHTML).not.toContain('javascript:');
		expect((window as unknown as { __pwned?: boolean }).__pwned).toBeUndefined();
	});

	it('spins while the run is in flight and reports the configured cap', async () => {
		settings(true, 90);
		let release: (answer: unknown) => void = () => {};
		api.ask.mockImplementation(
			() =>
				new Promise((resolve) => {
					release = resolve;
				})
		);
		await render(Ask);

		await page.getByPlaceholder('What do you want to know?').fill('k3s?');
		await page.getByRole('button', { name: 'Ask' }).click();

		// While pending: spinner copy, busy state, and the cap from the settings.
		await expect.element(page.getByRole('button', { name: /Thinking/ })).toBeVisible();
		await expect
			.element(page.getByRole('button', { name: /Thinking/ }))
			.toHaveAttribute('aria-busy', 'true');
		await expect.element(page.getByText(/this can take up to 90s/)).toBeVisible();

		release({
			found: true,
			question: 'k3s?',
			note_ids: [],
			hits: [],
			entry_id: '',
			message: 'answered'
		});
		await expect.element(page.getByText('answered')).toBeVisible();
		expect(page.getByRole('button', { name: /Thinking/ }).elements()).toHaveLength(0);
	});

	it('shows a timed-out run inline, keeping the question', async () => {
		api.ask.mockRejectedValue(new Error('the librarian did not finish within 60s'));
		await render(Ask);

		await page.getByPlaceholder('What do you want to know?').fill('k3s?');
		await page.getByRole('button', { name: 'Ask' }).click();

		await expect.element(page.getByText('the librarian did not finish within 60s')).toBeVisible();
		// the question stays so it can be retried or reworded
		await expect.element(page.getByPlaceholder('What do you want to know?')).toHaveValue('k3s?');
	});

	it('falls back to 60s when the payload predates the timeout field', async () => {
		api.getSettings.mockResolvedValue({ config: { ask: { enabled: true } } });
		api.ask.mockImplementation(() => new Promise(() => {}));
		await render(Ask);

		await page.getByPlaceholder('What do you want to know?').fill('k3s?');
		await page.getByRole('button', { name: 'Ask' }).click();

		await expect.element(page.getByText(/this can take up to 60s/)).toBeVisible();
	});

	it('shows a signpost instead of the form when asking is disabled', async () => {
		settings(false);
		await render(Ask);

		await expect.element(page.getByText(/Asking is disabled in the settings/)).toBeVisible();
		expect(page.getByPlaceholder('What do you want to know?').elements()).toHaveLength(0);
		expect(api.ask).not.toHaveBeenCalled();
	});
});
