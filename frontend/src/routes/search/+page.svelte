<script lang="ts">
	import { page } from '$app/state';
	import { api, type SearchResult } from '$lib/api/client';
	import { pageUrl } from '$lib/notes';
	import { onMount } from 'svelte';

	const q = $derived(page.url.searchParams.get('q') ?? '');
	let results = $state<SearchResult | null>(null);

	async function run(query: string) {
		if (!query.trim()) {
			results = null;
			return;
		}
		try {
			results = await api.search(query, 20);
		} catch {
			results = null;
		}
	}

	onMount(() => run(q));

	$effect(() => {
		run(q);
	});

	function ids(): string[] {
		if (!results) return [];
		return [...new Set([...results.names, ...results.content.map((h) => h.id)])];
	}
</script>

<h1 class="text-2xl font-semibold tracking-tight">Search results for “{q}”</h1>
{#if results}
	<ul class="mt-4 divide-y rounded-lg border">
		{#each ids() as id (id)}
			<li>
				<a href={pageUrl(id)} class="block px-4 py-3 hover:bg-muted">
					<div class="font-medium text-blue-600">{id}</div>
					{#each results.content.find((h) => h.id === id)?.excerpts.slice(0, 2) ?? [] as ex (ex)}
						<span class="block truncate text-sm text-muted-foreground">{ex}</span>
					{/each}
				</a>
			</li>
		{/each}
		{#if ids().length === 0}
			<li class="px-4 py-6 text-sm text-muted-foreground">
				No pages match. Try asking the librarian — a miss gets queued for retrieval.
			</li>
		{/if}
	</ul>
{/if}
