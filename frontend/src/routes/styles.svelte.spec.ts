import { describe, expect, it } from 'vitest';
import { page } from 'vitest/browser';
// Importing the app's Tailwind entry through the real pipeline: if the layout
// ever stops importing it again, these assertions fail instead of the UI
// silently shipping unstyled.
import './layout.css';

function probe(html: string): HTMLElement {
	const host = document.createElement('div');
	host.innerHTML = html;
	document.body.appendChild(host);
	return host;
}

describe('app stylesheet', () => {
	it('emits and applies Tailwind utilities', async () => {
		const host = probe('<div id="p1" class="hidden"></div><div id="p2" class="fixed"></div>');
		const hidden = host.querySelector('#p1') as HTMLElement;
		const fixed = host.querySelector('#p2') as HTMLElement;
		expect(getComputedStyle(hidden).display).toBe('none');
		expect(getComputedStyle(fixed).position).toBe('fixed');
		host.remove();
	});

	it('applies responsive (md:) variants only above the breakpoint', async () => {
		const host = probe('<div id="p3" class="static md:fixed"></div>');
		const el = host.querySelector('#p3') as HTMLElement;

		await page.viewport(400, 800);
		expect(getComputedStyle(el).position).toBe('static');

		await page.viewport(1000, 800);
		expect(getComputedStyle(el).position).toBe('fixed');

		await page.viewport(414, 896);
		host.remove();
	});

	it('contains wide markdown inside the note body', async () => {
		const host = probe(
			'<article class="wiki-body"><table><tbody><tr><td>wide</td></tr></tbody></table></article>'
		);
		const table = host.querySelector('table') as HTMLElement;
		const style = getComputedStyle(table);
		expect(style.display).toBe('block');
		expect(style.overflowX).toBe('auto');
		host.remove();
	});
});
