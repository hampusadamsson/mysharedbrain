<script lang="ts">
	import { page } from '$app/state';
	import { Activity, FileText, Inbox, MessagesSquare } from '@lucide/svelte';
	import { Badge } from '$lib/components/ui/badge';
	import { pageUrl } from '$lib/notes';
	import { space } from '$lib/stores/space.svelte';

	const NAV = [
		{ href: '/', label: 'Pages', icon: FileText },
		{ href: '/ask', label: 'Ask the librarian', icon: MessagesSquare },
		{ href: '/capture', label: 'Capture queue', icon: Inbox, badge: true },
		{ href: '/activity', label: 'Activity', icon: Activity }
	];

	function active(href: string): boolean {
		const path = page.url.pathname;
		if (href === '/') return path === '/' || path.startsWith('/p/') || path.startsWith('/search');
		return path === href || path.startsWith(href + '/');
	}
</script>

<div class="flex items-center gap-2.5 px-3 pt-1 pb-3">
	<span
		class="flex size-8 items-center justify-center rounded-md bg-gradient-to-br from-blue-600 to-blue-900 text-sm font-bold text-white"
	>
		M
	</span>
	<div>
		<div class="text-sm font-semibold">MySharedBrain</div>
		<div class="text-xs text-muted-foreground">Team space</div>
	</div>
</div>

<nav class="space-y-0.5 px-2">
	{#each NAV as item (item.href)}
		<a
			href={item.href}
			class="flex items-center gap-2.5 rounded-md px-2.5 py-2 text-sm font-medium transition-colors {active(
				item.href
			)
				? 'bg-blue-50 text-blue-700'
				: 'hover:bg-muted'}"
		>
			<item.icon class="size-4" />
			{item.label}
			{#if item.badge && space.pending > 0}
				<Badge class="ml-auto">{space.pending}</Badge>
			{/if}
		</a>
	{/each}
</nav>

<div class="px-4 pt-4 pb-1 text-[11px] font-bold tracking-wider text-muted-foreground">
	PAGES · {space.notes.length}
</div>
<ul class="flex-1 space-y-0.5 overflow-y-auto px-2 pb-2">
	{#if space.notes.length === 0}
		<li class="px-2.5 py-1.5 text-sm text-muted-foreground">No pages yet</li>
	{:else}
		{#each space.notes as id (id)}
			<li>
				<a
					href={pageUrl(id)}
					class="block truncate rounded-md px-2.5 py-1.5 text-sm hover:bg-muted {page.url
						.pathname === pageUrl(id)
						? 'bg-blue-50 font-medium text-blue-700'
						: ''}"
					title={id}
				>
					{id}
				</a>
			</li>
		{/each}
	{/if}
</ul>

<div class="border-t px-4 py-3">
	<a href="/ask" class="text-[13px] text-blue-600 hover:underline">Give feedback</a>
</div>
