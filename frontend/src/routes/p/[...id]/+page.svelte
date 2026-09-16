<script lang="ts">
	import { page } from '$app/state';

	// Rest param arrives decoded (may itself contain slashes).
	const id = $derived(page.params.id ?? '');
</script>

<h1 class="text-2xl font-semibold tracking-tight">{id || '…'}</h1>
<p class="mt-1 text-sm text-muted-foreground">
	Full note view lands in step 3 — this stub proves dynamic routing.
</p>
