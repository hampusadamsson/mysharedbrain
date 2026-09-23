<script lang="ts">
	import { api, type ImportResult } from '$lib/api/client';
	import { Button } from '$lib/components/ui/button';
	import * as Dialog from '$lib/components/ui/dialog';
	import { LoaderCircle } from '@lucide/svelte';
	import { toast } from 'svelte-sonner';

	interface Props {
		files: File[];
		overwrite: boolean;
		/** Called once the batch loop finishes, so the listing can refresh. */
		onfinished: () => void;
		/** Called when the reader dismisses the dialog; the host unmounts it. */
		onclose: () => void;
	}

	// Mounted only while an import is on screen (the host renders it under an
	// `{#if}`), so there is no long-lived instance to reset or re-run.
	let { files, overwrite, onfinished, onclose }: Props = $props();
	let open = $state(true);

	//: The API takes 250 per request; send fewer so a big folder reports progress
	//: instead of one long silence, and so one bad batch cannot lose the rest.
	const BATCH = 25;

	type Failure = { name: string; reason: string };

	let sent = $state(0);
	let created = $state<string[]>([]);
	let updated = $state<string[]>([]);
	let skipped = $state<string[]>([]);
	let failures = $state<Failure[]>([]);
	let running = $state(false);
	let finished = $state(false);

	const total = $derived(files.length);
	const percent = $derived(total === 0 ? 0 : Math.round((sent / total) * 100));
	const summary = $derived(
		[
			created.length ? `${created.length} new` : '',
			updated.length ? `${updated.length} replaced` : '',
			skipped.length ? `${skipped.length} skipped` : '',
			failures.length ? `${failures.length} failed` : ''
		]
			.filter(Boolean)
			.join(', ')
	);

	function absorb(result: ImportResult) {
		created = [...created, ...result.created];
		updated = [...updated, ...result.updated];
		skipped = [...skipped, ...result.skipped];
		failures = [
			...failures,
			...Object.entries(result.errors).map(([name, reason]) => ({ name, reason }))
		];
	}

	async function run() {
		running = true;
		finished = false;
		sent = 0;
		created = [];
		updated = [];
		skipped = [];
		failures = [];

		for (let i = 0; i < files.length; i += BATCH) {
			const batch = files.slice(i, i + BATCH);
			try {
				absorb(await api.importNotes(batch, '', overwrite));
			} catch (err) {
				// Report the batch and keep going: the earlier ones are already
				// written, and stopping would hide the rest.
				const reason = err instanceof Error ? err.message : String(err);
				failures = [...failures, ...batch.map((f) => ({ name: f.name, reason }))];
			}
			sent = Math.min(sent + batch.length, files.length);
		}

		running = false;
		finished = true;
		onfinished();
		if (failures.length === 0) toast.success(`Imported ${summary || 'nothing'}`);
	}

	// A new selection (or opening with one) starts a run. The guard is a plain
	// variable, not state: reading `running` here made the effect depend on it,
	// so finishing a run started another one — forever.
	let started: File[] | null = null;

	$effect(() => {
		const selection = files;
		if (selection.length === 0 || selection === started) return;
		started = selection;
		void run();
	});

	function close() {
		open = false;
		onclose();
	}
</script>

<Dialog.Root bind:open>
	<Dialog.Content class="sm:max-w-xl">
		<Dialog.Header>
			<Dialog.Title>
				{#if running}Importing pages{:else}Import finished{/if}
			</Dialog.Title>
			<Dialog.Description>
				{#if running}
					{sent} of {total} file{total === 1 ? '' : 's'} uploaded
					{#if overwrite}· existing pages are replaced{:else}· existing pages are left alone{/if}
				{:else}
					{summary || 'Nothing to import'}
				{/if}
			</Dialog.Description>
		</Dialog.Header>

		<div class="grid gap-4">
			<div class="h-1.5 w-full overflow-hidden rounded bg-muted">
				<div
					class="h-full rounded bg-blue-600 transition-[width] duration-200"
					style="width: {percent}%"
				></div>
			</div>

			{#if failures.length > 0}
				<div class="grid gap-1">
					<p class="text-xs font-medium text-muted-foreground">
						{failures.length} file{failures.length === 1 ? '' : 's'} not imported
					</p>
					<ul class="max-h-40 divide-y overflow-y-auto rounded-md border text-xs">
						{#each failures as failure (failure.name + failure.reason)}
							<li class="grid gap-0.5 px-3 py-1.5">
								<code class="font-medium">{failure.name}</code>
								<span class="text-muted-foreground">{failure.reason}</span>
							</li>
						{/each}
					</ul>
				</div>
			{/if}

			{#if finished && failures.length === 0 && total > 0}
				<p class="text-xs text-muted-foreground">
					Every file landed. The listing behind this dialog is up to date.
				</p>
			{/if}
		</div>

		<Dialog.Footer>
			{#if running}
				<Button disabled>
					<LoaderCircle class="size-4 animate-spin" aria-hidden="true" />
					Importing…
				</Button>
			{:else}
				<Button onclick={close}>Close</Button>
			{/if}
		</Dialog.Footer>
	</Dialog.Content>
</Dialog.Root>
