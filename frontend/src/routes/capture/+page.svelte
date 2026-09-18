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
	import Markdown from '$lib/components/Markdown.svelte';
	import Pagination from '$lib/components/Pagination.svelte';
	import { timeAgo } from '$lib/notes';
	import { refreshPending } from '$lib/stores/space.svelte';
	import { toast } from 'svelte-sonner';

	const PAGE_SIZE = 20;
	//: Bodies longer than this collapse to four lines with a Show more toggle.
	const CLAMP_AT = 240;
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
	let expanded = $state(new Set<string>());

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

	function toggleExpanded(id: string) {
		const next = new Set(expanded);
		if (next.has(id)) next.delete(id);
		else next.add(id);
		expanded = next;
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
			{@const long = entry.body.length > CLAMP_AT}
			{@const open = expanded.has(entry.id)}
			{@const meta = [entry.reviewer && `reviewed by ${entry.reviewer}`, entry.review_note]
				.filter(Boolean)
				.join(' · ')}
			<li class="overflow-hidden rounded-lg border bg-card shadow-xs">
				<!-- header: what it is, on which note, when -->
				<div class="flex flex-wrap items-center gap-x-2 gap-y-1 px-3 py-2">
					<Badge variant="outline" class={TAG}>{feedbackKindLabel(entry.kind)}</Badge>
					<Badge variant="outline" class={TAG}>{entry.status}</Badge>
					{#if entry.automated}
						<Badge variant="outline" class={TAG} title="Filed by the system, not a person"
							>automated</Badge
						>
					{/if}
					<span class="text-sm font-medium">{entry.note_id || 'general'}</span>
					<span class="ml-auto text-xs whitespace-nowrap text-muted-foreground" title={entry.ts}>
						{timeAgo(entry.ts)}
					</span>
				</div>
				<!-- body: markdown, compact, clamped until expanded -->
				<div class="border-t px-3 py-2">
					<Markdown
						content={entry.body}
						breaks
						class="wiki-body-compact {long && !open ? 'line-clamp-4' : ''}"
					/>
					{#if long}
						<button
							type="button"
							class="mt-1 text-xs font-medium text-blue-600 hover:underline"
							aria-expanded={open}
							onclick={() => toggleExpanded(entry.id)}
						>
							{open ? 'Show less' : 'Show more'}
						</button>
					{/if}
				</div>
				{#if meta}
					<p class="border-t px-3 py-1.5 text-xs text-muted-foreground">{meta}</p>
				{/if}
				<!-- actions -->
				<div class="flex flex-wrap items-center gap-2 border-t bg-muted/40 px-3 py-2">
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
