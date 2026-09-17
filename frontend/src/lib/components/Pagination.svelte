<script lang="ts">
	import { tick } from 'svelte';
	import * as Pagination from '$lib/components/ui/pagination';

	interface Props {
		/**
		 * Rows matching the current filter, across all pages. Optional: when a
		 * server does not report it (version skew) the control degrades to the
		 * page window instead of rendering `NaN`.
		 */
		total?: number;
		limit: number;
		offset: number;
		/** Rows actually rendered on this page. */
		count: number;
		/** Called with the new offset when a page button is used. */
		onchange: (offset: number) => void;
		/** Noun for the range text, e.g. "entry". */
		label?: string;
		/** Plural form, e.g. "entries" — English pluralisation is not a suffix. */
		labelPlural?: string;
		disabled?: boolean;
	}

	let {
		total,
		limit,
		offset,
		count,
		onchange,
		label = 'item',
		labelPlural = 'items',
		disabled = false
	}: Props = $props();

	const known = $derived(typeof total === 'number' && Number.isFinite(total));
	const from = $derived(known && total === 0 ? 0 : offset + 1);
	// Without a reported total, the honest upper bound is this page's last row.
	const to = $derived(known ? Math.min(offset + limit, total as number) : offset + count);
	// A full page is the only signal that more may follow.
	const canNext = $derived(known ? offset + limit < (total as number) : count >= limit);
	const currentPage = $derived(Math.floor(offset / limit) + 1);
	// Controlled from props: the parent owns the offset, so after reporting a
	// navigation the binding is reset to what is rendered — the control never
	// drifts, even when the parent keeps the old offset (e.g. a failed load).
	// Writable on purpose: the page control writes through bind:page and go()
	// resets it after reporting, so this never drifts from the parent's offset.
	// eslint-disable-next-line svelte/prefer-writable-derived
	let pageNum = $state(1);
	$effect(() => {
		pageNum = currentPage;
	});
	async function go(p: number) {
		onchange((p - 1) * limit);
		await tick();
		pageNum = currentPage;
	}
	// The page control needs a finite item count: with no total, pretend one
	// extra page exists exactly when more rows may follow.
	const rootCount = $derived(known ? (total as number) : offset + count + (canNext ? limit : 0));
</script>

<div class="flex flex-wrap items-center justify-between gap-2 pt-3">
	<p class="text-xs text-muted-foreground">
		{#if known}
			Showing {from}–{to} of {total}
			{total === 1 ? label : labelPlural}
		{:else}
			Showing {from}–{to}
		{/if}
	</p>
	<Pagination.Root bind:page={pageNum} count={rootCount} perPage={limit} onPageChange={go}>
		<Pagination.Content class="gap-2">
			<Pagination.Item>
				<Pagination.Previous aria-label="Previous" {disabled} />
			</Pagination.Item>
			<Pagination.Item>
				<Pagination.Next aria-label="Next" {disabled} />
			</Pagination.Item>
		</Pagination.Content>
	</Pagination.Root>
</div>
