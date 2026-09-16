<script lang="ts">
	import { Button } from '$lib/components/ui/button';

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
	const canPrev = $derived(offset > 0);
	// Without a total, a full page is the only signal that more may follow.
	const canNext = $derived(known ? offset + limit < (total as number) : count >= limit);
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
	<div class="flex gap-2">
		<Button
			size="sm"
			variant="outline"
			disabled={disabled || !canPrev}
			onclick={() => onchange(Math.max(0, offset - limit))}
		>
			Previous
		</Button>
		<Button
			size="sm"
			variant="outline"
			disabled={disabled || !canNext}
			onclick={() => onchange(offset + limit)}
		>
			Next
		</Button>
	</div>
</div>
