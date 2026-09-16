<script lang="ts">
	import { goto } from '$app/navigation';
	import { Brain, Menu, Plus, Search } from '@lucide/svelte';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import { api, type SearchResult } from '$lib/api/client';
	import { pageUrl } from '$lib/notes';
	import CreateDialog from '$lib/components/CreateDialog.svelte';

	interface Props {
		onmenu: () => void;
	}

	let { onmenu }: Props = $props();
	let q = $state('');
	let results = $state<SearchResult | null>(null);
	let createOpen = $state(false);
	let timer: ReturnType<typeof setTimeout> | null = null;

	function schedule() {
		if (timer) clearTimeout(timer);
		timer = setTimeout(() => quickSearch(q), 200);
	}

	async function quickSearch(query: string) {
		if (!query.trim()) {
			results = null;
			return;
		}
		try {
			const res = await api.search(query, 8);
			results = res;
		} catch {
			results = null;
		}
	}

	function ids(): string[] {
		if (!results) return [];
		return [...new Set([...results.names, ...results.content.map((h) => h.id)])];
	}

	function excerptFor(id: string): string | null {
		const hit = results?.content.find((h) => h.id === id);
		return hit?.excerpts[0] ?? null;
	}

	async function openNote(id: string) {
		results = null;
		q = '';
		await goto(pageUrl(id));
	}
</script>

<header class="sticky top-0 z-50 flex h-14 items-center gap-3 border-b bg-background px-4">
	<Button variant="ghost" size="icon" class="md:hidden" onclick={onmenu} aria-label="Menu">
		<Menu class="size-5" />
	</Button>
	<a href="/" class="flex items-center gap-2 font-semibold">
		<Brain class="size-5 text-blue-600" />
		<span class="hidden sm:inline">MySharedBrain</span>
	</a>
	<div class="relative mx-auto w-full max-w-md">
		<Search class="absolute top-2.5 left-3 size-4 text-muted-foreground" />
		<Input
			bind:value={q}
			oninput={schedule}
			onkeydown={(e) => {
				if (e.key === 'Enter' && q.trim()) {
					results = null;
					goto(`/search?q=${encodeURIComponent(q.trim())}`);
				}
				if (e.key === 'Escape') results = null;
			}}
			placeholder="Search notes"
			autocomplete="off"
			class="bg-muted pl-9"
		/>
		{#if results}
			<div
				class="absolute top-11 right-0 left-0 max-h-96 overflow-auto rounded-lg border bg-popover p-1 shadow-lg"
			>
				{#each ids() as id (id)}
					<button
						class="w-full rounded-md px-3 py-2 text-left hover:bg-muted"
						onclick={() => openNote(id)}
					>
						<div class="text-sm font-medium">{id}</div>
						{#if excerptFor(id)}
							<div class="truncate text-xs text-muted-foreground">{excerptFor(id)}</div>
						{/if}
					</button>
				{/each}
				<button
					class="w-full rounded-md px-3 py-2 text-left text-sm font-medium text-blue-600 hover:bg-muted"
					onclick={() => {
						const query = q;
						results = null;
						goto(`/search?q=${encodeURIComponent(query)}`);
					}}
				>
					See all results
				</button>
			</div>
		{/if}
	</div>
	<Button onclick={() => (createOpen = true)}>
		<Plus class="size-4" /> <span class="hidden sm:inline">Create</span>
	</Button>
	<span
		class="flex size-7 shrink-0 items-center justify-center rounded-full bg-blue-600 text-xs font-bold text-white"
		title="You"
	>
		Y
	</span>
</header>

<CreateDialog bind:open={createOpen} />
