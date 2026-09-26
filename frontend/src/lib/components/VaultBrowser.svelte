<script lang="ts">
	import { pageUrl } from '$lib/notes';
	import { Button } from '$lib/components/ui/button';
	import { ArrowDownAZ, ArrowUpAZ } from '@lucide/svelte';
	import { onMount } from 'svelte';

	interface Props {
		/** Direct children of one folder: their full ids. */
		folders: string[];
		notes: string[];
		class?: string;
	}

	let { folders, notes, class: className = '' }: Props = $props();

	// Sort order persists across listings (localStorage), default A–Z.
	let ascending = $state(true);
	onMount(() => {
		try {
			ascending = localStorage.getItem('vault-sort-order') !== 'desc';
		} catch {
		/* private mode / no storage — stay ascending */
		}
	});

	function toggleSort() {
		ascending = !ascending;
		try {
			localStorage.setItem('vault-sort-order', ascending ? 'asc' : 'desc');
		} catch {
		/* ignore */
		}
	}

	const compare = $derived(
		ascending
			? (a: string, b: string) => a.localeCompare(b)
			: (a: string, b: string) => b.localeCompare(a)
	);
	const sortedFolders = $derived([...folders].sort(compare));
	const sortedNotes = $derived([...notes].sort(compare));

	// A note that is also a folder (`projects` plus `projects/a`) would otherwise
	// appear twice. The folder row covers it: /p/<id> opens the page when one
	// exists there and the listing when it does not.
	const folderSet = $derived(new Set(sortedFolders));
	const files = $derived(sortedNotes.filter((note) => !folderSet.has(note)));
	const empty = $derived(sortedFolders.length === 0 && files.length === 0);
</script>

{#if !empty}
	<div class="mb-2 flex justify-end">
		<Button
			variant="outline"
			size="sm"
			onclick={toggleSort}
			aria-pressed={ascending}
			aria-label={ascending ? 'Sort Z to A' : 'Sort A to Z'}
			title={ascending ? 'Sorted A to Z — switch to Z to A' : 'Sorted Z to A — switch to A to Z'}
		>
			{#if ascending}
				<ArrowDownAZ aria-hidden="true" />
			{:else}
				<ArrowUpAZ aria-hidden="true" />
			{/if}
			{ascending ? 'A–Z' : 'Z–A'}
		</Button>
	</div>
{/if}
<ul class="divide-y overflow-hidden rounded-lg border {className}">
	{#each sortedFolders as folder (folder)}
		<li>
			<a
				href={pageUrl(folder)}
				class="flex items-center gap-2 px-4 py-2.5 text-sm font-medium hover:bg-muted"
			>
				<span aria-hidden="true">📁</span>
				<span class="truncate">{folder.split('/').pop()}</span>
			</a>
		</li>
	{/each}
	{#each files as note (note)}
		<li>
			<a
				href={pageUrl(note)}
				class="flex items-center gap-2 px-4 py-2.5 text-sm font-medium hover:bg-muted"
			>
				<span aria-hidden="true">📄</span>
				<span class="truncate">{note.split('/').pop()}</span>
			</a>
		</li>
	{/each}
	{#if empty}
		<li class="px-4 py-3 text-sm text-muted-foreground">Empty folder.</li>
	{/if}
</ul>
