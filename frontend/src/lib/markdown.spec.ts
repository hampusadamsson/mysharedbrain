// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import { preprocessWikiLinks, renderMarkdown } from './markdown';

describe('preprocessWikiLinks', () => {
	it('turns wiki links into data-target anchors', () => {
		expect(preprocessWikiLinks('see [[homelab]]')).toContain('data-target="homelab"');
		const aliased = preprocessWikiLinks('see [[projects/a|A page]]');
		expect(aliased).toContain('data-target="projects/a"');
		expect(aliased).toContain('>A page</a>');
	});
});

describe('renderMarkdown', () => {
	it('renders headings, lists, tables and code', () => {
		const html = renderMarkdown(
			'# Title\n\n- a\n- b\n\n| x | y |\n|---|---|\n| 1 | 2 |\n\n```py\nprint(1)\n```\n\n> quote'
		);
		expect(html).toContain('<h1');
		expect(html).toContain('<li>a</li>');
		expect(html).toContain('<table>');
		expect(html).toContain('<code');
		expect(html).toContain('<blockquote>');
	});

	it('keeps valid external links with rel=noopener', () => {
		const html = renderMarkdown('[docs](https://svelte.dev/docs)');
		expect(html).toContain('href="https://svelte.dev/docs"');
		expect(html).toContain('rel="noopener');
	});

	it('strips javascript: urls and raw script/img handlers', () => {
		const html = renderMarkdown(
			'[x](javascript:alert(1))\n\n<script>alert(2)</script>\n\n<img src=x onerror="alert(3)">'
		);
		expect(html).not.toContain('javascript:');
		expect(html).not.toContain('<script');
		expect(html).not.toContain('onerror');
	});

	it('renders wiki links as linkable spans for the router', () => {
		expect(renderMarkdown('go [[projects/homelab]]')).toContain('data-target="projects/homelab"');
	});
});
