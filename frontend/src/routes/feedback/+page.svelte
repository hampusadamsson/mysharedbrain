<script lang="ts">
	import { api, FEEDBACK_KINDS } from '$lib/api/client';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import * as Select from '$lib/components/ui/select';
	import { Textarea } from '$lib/components/ui/textarea';
	import { refreshPending, space } from '$lib/stores/space.svelte';
	import { toast } from 'svelte-sonner';

	let kind = $state<'edit' | 'missing' | 'request' | 'question'>('edit');
	let noteId = $state('');
	let body = $state('');
	let queueing = $state(false);

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

<h1 class="text-2xl font-semibold tracking-tight">Give feedback</h1>
<p class="mt-1 text-sm text-muted-foreground">
	Correct the vault, flag missing info, file a request or ask an open question. Everything lands in
	the capture queue for review.
</p>

<form
	class="mt-5 flex max-w-2xl flex-col gap-2"
	onsubmit={(e) => {
		e.preventDefault();
		queueFeedback();
	}}
>
	<div class="flex gap-2">
		<Select.Root type="single" value={kind} onValueChange={(v) => (kind = v as typeof kind)}>
			<Select.Trigger aria-label="Feedback kind" class="w-36">
				{FEEDBACK_KINDS.find((o) => o.value === kind)?.label ?? kind}
			</Select.Trigger>
			<Select.Content>
				{#each FEEDBACK_KINDS as option (option.value)}
					<Select.Item value={option.value}>{option.label}</Select.Item>
				{/each}
			</Select.Content>
		</Select.Root>
		<Input bind:value={noteId} placeholder="Page (optional)" autocomplete="off" />
	</div>
	<Textarea
		bind:value={body}
		placeholder="What should the librarian know?"
		aria-label="Feedback body"
		class="min-h-24"
	/>
	<div class="flex items-center gap-3">
		<Button type="submit" disabled={!body.trim() || queueing}>Queue feedback</Button>
		<a href="/capture" class="text-sm text-blue-600 hover:underline">
			View queue ({space.pending} pending)
		</a>
	</div>
</form>

<p class="mt-8 text-sm text-muted-foreground">
	Looking for an answer instead? <a href="/ask" class="text-blue-600 hover:underline"
		>Ask the librarian</a
	>.
</p>
