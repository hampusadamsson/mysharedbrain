<script lang="ts">
	import { api } from '$lib/api/client';
	import EmptyState from '$lib/components/EmptyState.svelte';
	import VaultBrowser from '$lib/components/VaultBrowser.svelte';
	import { Button } from '$lib/components/ui/button';
	import { onMount } from 'svelte';
	import { toast } from 'svelte-sonner';

	// The vault at its root: folders and notes directly below it. Only two things
	// replace this view — an empty vault (nothing to browse, so offer to create
	// the first page) and a failure to read it.
	let folders = $state<string[]>([]);
	let notes = $state<string[]>([]);
	let loading = $state(true);
	let error = $state('');
	let uploading = $state(false);
	let fileInput: HTMLInputElement | undefined = $state();
	let folderInput: HTMLInputElement | undefined = $state();

	async function onUpload(e: Event) {
		const input = e.currentTarget as HTMLInputElement;
		const files = [...(input.files ?? [])];
		input.value = '';
		if (files.length === 0 || uploading) return;
		uploading = true;
		try {
			const result = await api.importNotes(files);
			const n = result.created.length + result.updated.length;
			const errs = Object.entries(result.errors);
			if (n > 0) toast.success(`Imported ${n} page${n === 1 ? '' : 's'}`);
			if (errs.length > 0) toast.error(`${errs[0][0]}: ${errs[0][1]}`);
			if (n === 0 && errs.length === 0) toast.info('Nothing imported');
			await load();
		} catch (err) {
			toast.error(err instanceof Error ? err.message : String(err));
		} finally {
			uploading = false;
		}
	}

	const plural = (n: number, one: string) => `${n} ${n === 1 ? one : one + 's'}`;
	const summary = $derived(
		`${plural(notes.length, 'page')} and ${plural(folders.length, 'folder')} at the root`
	);

	async function load() {
		loading = true;
		error = '';
		try {
			const dir = await api.browse('');
			folders = dir.folders;
			notes = dir.notes;
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
			toast.error(error);
		} finally {
			loading = false;
		}
	}

	onMount(load);
</script>

{#if loading}
	<p class="text-sm text-muted-foreground">Loading…</p>
{:else if error}
	<p
		class="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive"
	>
		{error}
	</p>
{:else if folders.length === 0 && notes.length === 0}
	<EmptyState />
{:else}
	<div class="mb-4 flex flex-wrap items-end justify-between gap-3">
		<div>
			<h1 class="text-2xl font-semibold tracking-tight">All pages</h1>
			<p class="mt-1 text-sm text-muted-foreground">{summary}</p>
		</div>
		<div class="flex gap-2">
			<Button variant="outline" size="sm" disabled={uploading} onclick={() => fileInput?.click()}>
				{uploading ? 'Importing…' : 'Upload files'}
			</Button>
			<Button variant="outline" size="sm" disabled={uploading} onclick={() => folderInput?.click()}>
				{uploading ? 'Importing…' : 'Upload folder'}
			</Button>
		</div>
	</div>
	<input
		bind:this={fileInput}
		type="file"
		multiple
		accept=".md,.markdown,.txt,text/markdown,text/plain"
		class="hidden"
		onchange={onUpload}
	/>
	<input
		bind:this={folderInput}
		type="file"
		webkitdirectory
		class="hidden"
		onchange={onUpload}
	/>
	<VaultBrowser {folders} {notes} />
{/if}
