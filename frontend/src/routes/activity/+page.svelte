<script lang="ts">
	import { api, type AuditEntry } from '$lib/api/client';
	import { Button } from '$lib/components/ui/button';
	import { timeAgo } from '$lib/notes';
	import { onMount } from 'svelte';
	import { toast } from 'svelte-sonner';

	let entries = $state<AuditEntry[]>([]);

	async function load() {
		try {
			entries = (await api.audit(50)).entries;
		} catch (e) {
			toast.error(e instanceof Error ? e.message : String(e));
		}
	}

	onMount(load);
</script>

<div class="flex items-center justify-between">
	<h1 class="text-2xl font-semibold tracking-tight">Activity</h1>
	<Button variant="outline" size="sm" onclick={load}>Reload</Button>
</div>
<p class="mt-1 text-sm text-muted-foreground">Every vault and capture change, newest first.</p>

<ul class="mt-4 max-w-3xl divide-y rounded-lg border">
	{#each entries as entry (entry.ts + entry.action + entry.note_id)}
		<li class="flex gap-3 px-4 py-3">
			<span
				class="mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full bg-blue-600 text-[10px] font-bold text-white"
			>
				{entry.actor.slice(0, 1).toUpperCase()}
			</span>
			<div class="min-w-0">
				<p class="text-sm">
					<span class="font-medium">{entry.actor}</span>
					{entry.action}
					{#if entry.note_id}<code class="rounded bg-muted px-1.5 py-0.5 text-xs"
							>{entry.note_id}</code
						>{/if}
					{#if entry.detail}— {entry.detail}{/if}
				</p>
				<p class="text-xs text-muted-foreground">{timeAgo(entry.ts)}</p>
			</div>
		</li>
	{/each}
	{#if entries.length === 0}
		<li class="px-4 py-6 text-sm text-muted-foreground">No activity recorded yet.</li>
	{/if}
</ul>
