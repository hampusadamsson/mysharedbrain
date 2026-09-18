<script lang="ts">
	import * as Dialog from '$lib/components/ui/dialog';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import { api } from '$lib/api/client';

	interface Props {
		open: boolean;
		/** Currently chosen note id, if any — highlighted in the list. */
		value?: string | null;
		title?: string;
		onselect: (id: string) => void;
	}

	let {
		open = $bindable(false),
		value = null,
		title = 'Choose a note',
		onselect
	}: Props = $props();

	let query = $state('');
	let results = $state<string[]>([]);
	let loading = $state(false);
	let timer: ReturnType<typeof setTimeout> | null = null;
	let wasOpen = false;

	async function load() {
		loading = true;
		try {
			if (query.trim()) {
				const res = await api.search(query.trim(), 30, 0, false);
				results = [...new Set([...res.names, ...res.content.map((h) => h.id)])];
			} else {
				const res = await api.listNotes('', 50, 0);
				results = res.notes;
			}
		} catch {
			results = [];
		} finally {
			loading = false;
		}
	}

	function schedule() {
		if (timer) clearTimeout(timer);
		timer = setTimeout(load, 200);
	}

	function pick(id: string) {
		onselect(id);
		open = false;
	}

	$effect(() => {
		// Reset only on the open transition — `query` must not be a dependency
		// here, or every keystroke would re-run this and clear itself.
		if (open && !wasOpen) {
			query = '';
			void load();
		}
		wasOpen = open;
	});
</script>

<Dialog.Root bind:open>
	<Dialog.Content>
		<Dialog.Header>
			<Dialog.Title>{title}</Dialog.Title>
			<Dialog.Description>Search the vault by name or content.</Dialog.Description>
		</Dialog.Header>
		<Input
			bind:value={query}
			oninput={schedule}
			placeholder="Search notes…"
			autocomplete="off"
			aria-label="Search notes"
		/>
		<div class="max-h-72 overflow-auto rounded-md border">
			{#if loading}
				<p class="p-3 text-sm text-muted-foreground">Searching…</p>
			{:else if results.length === 0}
				<p class="p-3 text-sm text-muted-foreground">No notes found.</p>
			{:else}
				<ul class="divide-y">
					{#each results as id (id)}
						<li>
							<button
								type="button"
								class="w-full px-3 py-2 text-left text-sm hover:bg-muted"
								class:bg-muted={id === value}
								onclick={() => pick(id)}
							>
								{id}
							</button>
						</li>
					{/each}
				</ul>
			{/if}
		</div>
		<Dialog.Footer>
			<Button variant="ghost" onclick={() => (open = false)}>Cancel</Button>
		</Dialog.Footer>
	</Dialog.Content>
</Dialog.Root>
