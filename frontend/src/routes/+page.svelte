<script lang="ts">
	import { api } from '$lib/api/client';
	import EmptyState from '$lib/components/EmptyState.svelte';
	import VaultBrowser from '$lib/components/VaultBrowser.svelte';
	import { onMount } from 'svelte';
	import { toast } from 'svelte-sonner';

	// The vault at its root: folders and notes directly below it. Only two things
	// replace this view — an empty vault (nothing to browse, so offer to create
	// the first page) and a failure to read it.
	let folders = $state<string[]>([]);
	let notes = $state<string[]>([]);
	let loading = $state(true);
	let error = $state('');

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
	<h1 class="text-2xl font-semibold tracking-tight">All pages</h1>
	<p class="mt-1 mb-4 text-sm text-muted-foreground">{summary}</p>
	<VaultBrowser {folders} {notes} />
{/if}
