<script lang="ts">
	import { api } from '$lib/api/client';
	import InteractionLog from '$lib/components/InteractionLog.svelte';

	interface Props {
		noteId: string;
		/** Bump to refetch (e.g. after an edit) without remounting the panel. */
		version?: number;
	}

	let { noteId, version = 0 }: Props = $props();
</script>

<section class="mt-8 border-t pt-4">
	<h2 class="text-xs font-bold tracking-wider text-muted-foreground">FILE LOG</h2>
	<InteractionLog
		load={(kind, limit, offset) => api.noteHistory(noteId, kind ?? undefined, limit, offset)}
		refreshKey={version}
		pageSize={20}
		emptyText="No interactions recorded yet."
	/>
</section>
