<script lang="ts">
	import { pageUrl } from '$lib/notes';

	interface Props {
		/** Direct children of one folder: their full ids. */
		folders: string[];
		notes: string[];
		class?: string;
	}

	let { folders, notes, class: className = '' }: Props = $props();

	// A note that is also a folder (`projects` plus `projects/a`) would otherwise
	// appear twice. The folder row covers it: /p/<id> opens the page when one
	// exists there and the listing when it does not.
	const folderSet = $derived(new Set(folders));
	const files = $derived(notes.filter((note) => !folderSet.has(note)));
</script>

<ul class="divide-y overflow-hidden rounded-lg border {className}">
	{#each folders as folder (folder)}
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
	{#if folders.length === 0 && files.length === 0}
		<li class="px-4 py-3 text-sm text-muted-foreground">Empty folder.</li>
	{/if}
</ul>
