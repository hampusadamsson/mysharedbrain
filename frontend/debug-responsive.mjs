// Debug: sidebar transform, 404s, table overflow (deleted after use).
import { chromium } from 'playwright';

const BASE = 'https://mysharedbrain.haadpi.duckdns.org:9443';
const browser = await chromium.launch();
const context = await browser.newContext({ ignoreHTTPSErrors: true });
const page = await context.newPage();
const failures = [];
page.on('response', (r) => r.status() >= 400 && failures.push(`${r.status()} ${r.url()}`));

await page.setViewportSize({ width: 390, height: 844 });
await page.goto(BASE + '/', { waitUntil: 'networkidle' });
await page.waitForTimeout(500);

const aside = await page.locator('aside').evaluate((el) => {
	const cs = getComputedStyle(el);
	const r = el.getBoundingClientRect();
	return {
		classes: el.className,
		transform: cs.transform,
		position: cs.position,
		width: cs.width,
		left: Math.round(r.x),
		right: Math.round(r.right),
		viewport: window.innerWidth
	};
});
console.log('ASIDE:', JSON.stringify(aside, null, 2));

const scrimExists = await page.locator('button[aria-label="Close menu"]').count();
console.log('scrim present when closed:', scrimExists);

await page.getByRole('button', { name: 'Menu' }).click();
await page.waitForTimeout(500);
console.log(
	'scrim present when open:',
	await page.locator('button[aria-label="Close menu"]').count()
);
const openAside = await page
	.locator('aside')
	.evaluate((el) => Math.round(el.getBoundingClientRect().x));
console.log('aside x when open:', openAside);

// table overflow detail
await page.goto(BASE + '/p/e2e/responsive', { waitUntil: 'networkidle' });
await page.waitForTimeout(400);
const tableInfo = await page.evaluate(() => {
	const t = document.querySelector('article table');
	if (!t) return null;
	const cs = getComputedStyle(t);
	const host = t.parentElement;
	return {
		tableWidth: Math.round(t.getBoundingClientRect().width),
		display: cs.display,
		overflowX: cs.overflowX,
		hostTag: host?.tagName,
		hostOverflow: host ? getComputedStyle(host).overflowX : null,
		docScroll: document.documentElement.scrollWidth,
		clientWidth: document.documentElement.clientWidth
	};
});
console.log('TABLE:', JSON.stringify(tableInfo, null, 2));
console.log('FAILED REQUESTS:', failures.length ? failures : 'none');

await browser.close();
