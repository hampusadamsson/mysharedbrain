<script lang="ts">
	import { api, type Answer } from '$lib/api/client';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import { refreshPending } from '$lib/stores/space.svelte';
	import { pageUrl } from '$lib/notes';
	import { LoaderCircle } from '@lucide/svelte';
	import { onMount } from 'svelte';
	import { toast } from 'svelte-sonner';

	let question = $state('');
	let asking = $state(false);
	let answer = $state<Answer | null>(null);
	let error = $state('');
	// null = not loaded yet; the run refuses server-side too, this is just the signpost.
	let askEnabled = $state<boolean | null>(null);
	let timeoutSeconds = $state(60);

	onMount(async () => {
		try {
			const settings = await api.getSettings();
			askEnabled = settings.config.ask.enabled;
			// ?? keeps the hint readable if an older backend omits the field
			timeoutSeconds = settings.config.ask.timeout_seconds ?? 60;
		} catch {
			askEnabled = true;
		}
	});

	async function ask() {
		const q = question.trim();
		if (!q || asking) return;
		asking = true;
		answer = null;
		error = '';
		try {
			answer = await api.ask(q);
			await refreshPending();
		} catch (e) {
			// Stays on screen: a timeout or a provider error is the answer here.
			error = e instanceof Error ? e.message : String(e);
			toast.error(error);
		} finally {
			asking = false;
		}
	}
</script>

<h1 class="text-2xl font-semibold tracking-tight">Ask the librarian</h1>
<p class="mt-1 text-sm text-muted-foreground">
	Answered from the vault when possible — otherwise filed as an automated question for future
	retrieval.
</p>

{#if askEnabled === false}
	<p
		class="mt-5 rounded-md border border-border/60 bg-muted/40 px-3 py-2 text-sm text-muted-foreground"
	>
		Asking is disabled in the settings. Turn it on under Settings · Ask when you are ready.
	</p>
{:else}
	<form
		class="mt-5 flex flex-col gap-2 sm:flex-row"
		onsubmit={(e) => {
			e.preventDefault();
			ask();
		}}
	>
		<Input bind:value={question} placeholder="What do you want to know?" autocomplete="off" />
		<Button type="submit" disabled={!question.trim() || asking} aria-busy={asking}>
			{#if asking}
				<LoaderCircle class="size-4 animate-spin" aria-hidden="true" />
				Thinking…
			{:else}
				Ask
			{/if}
		</Button>
	</form>

	{#if asking}
		<p
			class="mt-3 flex items-center gap-2 text-sm text-muted-foreground"
			role="status"
			aria-live="polite"
		>
			<LoaderCircle class="size-4 shrink-0 animate-spin" aria-hidden="true" />
			Reading the vault — this can take up to {timeoutSeconds}s.
		</p>
	{/if}
{/if}

{#if error}
	<p
		class="mt-4 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive"
	>
		{error}
	</p>
{/if}

{#if answer}
	<div class="mt-4 rounded-lg border p-4">
		<p class="text-sm">{answer.message}</p>
		{#if answer.note_ids.length > 0}
			<div class="mt-3 flex flex-wrap gap-2">
				{#each answer.note_ids as id (id)}
					<a
						href={pageUrl(id)}
						class="rounded-md border px-3 py-1.5 text-sm font-medium hover:bg-muted"
					>
						{id}
					</a>
				{/each}
			</div>
		{/if}
	</div>
{/if}

<p class="mt-8 text-sm text-muted-foreground">
	Want to correct or add something instead? <a
		href="/feedback"
		class="text-blue-600 hover:underline">Give feedback</a
	>.
</p>
