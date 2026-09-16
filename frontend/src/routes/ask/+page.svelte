<script lang="ts">
	import { api, type Answer } from '$lib/api/client';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import { refreshPending, space } from '$lib/stores/space.svelte';
	import { pageUrl } from '$lib/notes';
	import { toast } from 'svelte-sonner';

	const KINDS = [
		{ value: 'edit', label: 'Edit' },
		{ value: 'missing', label: 'Missing info' },
		{ value: 'request', label: 'Request' }
	] as const;

	let question = $state('');
	let asking = $state(false);
	let answer = $state<Answer | null>(null);

	let kind = $state<'edit' | 'missing' | 'request'>('edit');
	let noteId = $state('');
	let body = $state('');
	let queueing = $state(false);

	async function ask() {
		const q = question.trim();
		if (!q || asking) return;
		asking = true;
		try {
			answer = await api.ask(q);
			await refreshPending();
		} catch (e) {
			toast.error(e instanceof Error ? e.message : String(e));
		} finally {
			asking = false;
		}
	}

	async function queueFeedback() {
		if (!body.trim() || queueing) return;
		queueing = true;
		try {
			await api.giveFeedback(kind, body, noteId);
			body = '';
			noteId = '';
			await refreshPending();
			toast.success('Queued for review');
		} catch (e) {
			toast.error(e instanceof Error ? e.message : String(e));
		} finally {
			queueing = false;
		}
	}
</script>

<h1 class="text-2xl font-semibold tracking-tight">Ask the librarian</h1>
<p class="mt-1 text-sm text-muted-foreground">
	Answered from the vault when possible — otherwise logged as missing information for future
	retrieval.
</p>

<form
	class="mt-5 flex flex-col gap-2 sm:flex-row"
	onsubmit={(e) => {
		e.preventDefault();
		ask();
	}}
>
	<Input bind:value={question} placeholder="What do you want to know?" autocomplete="off" />
	<Button type="submit" disabled={!question.trim() || asking}>Ask</Button>
</form>

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

<h2 class="mt-10 text-lg font-semibold">Give feedback</h2>
<p class="mt-1 text-sm text-muted-foreground">
	Correct the vault, flag missing info, or file a request. Everything lands in the capture queue for
	review.
</p>

<form
	class="mt-4 flex max-w-2xl flex-col gap-2"
	onsubmit={(e) => {
		e.preventDefault();
		queueFeedback();
	}}
>
	<div class="flex gap-2">
		<select
			bind:value={kind}
			aria-label="Feedback kind"
			class="h-9 rounded-md border bg-transparent px-2.5 text-sm"
		>
			{#each KINDS as option (option.value)}
				<option value={option.value}>{option.label}</option>
			{/each}
		</select>
		<Input bind:value={noteId} placeholder="Page (optional)" autocomplete="off" />
	</div>
	<textarea
		bind:value={body}
		placeholder="What should the librarian know?"
		aria-label="Feedback body"
		class="min-h-24 rounded-md border bg-transparent p-2.5 text-sm"></textarea>
	<div class="flex items-center gap-3">
		<Button type="submit" disabled={!body.trim() || queueing}>Queue feedback</Button>
		<a href="/capture" class="text-sm text-blue-600 hover:underline">
			View queue ({space.pending} pending)
		</a>
	</div>
</form>
