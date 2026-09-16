<script lang="ts">
	import { api, type FeedbackEntry, type FeedbackStatus } from '$lib/api/client';
	import { Badge } from '$lib/components/ui/badge';
	import { Button } from '$lib/components/ui/button';
	import * as Dialog from '$lib/components/ui/dialog';
	import { Textarea } from '$lib/components/ui/textarea';
	import { timeAgo } from '$lib/notes';
	import { refreshPending, refreshNotes } from '$lib/stores/space.svelte';
	import { onMount } from 'svelte';
	import { toast } from 'svelte-sonner';

	const FILTERS: { value: FeedbackStatus | 'all'; label: string }[] = [
		{ value: 'pending', label: 'Pending' },
		{ value: 'applied', label: 'Applied' },
		{ value: 'approved', label: 'Approved' },
		{ value: 'rejected', label: 'Rejected' },
		{ value: 'all', label: 'All' }
	];

	let filter = $state<FeedbackStatus | 'all'>('pending');
	let entries = $state<FeedbackEntry[]>([]);
	let loading = $state(true);
	let applyOpen = $state(false);
	let applying = $state<FeedbackEntry | null>(null);
	let applyContent = $state('');
	let busy = $state(false);

	async function load() {
		loading = true;
		try {
			entries = (await api.listCapture(filter === 'all' ? undefined : filter)).entries;
		} catch (e) {
			toast.error(e instanceof Error ? e.message : String(e));
		} finally {
			loading = false;
		}
	}

	onMount(load);
	$effect(() => {
		void filter;
		void load();
	});

	function review(entry: FeedbackEntry, verdict: 'approved' | 'rejected') {
		return async () => {
			try {
				await api.reviewCapture(entry.id, verdict);
				await load();
				await refreshPending();
				toast.success(`Marked ${verdict}`);
			} catch (e) {
				toast.error(e instanceof Error ? e.message : String(e));
			}
		};
	}

	async function openApply(entry: FeedbackEntry) {
		applying = entry;
		if (!entry.note_id) {
			applyContent = '';
			applyOpen = true;
			return;
		}
		let current: string;
		try {
			current = (await api.readNote(entry.note_id)).content;
		} catch {
			current = '';
		}
		const glue = current === '' ? '' : current.endsWith('\n') ? '\n' : '\n\n';
		applyContent = `${current}${glue}${entry.body}\n`;
		applyOpen = true;
	}

	async function applyFeedback() {
		if (!applying || busy) return;
		busy = true;
		try {
			const entry = applying;
			await api.reviewCapture(entry.id, 'applied', 'ui', entry.note_id ? applyContent : null);
			applyOpen = false;
			applying = null;
			await load();
			await refreshPending();
			await refreshNotes();
			toast.success('Applied to the vault');
		} catch (e) {
			toast.error(e instanceof Error ? e.message : String(e));
		} finally {
			busy = false;
		}
	}
</script>

<div class="flex items-center justify-between gap-3">
	<h1 class="text-2xl font-semibold tracking-tight">Capture queue</h1>
	<div class="flex gap-1">
		{#each FILTERS as option (option.value)}
			<Button
				size="sm"
				variant={filter === option.value ? 'default' : 'ghost'}
				onclick={() => (filter = option.value)}
			>
				{option.label}
			</Button>
		{/each}
	</div>
</div>
<p class="mt-1 text-sm text-muted-foreground">
	Reviewed and double-checked before anything touches the vault.
</p>

{#if loading}
	<p class="mt-4 text-sm text-muted-foreground">Loading…</p>
{:else if entries.length === 0}
	<p class="mt-4 text-sm text-muted-foreground">Queue is clear — nothing here.</p>
{:else}
	<ul class="mt-4 max-w-3xl space-y-3">
		{#each entries as entry (entry.id)}
			<li class="rounded-lg border p-4">
				<div class="flex flex-wrap items-center gap-2">
					<Badge variant="outline">{entry.kind}</Badge>
					<Badge variant={entry.status === 'pending' ? 'default' : 'secondary'}>
						{entry.status}
					</Badge>
					<span class="text-sm font-medium">{entry.note_id || 'general'}</span>
				</div>
				<p class="mt-2 text-sm whitespace-pre-wrap">{entry.body}</p>
				<p class="mt-2 text-xs text-muted-foreground">
					{timeAgo(entry.ts)}{entry.reviewer
						? ` · reviewed by ${entry.reviewer}`
						: ''}{entry.review_note ? ` · ${entry.review_note}` : ''}
				</p>
				{#if entry.status === 'pending'}
					<div class="mt-3 flex gap-2">
						<Button size="sm" onclick={() => openApply(entry)}>Apply</Button>
						<Button size="sm" variant="outline" onclick={review(entry, 'approved')}>Approve</Button>
						<Button size="sm" variant="ghost" onclick={review(entry, 'rejected')}>Reject</Button>
					</div>
				{/if}
			</li>
		{/each}
	</ul>
{/if}

<Dialog.Root bind:open={applyOpen}>
	<Dialog.Content class="sm:max-w-2xl">
		<Dialog.Header>
			<Dialog.Title>Apply feedback</Dialog.Title>
			<Dialog.Description>
				Review and edit, then apply to “{applying?.note_id ?? 'the vault'}”. Feedback: {applying?.body}
			</Dialog.Description>
		</Dialog.Header>
		{#if applying?.note_id}
			<Textarea
				bind:value={applyContent}
				aria-label="Content to apply"
				spellcheck="false"
				class="min-h-64 font-mono text-xs"
			></Textarea>
		{:else}
			<p class="text-sm text-muted-foreground">
				This entry has no page — applying only records the verdict.
			</p>
		{/if}
		<Dialog.Footer>
			<Button variant="ghost" onclick={() => (applyOpen = false)}>Cancel</Button>
			<Button onclick={applyFeedback} disabled={busy}>Apply to vault</Button>
		</Dialog.Footer>
	</Dialog.Content>
</Dialog.Root>
