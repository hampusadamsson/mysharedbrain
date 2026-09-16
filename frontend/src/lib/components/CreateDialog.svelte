<script lang="ts">
	import { goto } from '$app/navigation';
	import { Button } from '$lib/components/ui/button';
	import * as Dialog from '$lib/components/ui/dialog';
	import { Input } from '$lib/components/ui/input';
	import { api } from '$lib/api/client';
	import { refreshNotes } from '$lib/stores/space.svelte';
	import { toast } from 'svelte-sonner';

	interface Props {
		open: boolean;
		onCreated?: (id: string) => void;
	}

	let { open = $bindable(false), onCreated }: Props = $props();
	let id = $state('');
	let busy = $state(false);

	async function create() {
		const trimmed = id.trim();
		if (!trimmed || busy) return;
		busy = true;
		try {
			const note = await api.createNote(trimmed, '');
			id = '';
			open = false;
			await refreshNotes();
			if (onCreated) onCreated(note.id);
			else await goto(`/p/${note.id}`);
		} catch (e) {
			toast.error(e instanceof Error ? e.message : String(e));
		} finally {
			busy = false;
		}
	}
</script>

<Dialog.Root bind:open>
	<Dialog.Content>
		<Dialog.Header>
			<Dialog.Title>Create page</Dialog.Title>
			<Dialog.Description>
				Page id — use slashes for folders, e.g. <code>projects/homelab</code>.
			</Dialog.Description>
		</Dialog.Header>
		<Input
			bind:value={id}
			placeholder="new/page-id"
			autocomplete="off"
			onkeydown={(e) => e.key === 'Enter' && create()}
		/>
		<Dialog.Footer>
			<Button onclick={() => (open = false)} variant="ghost">Cancel</Button>
			<Button onclick={create} disabled={!id.trim() || busy}>Create</Button>
		</Dialog.Footer>
	</Dialog.Content>
</Dialog.Root>
