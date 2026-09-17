<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { ApiError, api, type Note } from '$lib/api/client';
	import { Button } from '$lib/components/ui/button';
	import NoteView from '$lib/components/NoteView.svelte';
	import { refreshNotes } from '$lib/stores/space.svelte';
	import { onMount } from 'svelte';
	import { toast } from 'svelte-sonner';

	const id = $derived(page.params.id ?? '');
	let note = $state<Note | null>(null);
	let folder = $state<{ folders: string[]; notes: string[] } | null>(null);
	let missing = $state(false);
	let loading = $state(true);

	async function load(target: string) {
		if (!target) return;
		loading = true;
		missing = false;
		folder = null;
		try {
			note = await api.readNote(target);
		} catch (e) {
			note = null;
			if (e instanceof ApiError && e.status === 404) {
				try {
					const dir = await api.browse(target);
					if (dir.folders.length > 0 || dir.notes.length > 0) folder = dir;
					else missing = true;
				} catch {
					missing = true;
				}
			} else {
				missing = true;
			}
		} finally {
			loading = false;
		}
	}

	onMount(() => load(id));
	$effect(() => {
		const target = id;
		void load(target);
	});

	async function afterChange(newId: string | null) {
		await refreshNotes();
		if (newId === null) await goto('/');
		else await goto(`/p/${newId}`);
	}

	async function restore() {
		try {
			await api.restoreNote(id);
			await refreshNotes();
			await load(id);
		} catch (e) {
			toast.error(e instanceof Error ? e.message : String(e));
		}
	}

	function handleClick(event: MouseEvent) {
		const anchor = (event.target as HTMLElement | null)?.closest('a[data-target]');
		if (!anchor) return;
		event.preventDefault();
		const target = anchor.getAttribute('data-target');
		if (target) goto(`/p/${target}`);
	}
</script>

{#if loading}
	<p class="text-sm text-muted-foreground">Loading…</p>
{:else if note}
	<div onclick={handleClick} role="presentation">
		<NoteView {note} onchanged={afterChange} onerror={(m) => toast.error(m)} />
	</div>
{:else if folder}
	<div class="text-sm text-muted-foreground">
		<a href="/" class="hover:underline">MySharedBrain</a>
		<span class="mx-1.5">/</span>
		{id}
	</div>
	<h1 class="mt-1 mb-4 text-2xl font-semibold tracking-tight">{id.split('/').pop()}</h1>
	<ul class="divide-y rounded-lg border">
		{#each folder.folders as sub (sub)}
			<li>
				<a href={`/p/${sub}`} class="block px-4 py-3 font-medium text-blue-600 hover:bg-muted">
					📁 {sub.split('/').pop()}
				</a>
			</li>
		{/each}
		{#each folder.notes as entry (entry)}
			<li>
				<a href={`/p/${entry}`} class="block px-4 py-3 font-medium text-blue-600 hover:bg-muted">
					📄 {entry.split('/').pop()}
				</a>
			</li>
		{/each}
	</ul>
{:else if missing}
	<h1 class="text-2xl font-semibold tracking-tight">Page not found</h1>
	<p class="mt-2 text-sm text-muted-foreground">
		No page or folder at <code class="rounded bg-muted px-1.5 py-0.5">{id}</code>. Ask the librarian
		and the miss is queued for retrieval.
	</p>
	<div class="mt-4 flex flex-wrap gap-2">
		<Button href="/ask">Ask the librarian</Button>
		<Button variant="outline" href={`/search?q=${encodeURIComponent(id)}`}>Search</Button>
		<Button variant="outline" onclick={restore}>Restore from trash</Button>
	</div>
{/if}
