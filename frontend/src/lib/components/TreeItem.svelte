<script lang="ts">
	import { ChevronRight, FileText } from '@lucide/svelte';
	import { pageUrl, type TreeNode } from '$lib/notes';
	import { isOpen, limitFor, showMore, toggle } from '$lib/stores/tree.svelte';
	import Self from './TreeItem.svelte';

	interface Props {
		nodes: TreeNode[];
		currentId: string;
		depth?: number;
		/** Folder path this level belongs to ('' = root) — pagination key. */
		levelKey?: string;
	}

	let { nodes, currentId, depth = 0, levelKey = '' }: Props = $props();
	let limit = $derived(limitFor(levelKey));
	let visible = $derived(nodes.slice(0, limit));
	let hidden = $derived(nodes.length - limit);
</script>

<ul class="space-y-0.5" class:pl-3={depth > 0}>
	{#each visible as node (node.full)}
		<li>
			<div
				class="flex items-center gap-0.5 rounded-md {currentId === node.full
					? 'bg-blue-50'
					: 'hover:bg-muted'}"
			>
				{#if node.children.length > 0}
					<button
						aria-label="Toggle {node.name}"
						class="p-1 text-muted-foreground"
						onclick={() => toggle(node.full)}
					>
						<ChevronRight
							class="size-3.5 transition-transform {isOpen(node.full, currentId)
								? 'rotate-90'
								: ''}"
						/>
					</button>
				{:else}
					<span class="w-5.5"></span>
				{/if}
				<a
					href={pageUrl(node.full)}
					class="flex min-w-0 flex-1 items-center gap-1.5 py-1.5 pr-2 text-sm {currentId ===
					node.full
						? 'font-medium text-blue-700'
						: ''}"
					title={node.full}
				>
					<FileText class="size-3.5 shrink-0 text-muted-foreground" />
					<span class="truncate">{node.isPage ? node.name : `${node.name}/`}</span>
				</a>
			</div>
			{#if node.children.length > 0 && isOpen(node.full, currentId)}
				<Self nodes={node.children} {currentId} depth={depth + 1} levelKey={node.full} />
			{/if}
		</li>
	{/each}
	{#if hidden > 0}
		<li class="pl-6">
			<button class="text-xs text-blue-600 hover:underline" onclick={() => showMore(levelKey)}>
				Show more ({hidden} of {nodes.length})
			</button>
		</li>
	{/if}
</ul>
