<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { api } from '$lib/api/client';
	import { LAYOUT_DOC, STARTER_DOCS } from '$lib/admin-seed';
	import type {
		BrainConfigDoc,
		CheckResult,
		JobRun,
		JobSpec,
		JobStatus,
		MCPServerConfig,
		ProviderInfo,
		Settings,
		ToolInfo
	} from '$lib/api/client';
	import { Badge } from '$lib/components/ui/badge';
	import { Button } from '$lib/components/ui/button';
	import * as Card from '$lib/components/ui/card';
	import { Checkbox } from '$lib/components/ui/checkbox';
	import * as Dialog from '$lib/components/ui/dialog';
	import ConnectionStatus from '$lib/components/ConnectionStatus.svelte';
	import { Input } from '$lib/components/ui/input';
	import { Label } from '$lib/components/ui/label';
	import * as Select from '$lib/components/ui/select';
	import { Separator } from '$lib/components/ui/separator';
	import * as Tabs from '$lib/components/ui/tabs';
	import { Textarea } from '$lib/components/ui/textarea';
	import { timeAgo } from '$lib/notes';
	import { onMount } from 'svelte';
	import { toast } from 'svelte-sonner';

	let settings = $state<Settings | null>(null);
	let draft = $state<BrainConfigDoc | null>(null);
	let dirty = $state(false);
	let saving = $state(false);
	let running = $state<string | null>(null);
	let loadError = $state('');
	// Connection checks, keyed by server name (and "model"): undefined = untried.
	let checks = $state<Record<string, CheckResult>>({});
	let checking = $state<Record<string, boolean>>({});
	// Model providers the server can reach, and which one is in effect.
	let providers = $state<ProviderInfo[]>([]);

	const TABS = ['agent', 'jobs', 'tools', 'mcp', 'templates'] as const;
	type Tab = (typeof TABS)[number];

	const SOURCES: Record<string, string> = {
		database: 'saved in the vault database',
		file: 'read from the seed file (nothing saved yet)',
		defaults: 'shipped defaults (no seed file, nothing saved yet)'
	};

	function isTab(value: string | null): value is Tab {
		return value !== null && (TABS as readonly string[]).includes(value);
	}

	// The selected tab lives in the URL, so a refresh (or a shared link) lands on
	// the same one instead of snapping back to the first.
	const requested = $derived(page.url.searchParams.get('tab'));
	const tab: Tab = $derived(isTab(requested) ? requested : 'agent');

	function selectTab(next: string) {
		if (!isTab(next) || next === tab) return;
		void goto(`?tab=${next}`, { replaceState: true, keepFocus: true, noScroll: true });
	}

	let runsFor = $state<string | null>(null);
	let runs = $state<JobRun[]>([]);

	/** Deep copy so Cancel-free editing never mutates the loaded snapshot. */
	function clone(config: BrainConfigDoc): BrainConfigDoc {
		return JSON.parse(JSON.stringify(config)) as BrainConfigDoc;
	}

	function emptyJob(index: number): JobSpec {
		return {
			id: `job-${index}`,
			name: '',
			description: '',
			enabled: true,
			every: '1d',
			cron: null,
			instructions: '',
			instructions_file: null,
			tools: null,
			mcp_servers: null,
			max_steps: null
		};
	}

	function statusFor(id: string): JobStatus | undefined {
		return settings?.jobs.find((j) => j.id === id);
	}

	async function load() {
		try {
			const loaded = await api.getSettings();
			settings = loaded;
			draft = clone(loaded.config);
			dirty = false;
			loadError = '';
		} catch (e) {
			// A hand-edited config can be invalid; say so rather than spin forever.
			loadError = e instanceof Error ? e.message : String(e);
			toast.error(loadError);
		}
		void loadProviders();
	}

	/** The provider list is dynamic: whatever this install can actually import. */
	async function loadProviders() {
		try {
			providers = (await api.modelProviders()).providers;
		} catch {
			providers = [];
		}
	}

	/** Which provider the draft would use: explicit, or the model string's prefix. */
	const chosenProvider = $derived.by(() => {
		if (!draft) return '';
		if (draft.agent.provider.name) return draft.agent.provider.name;
		const model = draft.agent.model;
		return model.includes(':') ? model.split(':', 1)[0] : '';
	});

	const chosenInfo = $derived(providers.find((p) => p.name === chosenProvider));

	/** What to call the endpoint field, per provider ('' = no endpoint field). */
	const urlLabel = $derived(
		chosenInfo?.url_param === 'azure_endpoint'
			? 'Endpoint'
			: chosenInfo?.url_param === 'api_base'
				? 'API base'
				: 'Base URL'
	);

	function pickProvider(name: string) {
		if (!draft) return;
		draft.agent.provider = { ...draft.agent.provider, name };
	}

	function optionRows(): [string, string][] {
		return Object.entries(draft?.agent.provider.options ?? {});
	}

	function setOption(key: string, value: string, previous?: string) {
		if (!draft) return;
		const options = { ...draft.agent.provider.options };
		// Renaming a row must move it, not add a second one — hence the explicit
		// undefined check rather than a truthiness test on the old key.
		if (previous !== undefined && previous !== key) delete options[previous];
		options[key] = value;
		draft.agent.provider.options = options;
	}

	function removeOption(key: string) {
		if (!draft) return;
		const options = { ...draft.agent.provider.options };
		delete options[key];
		draft.agent.provider.options = options;
	}

	function addOption() {
		if (!draft) return;
		// A placeholder until the user names it; the save validation rejects a key
		// the provider does not take, listing what it does.
		let n = Object.keys(draft.agent.provider.options).length + 1;
		while (`option-${n}` in draft.agent.provider.options) n += 1;
		setOption(`option-${n}`, '');
	}

	onMount(load);

	// Any edit to the draft marks it dirty; saving snapshots it again.
	$effect(() => {
		void draft;
		if (draft && settings && JSON.stringify(draft) !== JSON.stringify(settings.config)) {
			dirty = true;
		}
	});

	async function save() {
		if (!draft || saving) return;
		saving = true;
		try {
			const saved = await api.updateSettings(draft);
			settings = saved;
			draft = clone(saved.config);
			dirty = false;
			toast.success('Saved');
			// Validate connections now, so a broken server is not discovered by a job.
			void checkAll(saved.config.mcp_servers);
		} catch (e) {
			toast.error(e instanceof Error ? e.message : String(e));
		} finally {
			saving = false;
		}
	}

	async function runNow(jobId: string) {
		if (dirty) {
			toast.error('Save your changes first');
			return;
		}
		running = jobId;
		try {
			const run = await api.runJob(jobId);
			toast[run.status === 'ok' ? 'success' : 'error'](`Run ${run.status}`);
			await load();
		} catch (e) {
			toast.error(e instanceof Error ? e.message : String(e));
		} finally {
			running = null;
		}
	}

	async function openRuns(jobId: string) {
		runsFor = jobId;
		runs = [];
		try {
			runs = (await api.jobRuns(jobId)).runs;
		} catch (e) {
			toast.error(e instanceof Error ? e.message : String(e));
		}
	}

	function toggleSchedulerEnabled() {
		if (draft) draft.scheduler.enabled = !draft.scheduler.enabled;
	}

	function toggleRunOnStart() {
		if (draft) draft.scheduler.run_on_start = !draft.scheduler.run_on_start;
	}

	/** Page-type slug → template note rows for the Templates tab. */
	function templateRows(): [string, string][] {
		return Object.entries(draft?.admin.templates ?? {});
	}

	function setTemplate(key: string, value: string, previous?: string) {
		if (!draft) return;
		const templates = { ...draft.admin.templates };
		if (previous !== undefined && previous !== key) delete templates[previous];
		templates[key] = value;
		draft.admin.templates = templates;
	}

	function removeTemplate(key: string) {
		if (!draft) return;
		const templates = { ...draft.admin.templates };
		delete templates[key];
		draft.admin.templates = templates;
	}

	function addTemplate() {
		if (!draft) return;
		let n = Object.keys(draft.admin.templates).length + 1;
		while (`type-${n}` in draft.admin.templates) n += 1;
		setTemplate(`type-${n}`, '');
	}

	/** Prompt name → prompt note rows for the Templates tab. */
	function promptRows(): [string, string][] {
		return Object.entries(draft?.admin.prompts ?? {});
	}

	function setPrompt(key: string, value: string, previous?: string) {
		if (!draft) return;
		const prompts = { ...draft.admin.prompts };
		if (previous !== undefined && previous !== key) delete prompts[previous];
		prompts[key] = value;
		draft.admin.prompts = prompts;
	}

	function removePrompt(key: string) {
		if (!draft) return;
		const prompts = { ...draft.admin.prompts };
		delete prompts[key];
		draft.admin.prompts = prompts;
	}

	function addPrompt() {
		if (!draft) return;
		let n = Object.keys(draft.admin.prompts).length + 1;
		while (`prompt-${n}` in draft.admin.prompts) n += 1;
		setPrompt(`prompt-${n}`, '');
	}

	// Notes under the admin dir, for the Templates tab library list.
	let library = $state<string[]>([]);
	let libraryLoading = $state(false);
	let libraryTabSeen = $state(false);
	let seeding = $state(false);

	$effect(() => {
		// Lazily, once: the tab mounts with the page, so gate on first open.
		if (tab === 'templates' && draft && !libraryTabSeen) {
			libraryTabSeen = true;
			void loadLibrary();
		}
	});

	async function loadLibrary() {
		if (!draft) return;
		libraryLoading = true;
		try {
			library = (await api.listNotes(draft.admin.dir || 'admin', 500)).notes;
		} catch (e) {
			toast.error(e instanceof Error ? e.message : String(e));
		} finally {
			libraryLoading = false;
		}
	}

	/** Create the starter admin docs that are missing, and wire their mappings. */
	async function seedAdmin() {
		if (!draft || seeding) return;
		seeding = true;
		try {
			const dir = draft.admin.dir || 'admin';
			const existing = new Set((await api.listNotes(dir, 500)).notes);
			let created = 0;
			for (const doc of STARTER_DOCS) {
				const id = `${dir}/${doc.path}`;
				if (existing.has(id)) continue;
				await api.createNote(id, doc.content);
				created += 1;
			}
			const templates = { ...draft.admin.templates };
			const prompts = { ...draft.admin.prompts };
			for (const doc of STARTER_DOCS) {
				if (doc.template && !(doc.template in templates))
					templates[doc.template] = `${dir}/${doc.path}`;
				if (doc.prompt && !(doc.prompt in prompts)) prompts[doc.prompt] = `${dir}/${doc.path}`;
			}
			draft.admin.templates = templates;
			draft.admin.prompts = prompts;
			if (!draft.admin.layout_template || draft.admin.layout_template === 'admin/templates/layout')
				draft.admin.layout_template = `${dir}/${LAYOUT_DOC}`;
			await loadLibrary();
			toast.success(
				created > 0
					? `Seeded ${created} admin doc${created === 1 ? '' : 's'}`
					: 'Admin docs already present'
			);
		} catch (e) {
			toast.error(e instanceof Error ? e.message : String(e));
		} finally {
			seeding = false;
		}
	}

	function setTemperature(value: string) {
		if (draft) draft.agent.temperature = value === '' ? null : Number(value);
	}

	const schedulerEnabled = () => draft?.scheduler.enabled ?? false;
	const runOnStart = () => draft?.scheduler.run_on_start ?? false;
	const temperatureValue = () => draft?.agent.temperature ?? '';

	const anyJobEnabled = $derived(!!draft?.jobs.some((job) => job.enabled));

	/** True while nothing can run: the scheduler is off, or no job is enabled. */
	const paused = $derived(!!draft && (!draft.scheduler.enabled || !anyJobEnabled));

	function setScheduleMode(job: JobSpec, mode: string) {
		if (mode === 'cron') {
			job.cron = job.cron ?? '0 */4 * * *';
			job.every = null;
		} else {
			job.every = job.every ?? '4h';
			job.cron = null;
		}
	}

	function addJob() {
		if (!draft) return;
		const ids = new Set(draft.jobs.map((j) => j.id));
		let n = draft.jobs.length + 1;
		while (ids.has(`job-${n}`)) n += 1;
		draft.jobs = [...draft.jobs, emptyJob(n)];
	}

	function removeJob(index: number) {
		if (!draft) return;
		draft.jobs = draft.jobs.filter((_, i) => i !== index);
	}

	function toggleTool(name: string, enabled: boolean) {
		if (!draft) return;
		draft.tools = { ...draft.tools, [name]: { enabled } };
	}

	function toolEnabled(tool: ToolInfo): boolean {
		return draft?.tools[tool.name]?.enabled ?? tool.enabled;
	}

	/** A job with no list runs every tool enabled in the Tools tab. */
	const enabledToolNames = $derived(
		(settings?.tools ?? []).filter((tool) => toolEnabled(tool)).map((tool) => tool.name)
	);

	function jobToolOn(job: JobSpec, tool: ToolInfo): boolean {
		return toolEnabled(tool) && (job.tools === null || job.tools.includes(tool.name));
	}

	function jobToolLocked(job: JobSpec, tool: ToolInfo): boolean {
		// A tool switched off in the Tools tab cannot be added here — but one already
		// listed must stay removable, or a stale entry could never be undone.
		return !toolEnabled(tool) && !(job.tools?.includes(tool.name) ?? false);
	}

	function toolEnabledByName(name: string): boolean {
		const tool = settings?.tools.find((t) => t.name === name);
		return tool ? toolEnabled(tool) : true;
	}

	function jobToolSummary(job: JobSpec): string {
		if (job.tools === null) return 'every enabled tool';
		if (job.tools.length === 0) return 'no tools — this job can do nothing';
		const total = settings?.tools.length ?? 0;
		const unavailable = job.tools.filter((name) => !toolEnabledByName(name)).length;
		const base = `${job.tools.length} of ${total} tools`;
		return unavailable > 0 ? `${base} · ${unavailable} switched off` : base;
	}

	function toggleJobTool(job: JobSpec, tool: ToolInfo) {
		// `null` means "all enabled": materialise that before the first exclusion.
		const current = job.tools ?? enabledToolNames;
		const next = current.includes(tool.name)
			? current.filter((name) => name !== tool.name)
			: [...current, tool.name];
		// Back to every enabled tool? Collapse to null so the config stays unrestricted.
		const allOn =
			enabledToolNames.length > 0 && enabledToolNames.every((name) => next.includes(name));
		job.tools = allOn ? null : next;
	}

	/** Registered MCP servers — the config list itself, live from the draft. */
	const servers = $derived(draft?.mcp_servers ?? []);
	const enabledServerNames = $derived(
		servers.filter((server) => server.enabled).map((server) => server.name)
	);

	function jobServerOn(job: JobSpec, server: MCPServerConfig): boolean {
		return server.enabled && (job.mcp_servers === null || job.mcp_servers.includes(server.name));
	}

	function jobServerLocked(job: JobSpec, server: MCPServerConfig): boolean {
		// Same rule as tools: can't pick a server that is switched off, but a stale
		// entry in an existing job must stay removable.
		return !server.enabled && !(job.mcp_servers?.includes(server.name) ?? false);
	}

	function jobServerSummary(job: JobSpec): string {
		if (job.mcp_servers === null) return 'every enabled server';
		if (job.mcp_servers.length === 0) return 'no servers — this job gets no remote tools';
		const unavailable = job.mcp_servers.filter(
			(name) => !servers.find((s) => s.name === name)?.enabled
		).length;
		const base = `${job.mcp_servers.length} of ${servers.length} servers`;
		return unavailable > 0 ? `${base} · ${unavailable} switched off` : base;
	}

	function toggleJobServer(job: JobSpec, server: MCPServerConfig) {
		const current = job.mcp_servers ?? enabledServerNames;
		const next = current.includes(server.name)
			? current.filter((name) => name !== server.name)
			: [...current, server.name];
		const allOn =
			enabledServerNames.length > 0 && enabledServerNames.every((name) => next.includes(name));
		job.mcp_servers = allOn ? null : next;
	}

	async function checkServer(server: MCPServerConfig) {
		if (!server.name || checking[server.name]) return;
		checking = { ...checking, [server.name]: true };
		try {
			checks = { ...checks, [server.name]: await api.testMcpServer(server) };
		} catch (e) {
			// A 422 (bad config) still deserves a red line, not a toast only.
			checks = {
				...checks,
				[server.name]: {
					name: server.name,
					ok: false,
					detail: e instanceof Error ? e.message : String(e),
					tools: []
				}
			};
		} finally {
			checking = { ...checking, [server.name]: false };
		}
	}

	/** Check every enabled server in parallel — run after a save. */
	async function checkAll(servers: MCPServerConfig[]) {
		await Promise.all([...servers.filter((s) => s.enabled).map(checkServer), checkModelConfig()]);
	}

	/** Ask the configured model for a one-word answer. */
	async function checkModelConfig() {
		if (!draft || checking.model) return;
		checking = { ...checking, model: true };
		try {
			checks = { ...checks, model: await api.testModel(draft.agent) };
		} catch (e) {
			checks = {
				...checks,
				model: {
					name: draft.agent.model,
					ok: false,
					detail: e instanceof Error ? e.message : String(e),
					tools: []
				}
			};
		} finally {
			checking = { ...checking, model: false };
		}
	}

	function addServer() {
		if (!draft) return;
		draft.mcp_servers = [
			...draft.mcp_servers,
			{
				name: `server-${draft.mcp_servers.length + 1}`,
				transport: 'http',
				url: '',
				headers: {},
				enabled: true,
				insecure: false
			} satisfies MCPServerConfig
		];
	}

	function removeServer(index: number) {
		if (!draft) return;
		const [gone] = draft.mcp_servers.slice(index, index + 1);
		draft.mcp_servers = draft.mcp_servers.filter((_, i) => i !== index);
		// A job naming a removed server would fail config validation on save, so
		// drop the reference here instead of making the user hunt for it.
		if (!gone) return;
		for (const job of draft.jobs) {
			if (job.mcp_servers?.includes(gone.name)) {
				const rest = job.mcp_servers.filter((name) => name !== gone.name);
				job.mcp_servers = rest.length === 0 ? [] : rest;
			}
		}
	}
