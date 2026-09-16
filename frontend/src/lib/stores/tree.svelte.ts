// Tree UI state: per-level pagination + collapsed folders.
import { SvelteMap, SvelteSet } from 'svelte/reactivity';
import { TREE_PAGE_SIZE } from '$lib/notes';

export const collapsed = new SvelteSet<string>();
export const limits = new SvelteMap<string, number>();

export function limitFor(full: string): number {
	return limits.get(full) ?? TREE_PAGE_SIZE;
}

export function showMore(full: string) {
	limits.set(full, limitFor(full) + TREE_PAGE_SIZE);
}

export function toggle(full: string) {
	if (collapsed.has(full)) collapsed.delete(full);
	else collapsed.add(full);
}

/** Collapsed unless it (or a descendant) is the open note. */
export function isOpen(full: string, currentId: string): boolean {
	if (!collapsed.has(full)) return true;
	return currentId === full || currentId.startsWith(full + '/');
}
