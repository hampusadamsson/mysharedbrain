// Pure view helpers (unit-tested, no DOM).
export const TREE_PAGE_SIZE = 50;

/** Shareable page URL for a note id or folder path. */
export function pageUrl(id: string): string {
	return '/p/' + id.split('/').map(encodeURIComponent).join('/');
}

export function timeAgo(ts: string): string {
	const s = Math.floor((Date.now() - new Date(ts).getTime()) / 1000);
	if (s < 60) return 'just now';
	if (s < 3600) return `${Math.floor(s / 60)}m ago`;
	if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
	return `${Math.floor(s / 86400)}d ago`;
}

export interface TreeNode {
	name: string;
	full: string;
	isPage: boolean;
	children: TreeNode[];
}

/** Nested folder tree from flat note ids (folders and leaves sorted). */
export function buildTree(ids: string[]): TreeNode[] {
	const pageSet = new Set(ids);
	const draw = (prefix: string): TreeNode[] => {
		const folders = new Map<string, string>();
		const leaves: string[] = [];
		for (const id of ids) {
			if (prefix && id !== prefix && !id.startsWith(prefix + '/')) continue;
			const rest = prefix ? id.slice(prefix.length + 1) : id;
			if (!rest) continue;
			if (rest.includes('/')) {
				const seg = rest.split('/')[0];
				if (!folders.has(seg)) folders.set(seg, prefix ? `${prefix}/${seg}` : seg);
			} else {
				leaves.push(id);
			}
		}
		const folderFulls = new Set(folders.values());
		const out: TreeNode[] = [];
		for (const [name, full] of [...folders.entries()].sort(([a], [b]) => a.localeCompare(b))) {
			out.push({ name, full, isPage: pageSet.has(full), children: draw(full) });
		}
		for (const full of leaves.sort()) {
			if (folderFulls.has(full)) continue; // page that is also a folder: shown once
			out.push({ name: full.split('/').pop() ?? full, full, isPage: true, children: [] });
		}
		return out;
	};
	return draw('');
}
