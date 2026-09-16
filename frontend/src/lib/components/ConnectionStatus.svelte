<script lang="ts">
	import type { CheckResult } from '$lib/api/client';
	import { Check, LoaderCircle, X } from '@lucide/svelte';

	interface Props {
		/** A check is in flight. */
		checking: boolean;
		/** The last result, if any. */
		result?: CheckResult;
		/** Shown while checking, e.g. "Connecting…" or "Asking the model…". */
		checkingText?: string;
	}

	let { checking, result, checkingText = 'Checking…' }: Props = $props();
</script>

{#if checking || result}
	<div class="flex items-start gap-2 border-b px-6 pb-3 text-xs">
		{#if checking}
			<LoaderCircle class="mt-px size-3.5 shrink-0 animate-spin text-muted-foreground" />
			<span class="text-muted-foreground">{checkingText}</span>
		{:else if result?.ok}
			<Check class="mt-px size-3.5 shrink-0 text-emerald-600" />
			<span class="text-emerald-700 dark:text-emerald-500">
				ok · {result.detail}{result.tools.length > 0 ? ` · ${result.tools.join(', ')}` : ''}
			</span>
		{:else}
			<X class="mt-px size-3.5 shrink-0 text-destructive" />
			<span class="text-destructive">failed · {result?.detail}</span>
		{/if}
	</div>
{/if}
