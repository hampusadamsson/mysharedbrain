<script lang="ts">
	import { api } from '$lib/api/client';
	import EmptyState from '$lib/components/EmptyState.svelte';
	import VaultBrowser from '$lib/components/VaultBrowser.svelte';
	import { Button } from '$lib/components/ui/button';
	import { Checkbox } from '$lib/components/ui/checkbox';
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
	// Replace pages that already exist? Visible, because importing over an
	// existing note is the one destructive thing this view can do.
	let overwrite = $state(true);
	let fileInput: HTMLInputElement | undefined = $state();
	let folderInput: HTMLInputElement | undefined = $state();

	async function onUpload(e: Event) {
		const input = e.currentTarget as HTMLInputElement;
		const files = [...(input.files ?? [])];
		input.value = '';
		if (files.length === 0 || uploading) return;
		uploading = true;
		try {
			const result = await api.importNotes(files, '', overwrite);
			// Say what actually happened: with replacement off, every existing page
			// is skipped, and "nothing imported" would read as a failure.
			const parts: string[] = [];
			if (result.created.length) parts.push(`${result.created.length} new`);
			if (result.updated.length) parts.push(`${result.updated.length} replaced`);
			if (result.skipped.length) parts.push(`${result.skipped.length} skipped`);
			const errs = Object.entries(result.errors);
			if (errs.length) parts.push(`${errs.length} failed`);
			if (parts.length) toast.success(`Imported: ${parts.join(', ')}`);
			else toast.info('Nothing to import');
			if (errs.length) toast.error(`${errs[0][0]}: ${errs[0][1]}`);
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
{:else}
	<!-- The upload controls are not part of the "has pages" branch: importing a
	     folder is how an empty vault gets filled, which is the one case where
	     hiding them would be absurd. -->
	<div class="mb-4 flex flex-wrap items-end justify-between gap-3">
		<div>
			{#if folders.length === 0 && notes.length === 0}
				<h1 class="text-2xl font-semibold tracking-tight">All pages</h1>
				<p class="mt-1 text-sm text-muted-foreground">
					Nothing here yet — create a page, or import files.
				</p>
			{:else}
				<h1 class="text-2xl font-semibold tracking-tight">All pages</h1>
				<p class="mt-1 text-sm text-muted-foreground">{summary}</p>
			{/if}
		</div>
		<div class="flex flex-wrap items-center gap-3">
			<label
				class="flex cursor-pointer items-center gap-1.5 text-xs text-muted-foreground"
				title="Off: a page that already exists is left alone and reported as skipped"
			>
				<Checkbox
					bind:checked={overwrite}
					aria-label="Replace pages that already exist"
					disabled={uploading}
				/>
				Replace existing
			</label>
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
	<input bind:this={folderInput} type="file" webkitdirectory class="hidden" onchange={onUpload} />
	{#if folders.length === 0 && notes.length === 0}
		<EmptyState />
	{:else}
		<VaultBrowser {folders} {notes} />
	{/if}
{/if}
