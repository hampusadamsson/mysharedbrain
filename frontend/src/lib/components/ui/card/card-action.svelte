<script lang="ts">
	import { cn, type WithElementRef } from '$lib/utils.js';
	import type { HTMLAttributes } from 'svelte/elements';

	let {
		ref = $bindable(null),
		class: className,
		children,
		...restProps
	}: WithElementRef<HTMLAttributes<HTMLDivElement>> = $props();
</script>

<div
	bind:this={ref}
	data-slot="card-action"
	class={cn(
		// Mobile: own row after the description (DOM order is title, description,
		// action), full width so the buttons can wrap. Desktop (sm+): the
		// conventional top-right slot beside the title.
		'col-span-full justify-self-stretch sm:col-span-1 sm:col-start-2 sm:row-span-2 sm:row-start-1 sm:self-start sm:justify-self-end',
		className
	)}
	{...restProps}
>
	{@render children?.()}
</div>
