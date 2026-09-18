<script lang="ts">
	import { page } from '$app/state';
	import {
		Activity,
		FileText,
		Inbox,
		MessageCircle,
		MessagesSquare,
		Settings
	} from '@lucide/svelte';
	import { Badge } from '$lib/components/ui/badge';
	import { buildTree } from '$lib/notes';
	import { space } from '$lib/stores/space.svelte';
	import TreeItem from './TreeItem.svelte';

	const currentId = $derived(
		page.url.pathname.startsWith('/p/') ? decodeURIComponent(page.url.pathname.slice(3)) : ''
	);
	const tree = $derived(buildTree(space.notes));

	const NAV = [
		{ href: '/', label: 'Pages', icon: FileText },
		{ href: '/ask', label: 'Ask the librarian', icon: MessagesSquare },
		{ href: '/feedback', label: 'Give feedback', icon: MessageCircle },
		{ href: '/capture', label: 'Capture queue', icon: Inbox, badge: true },
		{ href: '/activity', label: 'Activity', icon: Activity },
		{ href: '/settings', label: 'Settings', icon: Settings }
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
	PAGE TREE · {space.notes.length}
</div>
<div class="flex-1 overflow-y-auto px-2 pb-2">
	{#if space.notes.length === 0}
		<p class="px-2.5 py-1.5 text-sm text-muted-foreground">No pages yet</p>
	{:else}
		<TreeItem nodes={tree} {currentId} />
	{/if}
</div>

<div class="border-t px-4 py-3">
	<a href="/feedback" class="text-[13px] text-blue-600 hover:underline">Give feedback</a>
</div>
