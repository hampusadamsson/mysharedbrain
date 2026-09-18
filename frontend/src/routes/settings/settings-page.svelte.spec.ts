import { beforeEach, describe, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import { render } from 'vitest-browser-svelte';
import Settings from './+page.svelte';
// Without the stylesheet the layout classes do nothing, so geometry assertions
// below would pass vacuously (the entry sits one level up).
import '../layout.css';
import type { BrainConfigDoc, Settings as SettingsPayload } from '$lib/api/client';

const api = vi.hoisted(() => ({
	getSettings: vi.fn(),
	updateSettings: vi.fn(),
	testMcpServer: vi.fn(),
	testModel: vi.fn(),
	modelProviders: vi.fn(),
	listNotes: vi.fn(),
	createNote: vi.fn(),
	search: vi.fn(),
	exportSettings: vi.fn(),
	importSettings: vi.fn()
}));

/** The catalog the server reports: what this install can import. */
const PROVIDERS = [
	{ name: 'openai', available: true, url_param: 'base_url', api_version_param: '', hint: '' },
	{
		name: 'azure',
		available: true,
		url_param: 'azure_endpoint',
		api_version_param: 'api_version',
		hint: ''
	},
	{
		name: 'cerebras',
		available: true,
		url_param: '',
		api_version_param: '',
		hint: ''
	},
	{
		name: 'ollama',
		available: true,
		url_param: 'base_url',
		api_version_param: '',
		hint: ''
	},
	{
		name: 'anthropic',
		available: false,
		url_param: '',
		api_version_param: '',
		hint: 'Please install the `anthropic` package to use the Anthropic provider'
	}
];
const nav = vi.hoisted(() => ({ search: '' }));
const goto = vi.hoisted(() => vi.fn());

vi.mock('$lib/api/client', async () => {
	const actual = await vi.importActual<typeof import('$lib/api/client')>('$lib/api/client');
	return { ...actual, api };
});

// The selected tab is the `tab` query param, so the tests drive the same input
// the browser does on refresh: the URL.
vi.mock('$app/state', () => ({
	page: {
		get url() {
			return new URL(`http://localhost/settings${nav.search}`);
		}
	}
}));

vi.mock('$app/navigation', () => ({ goto }));

/** The shipped schedule: three examples, all disabled. */
const SHIPPED_JOBS = [
	{
		id: 'capture-triage',
		name: 'Capture triage',
		description: '',
		enabled: false,
		every: '4h',
		cron: null,
		instructions: 'Triage the pending capture queue.',
		instructions_file: null,
		tools: null,
		mcp_servers: null,
		max_steps: null
	},
	{
		id: 'vault-sweep',
		name: 'Vault maintenance sweep',
		description: '',
		enabled: false,
		every: null,
		cron: '0 3 */2 * *',
		instructions: '',
		instructions_file: 'jobs/sweep.md',
		tools: ['list_notes', 'read_note'],
		mcp_servers: null,
		max_steps: null
	},
	{
		id: 'source-check',
		name: 'Source freshness',
		description: 'Re-check note sources.',
		enabled: false,
		every: '6d',
		cron: null,
		instructions: '',
		instructions_file: null,
		tools: null,
		mcp_servers: null,
		max_steps: null
	}
] satisfies BrainConfigDoc['jobs'];

function payload(jobs: BrainConfigDoc['jobs'] = SHIPPED_JOBS): SettingsPayload {
	const config: BrainConfigDoc = {
		agent: {
			model: 'openai:gpt-4o-mini',
			provider: { name: '', base_url: '', api_version: '', options: {} },
			api_key: '',
			api_key_env: 'OPENAI_API_KEY',
			instructions_file: 'librarian.md',
			instructions: '',
			max_steps: 20,
			temperature: 0.2
		},
		scheduler: { enabled: false, tick_seconds: 30, run_on_start: false },
		admin: {
			dir: 'admin',
			layout_template: 'admin/templates/layout',
			templates: {},
			prompts: {}
		},
		ask: {
			enabled: true,
			instructions_file: null,
			tools: null,
			mcp_servers: null,
			max_steps: null
		},
		tools: { delete_note: { enabled: false } },
		mcp_servers: [
			{
				name: 'reachable',
				transport: 'http',
				url: 'https://a.example.com/mcp',
				headers: {},
				enabled: true,
				insecure: false
			},
			{
				name: 'broken',
				transport: 'http',
				url: 'https://b.example.com/mcp',
				headers: {},
				enabled: true,
				insecure: false
			}
		],
		jobs,
		metadata: {}
	};
	return {
		config,
		jobs: jobs.map((j) => ({
			id: j.id,
			name: j.name || j.id,
			enabled: j.enabled,
			schedule: j.every ?? j.cron ?? '',
			next_run: '',
			last_run: '',
			last_status: ''
		})),
		tools: [
			{ name: 'read_note', description: 'Read a note', enabled: true },
			{ name: 'patch_note', description: 'Patch a section', enabled: true },
			{ name: 'delete_note', description: 'Soft-delete a note', enabled: false }
		],
		config_path: '/data/brain.yaml',
		config_source: 'database',
		api_key_env: 'OPENAI_API_KEY',
		api_key_configured: false
	};
}

beforeEach(() => {
	vi.clearAllMocks();
	nav.search = '';
	api.getSettings.mockResolvedValue(payload());
	api.modelProviders.mockResolvedValue({
		providers: PROVIDERS,
		current: 'openai',
		model: 'openai:gpt-4o-mini'
	});
	api.listNotes.mockResolvedValue({ notes: [] });
	api.createNote.mockImplementation(async (id: string, content = '') => ({
		id,
		content
	}));
});
/** Render with the tab the way a refresh would arrive: via the URL. */
async function openTab(name: string) {
	nav.search = name === 'agent' ? '' : `?tab=${name}`;
	await render(Settings);
}

async function openJobs() {
	await openTab('jobs');
}

/** Job badges only: the MCP tab renders enabled/disabled badges too. */
function jobsPanel() {
	// Only the active panel is mounted, so this is the Jobs tab's content.
	return page.getByRole('tabpanel');
}

async function openMcp() {
	await openTab('mcp');
}

describe('settings · mcp connect check', () => {
	it('shows a green ok with the tools when the server answers', async () => {
		api.testMcpServer.mockResolvedValue({
			name: 'reachable',
			ok: true,
			detail: '2 tools',
			tools: ['search', 'fetch']
		});
		await openMcp();

		await page.getByRole('button', { name: 'Test' }).first().click();

		await expect.element(page.getByText(/ok · 2 tools · search, fetch/)).toBeVisible();
	});

	it('shows a red failure with the error', async () => {
		api.testMcpServer.mockResolvedValue({
			name: 'broken',
			ok: false,
			detail: 'RuntimeError: Client failed to connect',
			tools: []
		});
		await openMcp();

		await page.getByRole('button', { name: 'Test' }).nth(1).click();

		await expect
			.element(page.getByText(/failed · RuntimeError: Client failed to connect/))
			.toBeVisible();
	});

	it('reports a rejected check (bad config) as a red line too', async () => {
		api.testMcpServer.mockRejectedValue(new Error('url must start with http://'));
		await openMcp();

		await page.getByRole('button', { name: 'Test' }).first().click();

		await expect.element(page.getByText(/failed · url must start with http/)).toBeVisible();
	});

	it('checks every enabled server on save', async () => {
		api.testMcpServer.mockResolvedValue({
			name: 'x',
			ok: true,
			detail: '1 tool',
			tools: ['t']
		});
		// echo what was saved, the way the real endpoint does
		api.updateSettings.mockImplementation(async (config: BrainConfigDoc) => ({
			...payload(),
			config
		}));
		await openMcp();

		// make the form dirty, then save
		await page.getByRole('button', { name: 'Disable' }).first().click();
		await page.getByRole('button', { name: 'Save' }).click();

		// one server was just disabled, so only the other is probed
		await expect.poll(() => api.testMcpServer).toHaveBeenCalledTimes(1);
		expect(api.testMcpServer).toHaveBeenCalledWith(
			expect.objectContaining({ name: 'broken', enabled: true })
		);
	});
});

describe('settings · mcp insecure', () => {
	it('offers a certificate-verification checkbox per server, off by default', async () => {
		await openMcp();

		const boxes = page.getByRole('checkbox', { name: /skip certificate verification/i });
		await expect.element(boxes.first()).toBeVisible();
		expect(boxes.elements()).toHaveLength(2);
		await expect.element(boxes.first()).not.toBeChecked();
	});

	it('checking it marks the form unsaved and persists insecure', async () => {
		api.updateSettings.mockImplementation(async (config: BrainConfigDoc) => ({
			...(await payload()),
			config
		}));
		await openMcp();

		await page
			.getByRole('checkbox', { name: /skip certificate verification/i })
			.first()
			.click();

		await expect.element(page.getByRole('button', { name: 'Save' })).toBeEnabled();
		await page.getByRole('button', { name: 'Save' }).click();

		await expect
			.poll(() => api.updateSettings)
			.toHaveBeenCalledWith(
				expect.objectContaining({
					mcp_servers: expect.arrayContaining([expect.objectContaining({ insecure: true })])
				})
			);
	});
});

describe('settings · job mcp servers', () => {
	it('lists the registered servers as toggles, not free text', async () => {
		await openJobs();

		expect(page.getByText(/Restrict MCP servers/).elements()).toHaveLength(0);
		await expect.element(page.getByRole('button', { name: 'reachable' }).first()).toBeVisible();
		await expect.element(page.getByRole('button', { name: 'broken' }).first()).toBeVisible();
		await expect.element(page.getByText(/every enabled server/).first()).toBeVisible();
	});

	it('narrows a job to specific servers and resets to all', async () => {
		await openJobs();

		await page.getByRole('button', { name: 'broken' }).first().click();

		await expect.element(page.getByText('1 of 2 servers')).toBeVisible();
		await expect
			.element(page.getByRole('button', { name: 'broken' }).first())
			.toHaveAttribute('aria-pressed', 'false');

		await page.getByRole('button', { name: 'Use all enabled' }).first().click();

		await expect.element(page.getByText(/every enabled server/).first()).toBeVisible();
	});

	it('collapses back to unrestricted when every enabled server is chosen', async () => {
		const job = { ...SHIPPED_JOBS[0], mcp_servers: ['reachable'] };
		api.getSettings.mockResolvedValue(payload([job]));
		await openJobs();
		await expect.element(page.getByText('1 of 2 servers')).toBeVisible();

		await page.getByRole('button', { name: 'broken' }).click();

		await expect.element(page.getByText(/every enabled server/).first()).toBeVisible();
	});

	it('says so when nothing is registered', async () => {
		const bare = payload();
		bare.config.mcp_servers = [];
		api.getSettings.mockResolvedValue(bare);
		await openJobs();

		await expect.element(page.getByText(/No MCP servers registered/).first()).toBeVisible();
	});

	it('drops a removed server from the jobs that named it', async () => {
		const job = { ...SHIPPED_JOBS[0], mcp_servers: ['broken'] };
		api.getSettings.mockResolvedValue(payload([job]));
		await openTab('mcp');

		await page.getByRole('button', { name: 'Remove' }).nth(1).click();
		await page.getByRole('alertdialog').getByRole('button', { name: 'Remove' }).click();
		await page.getByRole('tab', { name: 'Jobs' }).click();

		// the reference is gone, so saving cannot fail validation
		await expect
			.element(page.getByText('no servers — this job gets no remote tools'))
			.toBeVisible();
	});
	it('shows where the settings are stored', async () => {
		await openTab('agent');

		await expect
			.element(page.getByText(/saved in the vault database · seed \/data\/brain.yaml/))
			.toBeVisible();
	});

	it('says when nothing has been saved yet', async () => {
		const seeded = payload();
		seeded.config_source = 'file';
		api.getSettings.mockResolvedValue(seeded);

		await openTab('agent');

		await expect
			.element(page.getByText(/read from the seed file \(nothing saved yet\)/))
			.toBeVisible();
	});
});

describe('settings · responsive card actions', () => {
	/** Boxes of the action slot, description and header of one named card. */
	function boxes(cardTitle: string) {
		const card = [...document.querySelectorAll<HTMLElement>('[data-slot="card"]')].find((c) =>
			c.querySelector('[data-slot="card-title"]')?.textContent?.includes(cardTitle)
		);
		if (!card) throw new Error(`card not found: ${cardTitle}`);
		const header = card.querySelector<HTMLElement>('[data-slot="card-header"]');
		const description = card.querySelector<HTMLElement>('[data-slot="card-description"]');
		const action = card.querySelector<HTMLElement>('[data-slot="card-action"]');
		if (!header || !description || !action) throw new Error(`incomplete card: ${cardTitle}`);
		return {
			header: header.getBoundingClientRect(),
			description: description.getBoundingClientRect(),
			action: action.getBoundingClientRect()
		};
	}

	it('puts the action on its own row below the text on a phone', async () => {
		api.exportSettings.mockResolvedValue('agent:\n  model: openai:gpt-4o-mini\n');
		await page.viewport(360, 900);
		await openTab('config');

		const { header, description, action } = boxes('Extract config');
		// below the description, not beside it
		expect(action.top).toBeGreaterThanOrEqual(description.bottom - 1);
		// and using the card's full inner width so the buttons can wrap
		expect(action.width).toBeGreaterThan(header.width * 0.7);
	});

	it('puts the action back in the top-right corner from sm up', async () => {
		api.exportSettings.mockResolvedValue('agent:\n  model: openai:gpt-4o-mini\n');
		await page.viewport(1280, 900);
		await openTab('config');

		const { header, description, action } = boxes('Extract config');
		// beside the text (top row), on the right edge of the header
		expect(action.top).toBeLessThan(description.bottom);
		expect(action.left).toBeGreaterThan(description.left);
		expect(Math.abs(action.right - (header.right - (description.left - header.left)))).toBeLessThan(
			8
		);
	});
});

describe('settings · model check', () => {
	it('offers a test button that reports the round trip', async () => {
		api.testModel.mockResolvedValue({
			name: 'openai:gpt-4o-mini',
			ok: true,
			detail: 'answered in 412 ms: ok',
			tools: []
		});
		await openTab('agent');

		await page.getByRole('button', { name: 'Test model' }).click();

		await expect.element(page.getByText(/ok · answered in 412 ms/)).toBeVisible();
		expect(api.testModel).toHaveBeenCalledWith(
			expect.objectContaining({ model: 'openai:gpt-4o-mini' })
		);
	});

	it('surfaces a provider failure in red', async () => {
		api.testModel.mockResolvedValue({
			name: 'openai:gpt-4o-mini',
			ok: false,
			detail: 'UserError: Set the `OPENAI_API_KEY` environment variable',
			tools: []
		});
		await openTab('agent');

		await page.getByRole('button', { name: 'Test model' }).click();

		await expect
			.element(page.getByText(/failed · UserError: Set the `OPENAI_API_KEY`/))
			.toBeVisible();
	});

	it('treats a rejected check as a red line too', async () => {
		api.testModel.mockRejectedValue(new Error('invalid config: max_steps'));
		await openTab('agent');

		await page.getByRole('button', { name: 'Test model' }).click();

		await expect.element(page.getByText(/failed · invalid config: max_steps/)).toBeVisible();
	});

	it('checks the model as well as every enabled server on save', async () => {
		api.testModel.mockResolvedValue({
			name: 'm',
			ok: true,
			detail: 'answered in 1 ms: ok',
			tools: []
		});
		api.testMcpServer.mockResolvedValue({
			name: 's',
			ok: true,
			detail: '1 tool',
			tools: ['t']
		});
		api.updateSettings.mockImplementation(async (config: BrainConfigDoc) => ({
			...payload(),
			config
		}));
		await openTab('mcp');

		await page.getByRole('button', { name: 'Disable' }).first().click();
		await page.getByRole('button', { name: 'Save' }).click();

		await expect.poll(() => api.testMcpServer).toHaveBeenCalledTimes(1);
		await expect.poll(() => api.testModel).toHaveBeenCalledTimes(1);
	});
});

describe('settings · model provider', () => {
	it('labels the endpoint field the way that provider names it', async () => {
		const azure = payload();
		azure.config.agent.model = 'gpt-4o';
		azure.config.agent.provider = {
			name: 'azure',
			base_url: 'https://x.openai.azure.com',
			api_version: '2024-10-21',
			options: {}
		};
		api.getSettings.mockResolvedValue(azure);

		await openTab('agent');

		// azure takes the endpoint as azure_endpoint, and needs an api version
		await expect.element(page.getByLabelText('Endpoint')).toHaveValue('https://x.openai.azure.com');
		await expect.element(page.getByLabelText('API version')).toHaveValue('2024-10-21');
	});

	it('hides the endpoint field for a provider that takes none', async () => {
		const bare = payload();
		bare.config.agent.model = 'llama-3.3-70b';
		bare.config.agent.provider = {
			name: 'cerebras',
			base_url: '',
			api_version: '',
			options: {}
		};
		api.getSettings.mockResolvedValue(bare);

		await openTab('agent');

		expect(page.getByLabelText('Base URL').elements()).toHaveLength(0);
	});

	it('shows the install hint for a provider that is not available', async () => {
		const missing = payload();
		missing.config.agent.model = 'claude-3-5';
		missing.config.agent.provider = {
			name: 'anthropic',
			base_url: '',
			api_version: '',
			options: {}
		};
		api.getSettings.mockResolvedValue(missing);

		await openTab('agent');

		await expect.element(page.getByText(/Please install the `anthropic` package/)).toBeVisible();
	});

	it('edits extra provider options by argument name', async () => {
		await openTab('agent');

		await page.getByRole('button', { name: 'Add option' }).click();
		await page.getByLabelText('Option name').fill('region');
		await page.getByLabelText('Option value').fill('eu-west-1');

		await expect.element(page.getByLabelText('Option value')).toHaveValue('eu-west-1');
		// and removing it takes the row away
		await page.getByRole('button', { name: 'Remove' }).click();
		await page.getByRole('alertdialog').getByRole('button', { name: 'Remove' }).click();
		expect(page.getByLabelText('Option name').elements()).toHaveLength(0);
	});

	it('passes the chosen provider and endpoint to the model check', async () => {
		const custom = payload();
		custom.config.agent.model = 'llama3.1';
		custom.config.agent.provider = {
			name: 'ollama',
			base_url: 'http://localhost:11434/v1',
			api_version: '',
			options: {}
		};
		api.getSettings.mockResolvedValue(custom);
		api.testModel.mockResolvedValue({
			name: 'llama3.1',
			ok: true,
			detail: 'answered in 30 ms: ok',
			tools: []
		});

		await openTab('agent');
		await page.getByRole('button', { name: 'Test model' }).click();

		await expect
			.poll(() => api.testModel)
			.toHaveBeenCalledWith(
				expect.objectContaining({
					model: 'llama3.1',
					provider: expect.objectContaining({
						name: 'ollama',
						base_url: 'http://localhost:11434/v1'
					})
				})
			);
	});
	it('shows the temperature default rather than an empty field', async () => {
		await openTab('agent');

		const temp = page.getByLabelText('Temperature');
		await expect.element(temp).toHaveValue(0.2);
		await expect.element(page.getByText(/Low by default \(0.2\)/)).toBeVisible();
	});

	it('clearing the temperature means "let the provider decide"', async () => {
		await openTab('agent');

		await page.getByLabelText('Temperature').fill('');

		await expect.element(page.getByLabelText('Temperature')).toHaveValue(null);
	});
});

describe('settings · tab in the url', () => {
	it('defaults to Agent with no param', async () => {
		await openTab('agent');

		await expect
			.element(page.getByRole('tab', { name: 'Agent' }))
			.toHaveAttribute('data-state', 'active');
	});

	it.each([
		['agent', 'Agent'],
		['ask', 'Ask'],
		['jobs', 'Jobs'],
		['tools', 'Tools'],
		['mcp', 'MCP servers']
	])('stays on %s after a refresh', async (name, label) => {
		await openTab(name);

		await expect
			.element(page.getByRole('tab', { name: label }))
			.toHaveAttribute('data-state', 'active');
	});

	it('ignores an unknown tab instead of rendering nothing', async () => {
		nav.search = '?tab=nonsense';
		await render(Settings);

		await expect
			.element(page.getByRole('tab', { name: 'Agent' }))
			.toHaveAttribute('data-state', 'active');
	});

	it('puts the tab in the url, replacing history rather than stacking it', async () => {
		await openTab('agent');

		await page.getByRole('tab', { name: 'Tools' }).click();

		await expect
			.poll(() => goto)
			.toHaveBeenCalledWith('?tab=tools', {
				replaceState: true,
				keepFocus: true,
				noScroll: true
			});
	});
});

describe('settings · jobs', () => {
	it('displays the shipped example schedule', async () => {
		await openJobs();

		await expect.element(page.getByText('Capture triage')).toBeVisible();
		await expect.element(page.getByText('Vault maintenance sweep')).toBeVisible();
		await expect.element(page.getByText('Source freshness')).toBeVisible();
	});

	it('shows every example as disabled, with nothing scheduled', async () => {
		await openJobs();

		expect(
			jobsPanel()
				.getByText(/^disabled$/)
				.elements()
		).toHaveLength(3);
		expect(
			jobsPanel()
				.getByText(/^enabled$/)
				.elements()
		).toHaveLength(0);
		// no job is due, so no next-run line anywhere in the Jobs tab
		expect(
			jobsPanel()
				.getByText(/^next /)
				.elements()
		).toHaveLength(0);
	});

	it('says plainly that nothing runs yet', async () => {
		await openJobs();

		await expect.element(page.getByText(/Nothing runs yet/)).toBeVisible();
		await expect.element(page.getByText(/the scheduler is off/)).toBeVisible();
		await expect.element(page.getByText(/every job is disabled/)).toBeVisible();
	});

	it('drops the notice once a job is enabled', async () => {
		await openJobs();

		await page.getByRole('checkbox', { name: 'Enable Capture triage' }).click();

		await expect.element(jobsPanel().getByText(/^enabled$/)).toBeVisible();
		// scheduler is still off, so the notice stays but stops blaming the jobs
		await expect.element(page.getByText(/Nothing runs yet/)).toBeVisible();
		expect(page.getByText(/every job is disabled/).elements()).toHaveLength(0);
	});

	it('renders enable as a checkbox per job, checked to match state', async () => {
		await openJobs();

		for (const name of ['Capture triage', 'Vault maintenance sweep', 'Source freshness']) {
			await expect.element(page.getByRole('checkbox', { name: `Enable ${name}` })).toBeVisible();
			await expect
				.element(page.getByRole('checkbox', { name: `Enable ${name}` }))
				.not.toBeChecked();
		}
	});

	it('unchecking an enabled job flips it back to disabled', async () => {
		const running = payload(
			SHIPPED_JOBS.map((job, i): BrainConfigDoc['jobs'][number] => ({
				...job,
				enabled: i === 0
			}))
		);
		api.getSettings.mockResolvedValue(running);
		await openJobs();

		await expect
			.element(page.getByRole('checkbox', { name: 'Enable Capture triage' }))
			.toBeChecked();

		await page.getByRole('checkbox', { name: 'Enable Capture triage' }).click();

		await expect
			.element(page.getByRole('checkbox', { name: 'Enable Capture triage' }))
			.not.toBeChecked();
		await expect
			.element(
				jobsPanel()
					.getByText(/^disabled$/)
					.first()
			)
			.toBeVisible();
	});

	it('hides the notice when the scheduler and a job are both on', async () => {
		const running = payload(
			SHIPPED_JOBS.map((job, i): BrainConfigDoc['jobs'][number] => ({
				...job,
				enabled: i === 0
			}))
		);
		running.config.scheduler.enabled = true;
		api.getSettings.mockResolvedValue(running);

		await openJobs();

		expect(page.getByText(/Nothing runs yet/).elements()).toHaveLength(0);
	});

	it('explains a config file it cannot load', async () => {
		api.getSettings.mockRejectedValue(new Error('invalid config: url must start with http://'));

		await render(Settings);

		await expect.element(page.getByText('The config file could not be loaded')).toBeVisible();
		await expect.element(page.getByText(/url must start with http/)).toBeVisible();
	});
});

describe('settings · job tools', () => {
	async function firstJobCard() {
		await openJobs();
		// the checkboxes live in the first job card
		return page.getByRole('checkbox', { name: 'read_note' }).first();
	}

	it('offers the tools as checkboxes instead of a free-text field', async () => {
		await firstJobCard();

		expect(page.getByText(/Restrict tools/).elements()).toHaveLength(0);
		await expect.element(page.getByRole('checkbox', { name: 'patch_note' }).first()).toBeVisible();
	});

	it('starts unrestricted: every enabled tool is on', async () => {
		await firstJobCard();

		await expect.element(page.getByText(/every enabled tool/).first()).toBeVisible();
		await expect.element(page.getByRole('checkbox', { name: 'read_note' }).first()).toBeChecked();
		await expect.element(page.getByRole('checkbox', { name: 'patch_note' }).first()).toBeChecked();
	});

	it('turning one off narrows the job to an explicit list', async () => {
		await firstJobCard();

		await page.getByRole('checkbox', { name: 'patch_note' }).first().click();

		await expect.element(page.getByText('1 of 3 tools')).toBeVisible();
		await expect
			.element(page.getByRole('checkbox', { name: 'patch_note' }).first())
			.not.toBeChecked();
	});

	it('collapses back to unrestricted when every enabled tool is on again', async () => {
		const job = { ...SHIPPED_JOBS[0], tools: ['read_note'] };
		api.getSettings.mockResolvedValue(payload([job]));
		await openJobs();
		await expect.element(page.getByText('1 of 3 tools')).toBeVisible();

		await page.getByRole('checkbox', { name: 'patch_note' }).click();

		await expect.element(page.getByText(/every enabled tool/)).toBeVisible();
	});

	it('flags a listed tool that is switched off in the Tools tab', async () => {
		const job = { ...SHIPPED_JOBS[0], tools: ['read_note', 'delete_note'] };
		api.getSettings.mockResolvedValue(payload([job]));
		await openJobs();

		await expect.element(page.getByText('2 of 3 tools · 1 switched off')).toBeVisible();
		// and it stays clickable, so the stale entry can be dropped
		await expect.element(page.getByRole('checkbox', { name: 'delete_note' })).toBeEnabled();
	});

	it('lets a restricted job take every enabled tool again', async () => {
		const job = { ...SHIPPED_JOBS[0], tools: ['read_note'] };
		api.getSettings.mockResolvedValue(payload([job]));
		await openJobs();
		await expect.element(page.getByText('1 of 3 tools')).toBeVisible();

		await page.getByRole('button', { name: 'Use all enabled' }).click();

		await expect.element(page.getByText(/every enabled tool/)).toBeVisible();
	});

	it('blocks a tool that is switched off in the Tools tab', async () => {
		await firstJobCard();

		const off = page.getByRole('checkbox', { name: 'delete_note' }).first();
		await expect.element(off).toBeDisabled();
		await expect.element(off).not.toBeChecked();
	});
});

describe('settings · job instructions note', () => {
	it('shows the current note read-only, not as free text', async () => {
		const job = { ...SHIPPED_JOBS[0], instructions_file: 'jobs/sweep.md' };
		api.getSettings.mockResolvedValue(payload([job]));
		await openJobs();

		const field = page.getByLabelText('Instructions note for Capture triage');
		await expect.element(field).toHaveValue('jobs/sweep.md');
		await expect.element(field).toHaveAttribute('readonly');
	});

	it('opens a searchable picker and applies the chosen note', async () => {
		api.search.mockResolvedValue({ names: ['jobs/nightly.md'], content: [] });
		await openJobs();

		await page.getByRole('button', { name: 'Choose…' }).first().click();
		await expect.element(page.getByLabelText('Search notes')).toBeVisible();
		await page.getByLabelText('Search notes').fill('nightly');

		await expect.poll(() => api.search).toHaveBeenCalledWith('nightly', 30, 0, false);
		await page.getByRole('button', { name: 'jobs/nightly.md' }).click();

		await expect
			.element(page.getByLabelText('Instructions note for Capture triage'))
			.toHaveValue('jobs/nightly.md');
	});

	it('browses the vault when the search box is empty', async () => {
		api.listNotes.mockResolvedValue({ notes: ['jobs/a.md', 'jobs/b.md'] });
		await openJobs();

		await page.getByRole('button', { name: 'Choose…' }).first().click();

		await expect.poll(() => api.listNotes).toHaveBeenCalledWith('', 50, 0);
		await expect.element(page.getByRole('button', { name: 'jobs/a.md' })).toBeVisible();
	});

	it('clears the note without opening the picker', async () => {
		const job = { ...SHIPPED_JOBS[0], instructions_file: 'jobs/sweep.md' };
		api.getSettings.mockResolvedValue(payload([job]));
		await openJobs();

		await page.getByRole('button', { name: 'Clear' }).first().click();

		await expect
			.element(page.getByLabelText('Instructions note for Capture triage'))
			.toHaveValue('');
	});
});

describe('settings · ask tab', () => {
	it('shows the enable switch and the instructions picker', async () => {
		await openTab('ask');

		await expect
			.element(page.getByRole('checkbox', { name: 'Enable Ask the librarian' }))
			.toBeChecked();
		const field = page.getByLabelText('Instructions note for asking');
		await expect.element(field).toHaveValue('');
		await expect.element(field).toHaveAttribute('readonly');
	});

	it('toggles asking off', async () => {
		await openTab('ask');

		await page.getByRole('checkbox', { name: 'Enable Ask the librarian' }).click();

		await expect
			.element(page.getByRole('checkbox', { name: 'Enable Ask the librarian' }))
			.not.toBeChecked();
	});

	it('opens the picker and restricts tools like a job does', async () => {
		api.search.mockResolvedValue({ names: ['ask-policy.md'], content: [] });
		await openTab('ask');

		await page.getByRole('button', { name: 'Choose…' }).click();
		await page.getByLabelText('Search notes').fill('policy');
		await expect.poll(() => api.search).toHaveBeenCalledWith('policy', 30, 0, false);
		await page.getByRole('button', { name: 'ask-policy.md' }).click();
		await expect
			.element(page.getByLabelText('Instructions note for asking'))
			.toHaveValue('ask-policy.md');

		await page.getByRole('checkbox', { name: 'read_note' }).click();
		await expect.element(page.getByRole('checkbox', { name: 'read_note' })).not.toBeChecked();
	});
});

describe('settings · agent instructions note', () => {
	it('shows the current note read-only, not as free text, with no inline textarea', async () => {
		await openTab('agent');

		const field = page.getByLabelText('Instructions note for the agent');
		await expect.element(field).toHaveValue('librarian.md');
		await expect.element(field).toHaveAttribute('readonly');
		expect(document.body.textContent).not.toContain('Inline instructions');
	});

	it('opens a searchable picker and applies the chosen note', async () => {
		api.search.mockResolvedValue({ names: ['librarian-v2.md'], content: [] });
		await openTab('agent');

		await page.getByRole('button', { name: 'Choose…' }).click();
		await expect.element(page.getByLabelText('Search notes')).toBeVisible();
		await page.getByLabelText('Search notes').fill('librarian');

		await expect.poll(() => api.search).toHaveBeenCalledWith('librarian', 30, 0, false);
		await page.getByRole('button', { name: 'librarian-v2.md' }).click();

		await expect
			.element(page.getByLabelText('Instructions note for the agent'))
			.toHaveValue('librarian-v2.md');
	});

	it('clears the note without opening the picker', async () => {
		await openTab('agent');

		await page.getByRole('button', { name: 'Clear' }).click();

		await expect.element(page.getByLabelText('Instructions note for the agent')).toHaveValue('');
	});

	it('explains how the agent note and job notes combine', async () => {
		await openTab('agent');

		await expect
			.element(
				page.getByText(
					"Standing instructions for every run; a job's own instructions note is appended on top of these, not instead of them."
				)
			)
			.toBeVisible();
	});
});

describe('settings · tools tab', () => {
	async function openTools() {
		await openTab('tools');
	}

	it('renders one checkbox per tool, checked to match enabled', async () => {
		await openTools();

		await expect.element(page.getByRole('checkbox', { name: 'read_note' })).toBeVisible();
		await expect.element(page.getByRole('checkbox', { name: 'patch_note' })).toBeVisible();
		await expect.element(page.getByRole('checkbox', { name: 'delete_note' })).toBeVisible();
		await expect.element(page.getByRole('checkbox', { name: 'read_note' })).toBeChecked();
		await expect.element(page.getByRole('checkbox', { name: 'delete_note' })).not.toBeChecked();
	});

	it('toggling a checkbox flips the tool without a save round-trip', async () => {
		await openTools();

		await page.getByRole('checkbox', { name: 'delete_note' }).click();
		await expect.element(page.getByRole('checkbox', { name: 'delete_note' })).toBeChecked();

		await page.getByRole('checkbox', { name: 'read_note' }).click();
		await expect.element(page.getByRole('checkbox', { name: 'read_note' })).not.toBeChecked();
	});
});

describe('settings · config tab', () => {
	async function openConfig() {
		await openTab('config');
	}

	it('does not fetch the extract while on another tab', async () => {
		api.exportSettings.mockResolvedValue('agent:\n  model: openai:gpt-4o\n');
		await openTab('agent');
		expect(api.exportSettings).not.toHaveBeenCalled();
	});

	it('loads the extract on first open', async () => {
		api.exportSettings.mockResolvedValue('agent:\n  model: openai:gpt-4o\n');

		await openConfig();

		await expect.poll(() => api.exportSettings).toHaveBeenCalledTimes(1);
		await expect
			.element(page.getByLabelText('Exported config'))
			.toHaveValue('agent:\n  model: openai:gpt-4o\n');
	});

	it('refresh re-fetches the extract', async () => {
		api.exportSettings.mockResolvedValue('agent:\n  model: openai:gpt-4o\n');
		await openConfig();
		await expect.poll(() => api.exportSettings).toHaveBeenCalledTimes(1);

		api.exportSettings.mockResolvedValue('agent:\n  model: openai:gpt-4o-mini\n');
		await page.getByRole('button', { name: 'Refresh' }).click();

		await expect.poll(() => api.exportSettings).toHaveBeenCalledTimes(2);
		await expect
			.element(page.getByLabelText('Exported config'))
			.toHaveValue('agent:\n  model: openai:gpt-4o-mini\n');
	});

	it('applies pasted yaml through the import endpoint, then reloads the draft', async () => {
		api.exportSettings.mockResolvedValue('agent:\n  model: openai:gpt-4o-mini\n');
		const updated = payload();
		updated.config.agent.model = 'openai:gpt-4o';
		api.importSettings.mockResolvedValue(updated);
		await openConfig();

		await page.getByLabelText('Config to import').fill('agent:\n  model: openai:gpt-4o\n');
		await page.getByRole('button', { name: 'Apply' }).click();

		await expect
			.poll(() => api.importSettings)
			.toHaveBeenCalledWith('agent:\n  model: openai:gpt-4o\n');
		// the pasted text is cleared and the draft now reflects what was imported
		await expect.element(page.getByLabelText('Config to import')).toHaveValue('');
	});

	it('reloading the draft after import shows the new model on the Agent tab', async () => {
		const updated = payload();
		updated.config.agent.model = 'openai:gpt-4o';
		api.getSettings.mockResolvedValue(updated);

		await openTab('agent');

		await expect.element(page.getByLabelText('Model')).toHaveValue('openai:gpt-4o');
	});

	it('surfaces a rejected import as an error, without touching the draft', async () => {
		api.exportSettings.mockResolvedValue('agent:\n  model: openai:gpt-4o-mini\n');
		api.importSettings.mockRejectedValue(new Error('invalid yaml: mapping expected'));
		await openConfig();

		await page.getByLabelText('Config to import').fill('not: [valid');
		await page.getByRole('button', { name: 'Apply' }).click();

		await expect.poll(() => api.importSettings).toHaveBeenCalled();
		// the pasted text stays so the user can fix it, rather than vanishing
		await expect.element(page.getByLabelText('Config to import')).toHaveValue('not: [valid');
	});

	it('disables Apply until there is something to import', async () => {
		api.exportSettings.mockResolvedValue('');
		await openConfig();

		await expect.element(page.getByRole('button', { name: 'Apply' })).toBeDisabled();
		await page.getByLabelText('Config to import').fill('agent: {}');
		await expect.element(page.getByRole('button', { name: 'Apply' })).toBeEnabled();
	});
});
