<script lang="ts">
	import {
		api,
		FEEDBACK_STATUSES,
		feedbackKindLabel,
		type FeedbackEntry,
		type FeedbackStatus
	} from '$lib/api/client';
	import { Badge } from '$lib/components/ui/badge';
	import { Button } from '$lib/components/ui/button';
	import * as Select from '$lib/components/ui/select';
	import Pagination from '$lib/components/Pagination.svelte';
	import { timeAgo } from '$lib/notes';
	import { refreshPending } from '$lib/stores/space.svelte';
	import { toast } from 'svelte-sonner';

	const PAGE_SIZE = 20;
	// Tags read as metadata, not as controls: dim them so they never compete
	// with the action buttons beside them.
	const TAG = 'border-border/60 font-normal text-muted-foreground';

	const FILTERS: { value: FeedbackStatus | 'all'; label: string }[] = [
		{ value: 'pending', label: 'Pending' },
		{ value: 'approved', label: 'Approved' },
		{ value: 'applied', label: 'Applied' },
		{ value: 'rejected', label: 'Rejected' },
		{ value: 'all', label: 'All' }
	];

	let filter = $state<FeedbackStatus | 'all'>('pending');
	let entries = $state<FeedbackEntry[]>([]);
	let total = $state(0);
	let offset = $state(0);
	let loading = $state(true);

	async function load() {
		loading = true;
		try {
			const res = await api.listCapture(filter === 'all' ? undefined : filter, PAGE_SIZE, offset);
			entries = res.entries;
			total = res.total;
			// A review can empty the last page — step back instead of showing none.
			if (entries.length === 0 && offset > 0) {
				offset = Math.max(0, offset - PAGE_SIZE);
				return;
			}
		} catch (e) {
			toast.error(e instanceof Error ? e.message : String(e));
		} finally {
			loading = false;
		}
	}

	$effect(() => {
		void filter;
		offset = 0;
		void load();
	});

	async function setStatus(entry: FeedbackEntry, status: FeedbackStatus) {
		if (status === entry.status) return;
		try {
			await api.setCaptureStatus(entry.id, status);
			await load();
			await refreshPending();
			toast.success(`Marked ${status}`);
		} catch (e) {
			toast.error(e instanceof Error ? e.message : String(e));
			await load(); // put the control back to the stored state
		}
	}

	function review(entry: FeedbackEntry, verdict: 'approved') {
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
</script>

<div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
	<h1 class="text-2xl font-semibold tracking-tight">Capture queue</h1>
	<div role="group" aria-label="Filter by state" class="flex flex-wrap gap-1">
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
					<Badge variant="outline" class={TAG}>{feedbackKindLabel(entry.kind)}</Badge>
					<Badge variant="outline" class={TAG}>{entry.status}</Badge>
					{#if entry.automated}
						<Badge variant="outline" class={TAG} title="Filed by the system, not a person"
							>automated</Badge
						>
					{/if}
					<span class="text-sm font-medium">{entry.note_id || 'general'}</span>
				</div>
				<p class="mt-2 text-sm whitespace-pre-wrap">{entry.body}</p>
				<p class="mt-2 text-xs text-muted-foreground">
					{timeAgo(entry.ts)}{entry.reviewer
						? ` · reviewed by ${entry.reviewer}`
						: ''}{entry.review_note ? ` · ${entry.review_note}` : ''}
				</p>
				<div class="mt-3 flex flex-wrap items-center gap-2">
					<label class="text-xs text-muted-foreground" for="status-{entry.id}">State</label>
					<Select.Root
						type="single"
						value={entry.status}
						onValueChange={(v) => setStatus(entry, v as FeedbackStatus)}
					>
						<Select.Trigger
							id="status-{entry.id}"
							aria-label="State for {entry.kind} entry"
							class="h-8 text-xs"
						>
							{FEEDBACK_STATUSES.find((o) => o.value === entry.status)?.label ?? entry.status}
						</Select.Trigger>
						<Select.Content>
							{#each FEEDBACK_STATUSES as option (option.value)}
								<Select.Item value={option.value}>{option.label}</Select.Item>
							{/each}
						</Select.Content>
					</Select.Root>
					{#if entry.status === 'pending'}
						<!-- One action: approving endorses the entry. Every other state
						     (including Rejected) is the State control beside it. -->
						<Button size="sm" onclick={review(entry, 'approved')}>Approve</Button>
					{/if}
				</div>
			</li>
		{/each}
	</ul>
	<div class="max-w-3xl">
		<Pagination
			{total}
			limit={PAGE_SIZE}
			{offset}
			count={entries.length}
			label="entry"
			labelPlural="entries"
			disabled={loading}
			onchange={(next) => {
				offset = next;
				void load();
			}}
		/>
	</div>
{/if}