</script>

<div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
	<div>
		<h1 class="text-2xl font-semibold tracking-tight">Settings</h1>
		<p class="mt-1 text-sm text-muted-foreground">
			Agent, tools, MCP servers and scheduled jobs — one config file.
		</p>
	</div>
	<div class="flex items-center gap-2">
		{#if dirty}<Badge variant="outline">unsaved</Badge>{/if}
		<Button onclick={save} disabled={!dirty || saving}>{saving ? 'Saving…' : 'Save'}</Button>
	</div>
</div>

{#if !draft || !settings}
	{#if loadError}
		<div class="mt-6 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2">
			<p class="text-sm font-medium text-destructive">The config file could not be loaded</p>
			<p class="mt-1 font-mono text-xs text-destructive">{loadError}</p>
			<p class="mt-2 text-xs text-muted-foreground">
				Fix that file (or remove it to fall back to the shipped example schedule), then reload this
				page.
			</p>
		</div>
	{:else}
		<p class="mt-6 text-sm text-muted-foreground">Loading…</p>
	{/if}
{:else}
	<p class="mt-3 font-mono text-xs text-muted-foreground">
		{SOURCES[settings.config_source] ?? settings.config_source} · seed {settings.config_path}
	</p>

	<Tabs.Root value={tab} onValueChange={selectTab} class="mt-4">
		<Tabs.List>
			<Tabs.Trigger value="agent">Agent</Tabs.Trigger>
			<Tabs.Trigger value="jobs">Jobs</Tabs.Trigger>
			<Tabs.Trigger value="tools">Tools</Tabs.Trigger>
			<Tabs.Trigger value="mcp">MCP servers</Tabs.Trigger>
			<Tabs.Trigger value="templates">Templates</Tabs.Trigger>
		</Tabs.List>

		<Tabs.Content value="agent" class="mt-4 space-y-4">
			<Card.Root>
				<Card.Header>
					<Card.Title>Model</Card.Title>
					<Card.Description>
						Pydantic-AI model string. The token is read from an environment variable so a container
						can inject it from a secret.
					</Card.Description>
					<Card.Action>
						<Button
							size="sm"
							variant="outline"
							disabled={checking.model}
							onclick={checkModelConfig}
						>
							Test model
						</Button>
					</Card.Action>
				</Card.Header>
				{#if checking.model || checks.model}
					<ConnectionStatus
						checking={!!checking.model}
						result={checks.model}
						checkingText="Asking the model…"
					/>
				{/if}
				<Card.Content class="grid gap-4 sm:grid-cols-2">
					<div class="grid gap-2">
						<Label for="provider">Provider</Label>
						<Select.Root
							type="single"
							value={draft.agent.provider.name}
							onValueChange={(v) => pickProvider(v as string)}
						>
							<Select.Trigger>
								<Select.Value placeholder="from the model string" />
							</Select.Trigger>
							<Select.Content>
								<Select.Item value="">from the model string</Select.Item>
								{#each providers as option (option.name)}
									<Select.Item value={option.name} disabled={!option.available}>
										{option.name}{option.available ? '' : ' (not installed)'}
									</Select.Item>
								{/each}
							</Select.Content>
						</Select.Root>
						{#if chosenInfo && !chosenInfo.available}
							<p class="text-xs text-destructive">{chosenInfo.hint || 'SDK not installed'}</p>
						{:else if chosenInfo?.url_param}
							<p class="text-xs text-muted-foreground">
								Set a custom {urlLabel} only if you are not using the default endpoint.
							</p>
						{/if}
					</div>
					<div class="grid gap-2">
						<Label for="model">Model</Label>
						<Input
							id="model"
							bind:value={draft.agent.model}
							placeholder={draft.agent.provider.name
								? 'model id, e.g. llama3.1'
								: 'provider:model, e.g. openai:gpt-4o'}
							spellcheck="false"
						/>
					</div>
					{#if chosenInfo?.url_param || draft.agent.provider.base_url}
						<div class="grid gap-2">
							<Label for="baseurl">{urlLabel}</Label>
							<Input
								id="baseurl"
								bind:value={draft.agent.provider.base_url}
								placeholder="https://host/v1"
								spellcheck="false"
							/>
						</div>
					{/if}
					{#if chosenInfo?.api_version_param || draft.agent.provider.api_version}
						<div class="grid gap-2">
							<Label for="apiversion">API version</Label>
							<Input
								id="apiversion"
								bind:value={draft.agent.provider.api_version}
								placeholder="2024-10-21"
								spellcheck="false"
							/>
						</div>
					{/if}
					<div class="grid gap-2 sm:col-span-2">
						<div class="flex flex-wrap items-baseline gap-2">
							<Label>Extra provider options</Label>
							<span class="text-xs text-muted-foreground">
								by argument name — anything else that provider's constructor needs
							</span>
							<Button size="sm" variant="ghost" onclick={addOption}>Add option</Button>
						</div>
						{#each optionRows() as [key, value] (key)}
							<div class="flex gap-2">
								<Input
									value={key}
									placeholder="region"
									aria-label="Option name"
									spellcheck="false"
									oninput={(e) => setOption(e.currentTarget.value, value, key)}
								/>
								<Input
									{value}
									placeholder="eu-west-1"
									aria-label="Option value"
									spellcheck="false"
									oninput={(e) => setOption(key, e.currentTarget.value)}
								/>
								<Button size="sm" variant="ghost" onclick={() => removeOption(key)}>Remove</Button>
							</div>
						{/each}
					</div>
					<div class="grid gap-2">
						<Label for="keyenv">Token env var</Label>
						<Input id="keyenv" bind:value={draft.agent.api_key_env} spellcheck="false" />
					</div>
					<div class="grid gap-2">
						<Label for="apikey">Token</Label>
						<Input
							id="apikey"
							type="password"
							bind:value={draft.agent.api_key}
							placeholder={settings.api_key_configured ? 'stored' : 'not set'}
							spellcheck="false"
						/>
					</div>
					<div class="grid gap-2">
						<Label for="steps">Max steps</Label>
						<Input id="steps" type="number" min="1" bind:value={draft.agent.max_steps} />
					</div>
					<div class="grid gap-2">
						<Label for="temp">Temperature</Label>
						<Input
							id="temp"
							type="number"
							step="0.1"
							min="0"
							max="2"
							value={temperatureValue()}
							placeholder="provider default"
							oninput={(e) => {
								const v = (e.currentTarget as HTMLInputElement).value;
								setTemperature(v);
							}}
						/>
						<p class="text-xs text-muted-foreground">
							Low by default (0.2) — careful edits, not creative writing. Empty means "let the
							provider decide".
						</p>
					</div>
					<div class="grid gap-2">
						<Label for="instrfile">Instructions note</Label>
						<Input
							id="instrfile"
							bind:value={draft.agent.instructions_file}
							placeholder="librarian.md"
							spellcheck="false"
						/>
					</div>
					<div class="grid gap-2 sm:col-span-2">
						<Label for="instr">Inline instructions</Label>
						<Textarea id="instr" bind:value={draft.agent.instructions} class="min-h-24"></Textarea>
					</div>
				</Card.Content>
			</Card.Root>

			<Card.Root>
				<Card.Header>
					<Card.Title>Scheduler</Card.Title>
					<Card.Description>How often due jobs are checked.</Card.Description>
				</Card.Header>
				<Card.Content class="grid gap-4 sm:grid-cols-3">
					<div class="grid gap-2">
						<Label>Enabled</Label>
						<Button
							variant={schedulerEnabled() ? 'default' : 'outline'}
							onclick={toggleSchedulerEnabled}
						>
							{draft.scheduler.enabled ? 'On' : 'Off'}
						</Button>
					</div>
					<div class="grid gap-2">
						<Label for="tick">Tick (seconds)</Label>
						<Input id="tick" type="number" min="1" bind:value={draft.scheduler.tick_seconds} />
					</div>
					<div class="grid gap-2">
						<Label>Run on start</Label>
						<Button variant={runOnStart() ? 'default' : 'outline'} onclick={toggleRunOnStart}>
							{draft.scheduler.run_on_start ? 'Yes' : 'No'}
						</Button>
					</div>
				</Card.Content>
			</Card.Root>
		</Tabs.Content>

		<Tabs.Content value="jobs" class="mt-4 space-y-4">
			<div class="flex flex-wrap items-center justify-between gap-2">
				<p class="text-sm text-muted-foreground">
					Each job runs the agent with the instructions below and the enabled tools.
				</p>
				<Button variant="outline" size="sm" onclick={addJob}>Add job</Button>
			</div>

			{#if paused}
				<p
					class="rounded-md border border-border/60 bg-muted/40 px-3 py-2 text-xs text-muted-foreground"
				>
					This is the shipped example schedule. Nothing runs yet —
					{#if !draft.scheduler.enabled}the scheduler is off{/if}{#if !draft.scheduler.enabled && !anyJobEnabled}
						and
					{/if}{#if !anyJobEnabled}{draft.jobs.length === 1 ? 'the job is' : 'every job is'} disabled{/if}.
					Enable a job here and the scheduler under Agent when you are ready.
				</p>
			{/if}

			{#if draft.jobs.length === 0}
				<p class="text-sm text-muted-foreground">No jobs yet.</p>
			{/if}

			{#each draft.jobs as job, index (index)}
				<Card.Root>
					<Card.Header>
						<Card.Title class="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
							<span class="min-w-0 break-words">{job.name || job.id}</span>
							<Badge variant={job.enabled ? 'default' : 'secondary'}>
								{job.enabled ? 'enabled' : 'disabled'}
							</Badge>
							{#if statusFor(job.id)?.next_run}
								<span class="text-xs font-normal break-words text-muted-foreground">
									next {timeAgo(statusFor(job.id)!.next_run)}
								</span>
							{/if}
						</Card.Title>
						<div class="flex flex-wrap items-center gap-2">
							<label class="flex cursor-pointer items-center gap-1.5 text-sm font-medium">
								<Checkbox
									checked={job.enabled}
									aria-label={`Enable ${job.name || job.id}`}
									onCheckedChange={(v) => (job.enabled = v === true)}
								/>
								Enable
							</label>
							<Button
								size="sm"
								variant="outline"
								disabled={running === job.id}
								onclick={() => runNow(job.id)}
							>
								{running === job.id ? 'Running…' : 'Run now'}
							</Button>
							<Button size="sm" variant="ghost" onclick={() => openRuns(job.id)}>History</Button>
							<Button size="sm" variant="ghost" onclick={() => removeJob(index)}>Remove</Button>
						</div>
					</Card.Header>
					<Card.Content class="grid gap-4 sm:grid-cols-2">
						<div class="grid gap-2">
							<Label>Id</Label>
							<Input bind:value={job.id} spellcheck="false" />
						</div>
						<div class="grid gap-2">
							<Label>Name</Label>
							<Input bind:value={job.name} />
						</div>
						<div class="grid gap-2">
							<Label>Schedule</Label>
							<div class="flex gap-2">
								<Select.Root
									type="single"
									value={job.cron ? 'cron' : 'every'}
									onValueChange={(v) => setScheduleMode(job, v as string)}
								>
									<Select.Trigger class="w-28">
										<Select.Value />
									</Select.Trigger>
									<Select.Content>
										<Select.Item value="every">interval</Select.Item>
										<Select.Item value="cron">cron</Select.Item>
									</Select.Content>
								</Select.Root>
								{#if job.cron !== null}
									<Input bind:value={job.cron} placeholder="0 */4 * * *" spellcheck="false" />
								{:else}
									<Input bind:value={job.every} placeholder="4h" spellcheck="false" />
								{/if}
							</div>
						</div>
						<div class="grid gap-2">
							<Label>Instructions note</Label>
							<Input
								value={job.instructions_file ?? ''}
								oninput={(e) => {
									const v = (e.currentTarget as HTMLInputElement).value;
									job.instructions_file = v === '' ? null : v;
								}}
								placeholder="jobs/daily.md"
								spellcheck="false"
							/>
						</div>
						<div class="grid gap-2 sm:col-span-2">
							<Label>Instructions</Label>
							<Textarea bind:value={job.instructions} class="min-h-24"></Textarea>
						</div>
						<div class="grid gap-2 sm:col-span-2">
							<div class="flex flex-wrap items-baseline gap-2">
								<Label>Tools</Label>
								<span class="text-xs text-muted-foreground">{jobToolSummary(job)}</span>
								{#if job.tools !== null}
									<Button size="sm" variant="ghost" onclick={() => (job.tools = null)}>
										Use all enabled
									</Button>
								{/if}
							</div>
							<div class="flex flex-wrap gap-1.5">
								{#each settings.tools as tool (tool.name)}
									{@const on = jobToolOn(job, tool)}
									<Button
										size="sm"
										variant={on ? 'default' : 'outline'}
										aria-pressed={on}
										disabled={jobToolLocked(job, tool)}
										title={jobToolLocked(job, tool)
											? `${tool.name} is switched off in the Tools tab`
											: tool.description}
										onclick={() => toggleJobTool(job, tool)}
									>
										{tool.name}
									</Button>
								{/each}
							</div>
						</div>
						<div class="grid gap-2 sm:col-span-2">
							<div class="flex flex-wrap items-baseline gap-2">
								<Label>MCP servers</Label>
								<span class="text-xs text-muted-foreground">{jobServerSummary(job)}</span>
								{#if job.mcp_servers !== null}
									<Button size="sm" variant="ghost" onclick={() => (job.mcp_servers = null)}>
										Use all enabled
									</Button>
								{/if}
							</div>
							{#if servers.length === 0}
								<p class="text-xs text-muted-foreground">
									No MCP servers registered — add one in the MCP servers tab.
								</p>
							{:else}
								<div class="flex flex-wrap gap-1.5">
									{#each servers as server (server.name)}
										{@const on = jobServerOn(job, server)}
										<Button
											size="sm"
											variant={on ? 'default' : 'outline'}
											aria-pressed={on}
											disabled={jobServerLocked(job, server)}
											title={jobServerLocked(job, server)
												? `${server.name} is switched off in the MCP servers tab`
												: server.url}
											onclick={() => toggleJobServer(job, server)}
										>
											{server.name}
										</Button>
									{/each}
								</div>
							{/if}
						</div>
						{#if statusFor(job.id)?.last_status}
							<div class="sm:col-span-2">
								<Separator />
								<p class="mt-3 text-xs text-muted-foreground">
									Last run {statusFor(job.id)!.last_status} · {timeAgo(statusFor(job.id)!.last_run)}
								</p>
							</div>
						{/if}
					</Card.Content>
				</Card.Root>
			{/each}
		</Tabs.Content>

		<Tabs.Content value="tools" class="mt-4 space-y-3">
			<p class="text-sm text-muted-foreground">
				Built-in tools act on vault notes and the capture queue only.
			</p>
			<ul class="max-w-3xl divide-y rounded-lg border">
				{#each settings.tools as tool (tool.name)}
					<li>
						<label class="flex cursor-pointer items-center gap-3 px-4 py-3">
							<Checkbox
								checked={toolEnabled(tool)}
								aria-label={tool.name}
								onCheckedChange={(v) => toggleTool(tool.name, v === true)}
							/>
							<div class="min-w-0 flex-1">
								<code class="text-sm font-medium">{tool.name}</code>
								<p class="text-xs text-muted-foreground">{tool.description}</p>
							</div>
						</label>
					</li>
				{/each}
			</ul>
		</Tabs.Content>

		<Tabs.Content value="mcp" class="mt-4 space-y-4">
			<div class="flex items-center justify-between">
				<p class="text-sm text-muted-foreground">
					Remote MCP servers contribute extra tools to every job that allows them. Saving checks
					every enabled server can be reached.
				</p>
				<Button variant="outline" size="sm" onclick={addServer}>Add server</Button>
			</div>

			{#if draft.mcp_servers.length === 0}
				<p class="text-sm text-muted-foreground">No MCP servers configured.</p>
			{/if}

			{#each draft.mcp_servers as server, index (index)}
				<Card.Root>
					<Card.Header>
						<Card.Title class="flex items-center gap-2">
							{server.name || 'server'}
							<Badge variant={server.enabled ? 'default' : 'secondary'}>
								{server.enabled ? 'enabled' : 'disabled'}
							</Badge>
						</Card.Title>
						<Card.Action>
							<div class="flex flex-wrap gap-2">
								<Button
									size="sm"
									variant="outline"
									disabled={checking[server.name]}
									onclick={() => checkServer(server)}
								>
									Test
								</Button>
								<Button
									size="sm"
									variant={server.enabled ? 'outline' : 'default'}
									onclick={() => (server.enabled = !server.enabled)}
								>
									{server.enabled ? 'Disable' : 'Enable'}
								</Button>
								<Button size="sm" variant="ghost" onclick={() => removeServer(index)}>
									Remove
								</Button>
							</div>
						</Card.Action>
					</Card.Header>
					{#if checking[server.name] || checks[server.name]}
						<ConnectionStatus
							checking={!!checking[server.name]}
							result={checks[server.name]}
							checkingText="Connecting…"
						/>
					{/if}
					<Card.Content class="grid gap-4 sm:grid-cols-2">
						<div class="grid gap-2">
							<Label>Name</Label>
							<Input bind:value={server.name} spellcheck="false" />
						</div>
						<div class="grid gap-2">
							<Label>Transport</Label>
							<Select.Root
								type="single"
								value={server.transport}
								onValueChange={(v) => (server.transport = v as MCPServerConfig['transport'])}
							>
								<Select.Trigger>
									<Select.Value />
								</Select.Trigger>
								<Select.Content>
									<Select.Item value="http">http</Select.Item>
									<Select.Item value="sse">sse</Select.Item>
								</Select.Content>
							</Select.Root>
						</div>
						<div class="grid gap-2 sm:col-span-2">
							<Label>URL</Label>
							<Input bind:value={server.url} placeholder="https://host/mcp" spellcheck="false" />
							<p class="text-xs text-muted-foreground">
								Remote servers only — the librarian has no shell and cannot run local processes.
							</p>
							<label class="flex cursor-pointer items-start gap-2">
								<Checkbox
									checked={server.insecure ?? false}
									aria-label={`Skip certificate verification for ${server.name || 'server'}`}
									onCheckedChange={(v) => (server.insecure = v === true)}
								/>
								<span class="text-xs text-muted-foreground">
									Skip TLS certificate verification (self-signed certificates). Off unless you need
									it — anyone on the network can read and modify this traffic.
								</span>
							</label>
						</div>
					</Card.Content>
				</Card.Root>
			{/each}
		</Tabs.Content>

		<Tabs.Content value="templates" class="mt-4 space-y-4">
			<Card.Root>
				<Card.Header>
					<Card.Title>Vault administration</Card.Title>
					<Card.Description>
						Markdown in the vault the librarian manages the vault by — page templates, reusable
						prompts, and the wiki layout. Edit the content as regular pages.
					</Card.Description>
				</Card.Header>
				<Card.Content class="grid gap-4 sm:grid-cols-2">
					<div class="grid gap-2">
						<Label for="admindir">Admin directory</Label>
						<Input
							id="admindir"
							bind:value={draft.admin.dir}
							placeholder="admin"
							spellcheck="false"
						/>
						<p class="text-xs text-muted-foreground">Section holding templates and prompts.</p>
					</div>
					<div class="grid gap-2">
						<Label for="layouttpl">Layout template</Label>
						<Input
							id="layouttpl"
							bind:value={draft.admin.layout_template}
							placeholder="admin/templates/layout"
							spellcheck="false"
						/>
						{#if draft.admin.layout_template}
							<a
								href={`/p/${draft.admin.layout_template}`}
								class="text-xs text-blue-600 hover:underline"
							>
								Open page
							</a>
						{/if}
					</div>
				</Card.Content>
			</Card.Root>

			<Card.Root>
				<Card.Header>
					<Card.Title>Page templates</Card.Title>
					<Card.Description>
						Page type slug → template note. New pages of a known type start from their template.
					</Card.Description>
					<Card.Action>
						<Button size="sm" variant="outline" onclick={addTemplate}>Add template</Button>
					</Card.Action>
				</Card.Header>
				<Card.Content class="space-y-2">
					{#each templateRows() as [key, value] (key)}
						<div class="flex gap-2">
							<Input
								value={key}
								placeholder="meeting"
								aria-label="Template type"
								spellcheck="false"
								oninput={(e) => setTemplate(e.currentTarget.value, value, key)}
							/>
							<Input
								{value}
								placeholder="admin/templates/meeting"
								aria-label="Template note"
								spellcheck="false"
								oninput={(e) => setTemplate(key, e.currentTarget.value)}
							/>
							<Button size="sm" variant="ghost" onclick={() => removeTemplate(key)}>Remove</Button>
						</div>
					{/each}
					{#if templateRows().length === 0}
						<p class="text-sm text-muted-foreground">No page templates mapped yet.</p>
					{/if}
				</Card.Content>
			</Card.Root>

			<Card.Root>
				<Card.Header>
					<Card.Title>Prompts</Card.Title>
					<Card.Description>
						Prompt name → prompt note. The librarian reads the note before a run.
					</Card.Description>
					<Card.Action>
						<Button size="sm" variant="outline" onclick={addPrompt}>Add prompt</Button>
					</Card.Action>
				</Card.Header>
				<Card.Content class="space-y-2">
					{#each promptRows() as [key, value] (key)}
						<div class="flex gap-2">
							<Input
								value={key}
								placeholder="triage"
								aria-label="Prompt name"
								spellcheck="false"
								oninput={(e) => setPrompt(e.currentTarget.value, value, key)}
							/>
							<Input
								{value}
								placeholder="admin/prompts/triage"
								aria-label="Prompt note"
								spellcheck="false"
								oninput={(e) => setPrompt(key, e.currentTarget.value)}
							/>
							<Button size="sm" variant="ghost" onclick={() => removePrompt(key)}>Remove</Button>
						</div>
					{/each}
					{#if promptRows().length === 0}
						<p class="text-sm text-muted-foreground">No prompts mapped yet.</p>
					{/if}
				</Card.Content>
			</Card.Root>

			<Card.Root>
				<Card.Header>
					<Card.Title>In the vault</Card.Title>
					<Card.Description>Notes under {draft.admin.dir || 'admin'}.</Card.Description>
					<Card.Action>
						<div class="flex gap-2">
							<Button size="sm" variant="ghost" onclick={loadLibrary}>Refresh</Button>
							<Button size="sm" variant="outline" disabled={seeding} onclick={seedAdmin}>
								{seeding ? 'Seeding…' : 'Seed starter set'}
							</Button>
						</div>
					</Card.Action>
				</Card.Header>
				<Card.Content>
					{#if libraryLoading}
						<p class="text-sm text-muted-foreground">Loading…</p>
					{:else if library.length === 0}
						<p class="text-sm text-muted-foreground">
							Nothing here yet — seed the starter set or create pages under {draft.admin.dir ||
								'admin'}.
						</p>
					{:else}
						<ul class="divide-y rounded-lg border">
							{#each library as id (id)}
								<li>
									<a
										href={`/p/${id}`}
										class="block px-4 py-2 text-sm font-medium text-blue-600 hover:bg-muted"
									>
										{id}
									</a>
								</li>
							{/each}
						</ul>
					{/if}
				</Card.Content>
			</Card.Root>
		</Tabs.Content>
	</Tabs.Root>
{/if}

<Dialog.Root open={runsFor !== null} onOpenChange={(open) => (runsFor = open ? runsFor : null)}>
	<Dialog.Content class="sm:max-w-2xl">
		<Dialog.Header>
			<Dialog.Title>Run history — {runsFor}</Dialog.Title>
			<Dialog.Description>Newest first.</Dialog.Description>
		</Dialog.Header>
		<ul class="max-h-96 space-y-3 overflow-y-auto">
			{#each runs as run (run.id)}
				<li class="rounded-md border p-3">
					<div class="flex items-center gap-2">
						<Badge variant={run.status === 'ok' ? 'default' : 'secondary'}>{run.status}</Badge>
						<span class="text-xs text-muted-foreground">{timeAgo(run.started_at)}</span>
					</div>
					{#if run.detail}
						<pre class="mt-2 text-xs whitespace-pre-wrap text-muted-foreground">{run.detail}</pre>
					{/if}
				</li>
			{/each}
			{#if runs.length === 0}
				<li class="text-sm text-muted-foreground">No runs recorded.</li>
			{/if}
		</ul>
		<Dialog.Footer>
			<Button variant="ghost" onclick={() => (runsFor = null)}>Close</Button>
		</Dialog.Footer>
	</Dialog.Content>
</Dialog.Root>
