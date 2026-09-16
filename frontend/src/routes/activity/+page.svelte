<script lang="ts">
	import { api } from '$lib/api/client';
	import { Button } from '$lib/components/ui/button';
	import InteractionLog from '$lib/components/InteractionLog.svelte';

	let refreshKey = $state(0);
</script>

<div class="flex items-center justify-between">
	<h1 class="text-2xl font-semibold tracking-tight">Activity</h1>
	<Button variant="outline" size="sm" onclick={() => (refreshKey += 1)}>Reload</Button>
</div>
<p class="mt-1 text-sm text-muted-foreground">
	Every vault and capture change, newest first — librarian activity is tagged. Filter by kind.
</p>

<InteractionLog
	load={(kind, limit, offset) => api.audit(limit, offset, kind ?? undefined)}
	{refreshKey}
	pageSize={25}
	emptyText="No activity recorded yet."
/>
