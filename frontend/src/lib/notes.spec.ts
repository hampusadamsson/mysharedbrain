import { describe, expect, it } from 'vitest';
import {
	buildTree,
	compactTree,
	formatProperty,
	isLibrarian,
	pageUrl,
	splitFrontmatter,
	tagList,
	timeAgo
} from './notes';

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

describe('splitFrontmatter', () => {
	it('splits the block off the body', () => {
		const { raw, body } = splitFrontmatter('---\ntags: [a, b]\n---\n# Title\ntext\n');
		expect(raw).toBe('tags: [a, b]');
		expect(body).toBe('# Title\ntext\n');
	});

	it('leaves a note without frontmatter untouched', () => {
		const content = '# Just a note\n\nbody\n';
		expect(splitFrontmatter(content)).toEqual({ raw: null, body: content });
	});

	it('ignores an unterminated block', () => {
		const content = '---\ntags: [a]\n\nno closing fence\n';
		expect(splitFrontmatter(content).raw).toBeNull();
		expect(splitFrontmatter(content).body).toBe(content);
	});

	it('keeps a body-only horizontal rule', () => {
		const { body } = splitFrontmatter('text\n\n---\n\nmore\n');
		expect(body).toBe('text\n\n---\n\nmore\n');
	});
});

describe('tagList', () => {
	it('accepts lists, comma strings and # prefixes', () => {
		expect(tagList(['type/daily', 'status/raw'])).toEqual(['type/daily', 'status/raw']);
		expect(tagList('type/daily, #status/raw')).toEqual(['type/daily', 'status/raw']);
		expect(tagList(undefined)).toEqual([]);
	});
});

describe('formatProperty', () => {
	it('renders scalars, lists and objects', () => {
		expect(formatProperty('raw')).toBe('raw');
		expect(formatProperty(3)).toBe('3');
		expect(formatProperty(true)).toBe('true');
		expect(formatProperty(['a', 'b'])).toBe('a, b');
		expect(formatProperty({ src: 'x' })).toBe('{"src":"x"}');
		expect(formatProperty(null)).toBe('');
	});
});

describe('isLibrarian', () => {
	it('recognises the librarian actor, not humans or clients', () => {
		expect(isLibrarian('librarian')).toBe(true);
		expect(isLibrarian('librarian:vault-sweep')).toBe(true);
		expect(isLibrarian('api')).toBe(false);
		expect(isLibrarian('mcp')).toBe(false);
		expect(isLibrarian('curator')).toBe(false);
	});
});

describe('buildTree', () => {
	it('composes single-child folder chains, keeps pages reachable', () => {
		const tree = compactTree(buildTree(['a/b/c/note', 'todo']));
		expect(tree.map((n) => n.full)).toEqual(['a/b/c', 'todo']);
		const chain = tree[0];
		expect(chain.name).toBe('a/b/c');
		expect(chain.isPage).toBe(false);
		expect(chain.children.map((n) => n.full)).toEqual(['a/b/c/note']);
	});

	it('stops composing at pages and at branches', () => {
		// `a` is itself a page: its row (and link) must survive.
		const withPage = compactTree(buildTree(['a', 'a/b/note']));
		expect(withPage.map((n) => n.name)).toEqual(['a']);
		expect(withPage[0].isPage).toBe(true);
		expect(withPage[0].children.map((n) => n.full)).toEqual(['a/b']);
		expect(withPage[0].children[0].children.map((n) => n.full)).toEqual(['a/b/note']);
		// two children: no composing.
		const branched = compactTree(buildTree(['a/b/one', 'a/c/two']));
		expect(branched.map((n) => n.name)).toEqual(['a']);
		expect(branched[0].children.map((n) => n.name)).toEqual(['b', 'c']);
	});

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
