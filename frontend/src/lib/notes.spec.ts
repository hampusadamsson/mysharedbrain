import { describe, expect, it } from 'vitest';
import { buildTree, pageUrl, timeAgo } from './notes';

describe('pageUrl', () => {
	it('encodes each path segment', () => {
		expect(pageUrl('todo')).toBe('/p/todo');
		expect(pageUrl('projects/my note')).toBe('/p/projects/my%20note');
	});
});

describe('timeAgo', () => {
	it('formats relative times', () => {
		const now = Date.now();
		expect(timeAgo(new Date(now - 10_000).toISOString())).toBe('just now');
		expect(timeAgo(new Date(now - 5 * 60_000).toISOString())).toBe('5m ago');
		expect(timeAgo(new Date(now - 3 * 3_600_000).toISOString())).toBe('3h ago');
		expect(timeAgo(new Date(now - 2 * 86_400_000).toISOString())).toBe('2d ago');
	});
});

describe('buildTree', () => {
	it('nests folders, sorts, and dedupes page-folders', () => {
		const tree = buildTree(['todo', 'projects/homelab', 'projects/golf', 'a', 'a/b']);
		expect(tree.map((n) => n.full)).toEqual(['a', 'projects', 'todo']);
		const projects = tree[1];
		expect(projects.isPage).toBe(false);
		expect(projects.children.map((n) => n.name)).toEqual(['golf', 'homelab']);
		const a = tree[0];
		expect(a.isPage).toBe(true);
		expect(a.children.map((n) => n.full)).toEqual(['a/b']);
	});
});
