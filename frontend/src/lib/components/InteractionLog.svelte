<script lang="ts">
	import type { AuditEntry, FileStats } from '$lib/api/client';
	import { Badge } from '$lib/components/ui/badge';
	import { Button } from '$lib/components/ui/button';
	import Pagination from '$lib/components/Pagination.svelte';
	import { AUDIT_KINDS } from '$lib/audit';
	import { isLibrarian, timeAgo } from '$lib/notes';
	import { toast } from 'svelte-sonner';

	export interface InteractionPage {
		entries: AuditEntry[];
		total?: number;
		stats?: FileStats;
	}

	interface Props {
		/**
		 * Fetches one page. Both scopes plug in here: the whole log
		 * (`api.audit`) or one file (`api.noteHistory`).
		 */
		load: (kind: string | null, limit: number, offset: number) => Promise<InteractionPage>;
		pageSize?: number;
		/** Bump to refetch without losing the filter (e.g. after an edit). */
		refreshKey?: number;
		emptyText?: string;
	}

	let {
		load,
		pageSize = 20,
		refreshKey = 0,
		emptyText = 'Nothing recorded yet.'
	}: Props = $props();

	let kind = $state<string | null>(null);
	let offset = $state(0);
	let entries = $state<AuditEntry[]>([]);
	let stats = $state<FileStats | null>(null);
	let total = $state<number | undefined>(undefined);
	let loading = $state(true);

	async function fetchPage() {
		loading = true;
		try {
			const res = await load(kind, pageSize, offset);
			entries = res.entries;
			stats = res.stats ?? null;
			total = res.total;
			// A filter can empty the last page — step back instead of showing none.
			if (entries.length === 0 && offset > 0) {
				offset = Math.max(0, offset - pageSize);
			}
		} catch (e) {
			toast.error(e instanceof Error ? e.message : String(e));
		} finally {
			loading = false;
		}
	}

	// The single data path: scope load fn, filter, page and caller all refetch.
	$effect(() => {
		void load;
		void refreshKey;
		void kind;
		void offset;
		void pageSize;
		void fetchPage();
	});

	const counted = $derived(AUDIT_KINDS.filter((k) => (stats?.counts[k.kind] ?? 0) > 0));

	function pick(next: string | null) {
		kind = next;
		offset = 0;
	}
</script>

{#if stats && stats.total > 0}
	<div class="mt-3 flex flex-wrap gap-1.5">
		<Button size="sm" variant={kind === null ? 'default' : 'outline'} onclick={() => pick(null)}>
			All {stats.total}
		</Button>
		{#each counted as option (option.kind)}
			<Button
				size="sm"
				variant={kind === option.kind ? 'default' : 'outline'}
				onclick={() => pick(option.kind)}
			>
				{stats.counts[option.kind]}
				{option.label}
			</Button>
		{/each}
	</div>
{/if}

{#if stats && (stats.first_seen || stats.last_seen)}
	<p class="mt-2 text-xs text-muted-foreground">
		{#if stats.first_seen}first {timeAgo(
				stats.first_seen
			)}{/if}{#if stats.first_seen && stats.last_seen}
			·{/if}{#if stats.last_seen}last {timeAgo(stats.last_seen)}{/if}
	</p>
{/if}

{#if loading && entries.length === 0}
	<p class="mt-3 text-sm text-muted-foreground">Loading…</p>
{:else if entries.length === 0}
	<p class="mt-3 text-sm text-muted-foreground">
		{kind === null ? emptyText : 'Nothing of that kind here.'}
	</p>
{:else}
	<ul class="mt-3 divide-y rounded-lg border">
		{#each entries as entry (entry.ts + entry.action + entry.actor + entry.note_id)}
			<li class="flex gap-3 px-4 py-2.5">
				<span
					class="mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full text-[10px] font-bold text-white {isLibrarian(
						entry.actor
					)
						? 'bg-violet-600'
						: 'bg-blue-600'}"
				>
					{entry.actor.slice(0, 1).toUpperCase()}
				</span>
				<div class="min-w-0">
					<p class="flex flex-wrap items-center gap-1.5 text-sm">
						<span class="font-medium">{entry.actor}</span>
						{#if isLibrarian(entry.actor)}
							<Badge variant="secondary">Librarian</Badge>
						{/if}
						<span>{entry.action}</span>
						<Badge variant="outline">{entry.kind}</Badge>
						{#if entry.note_id}<code class="rounded bg-muted px-1.5 py-0.5 text-xs"
								>{entry.note_id}</code
							>{/if}
					</p>
					<p class="text-xs text-muted-foreground">
						{timeAgo(entry.ts)}{entry.detail ? ` · ${entry.detail}` : ''}
					</p>
				</div>
			</li>
		{/each}
	</ul>
	<Pagination
		{total}
		limit={pageSize}
		{offset}
		count={entries.length}
		label="interaction"
		labelPlural="interactions"
		disabled={loading}
		onchange={(next) => (offset = next)}
	/>
{/if}
