// Responsive audit: loads every route at phone/tablet/desktop viewports and
// reports page-level horizontal overflow (ignoring content contained by its own
// scroll box) plus mobile drawer/dialog behaviour.
//
//   pnpm audit:responsive                          # live cluster
//   BASE=http://localhost:5173 pnpm audit:responsive
//
// Exits non-zero when something overflows.
import { chromium } from 'playwright';

const BASE = process.env.BASE ?? 'https://mysharedbrain.haadpi.duckdns.org:9443';
const VIEWPORTS = [
	{ name: 'mobile-360', width: 360, height: 740 },
	{ name: 'mobile-390', width: 390, height: 844 },
	{ name: 'landscape-844', width: 844, height: 390 },
	{ name: 'tablet-768', width: 768, height: 1024 },
	{ name: 'desktop-1280', width: 1280, height: 800 },
	{ name: 'desktop-1440', width: 1440, height: 900 }
];
const STATIC_ROUTES = ['/', '/ask', '/capture', '/activity', '/settings', '/search?q=test'];

/** Page route that exists in whatever vault we audit (plus its folder). */
async function vaultRoutes() {
	try {
		const res = await fetch(`${BASE}/api/notes`);
		const { notes } = await res.json();
		const routes = [];
		if (notes?.length) routes.push(`/p/${notes[0]}`);
		const nested = notes?.find((n) => n.includes('/'));
		if (nested) routes.push(`/p/${nested.split('/')[0]}`);
		return routes;
	} catch {
		return [];
	}
}

const ROUTES = [...STATIC_ROUTES, ...(await vaultRoutes())];

const issues = [];
const browser = await chromium.launch();
const context = await browser.newContext({ ignoreHTTPSErrors: true });
const page = await context.newPage();
const consoleErrors = [];
page.on('console', (m) => m.type() === 'error' && consoleErrors.push(m.text()));
page.on('pageerror', (e) => consoleErrors.push(String(e)));

async function overflow() {
	return page.evaluate(() => {
		const doc = document.documentElement;
		const overflowX = doc.scrollWidth - doc.clientWidth;
		const culprits = [];
		if (overflowX > 1) {
			// Only report elements that are NOT inside a scroll container: those
			// are the ones actually widening the page (children of an
			// overflow:auto box are contained by design).
			for (const el of document.querySelectorAll('body *')) {
				const r = el.getBoundingClientRect();
				if (r.width === 0 || r.right <= doc.clientWidth + 1) continue;
				let clipped = false;
				for (let p = el.parentElement; p && p !== doc; p = p.parentElement) {
					const ox = getComputedStyle(p).overflowX;
					if (ox === 'auto' || ox === 'scroll' || ox === 'hidden') {
						clipped = true;
						break;
					}
				}
				if (!clipped) {
					culprits.push(
						`${el.tagName.toLowerCase()}.${String(el.className).split(' ')[0]} w=${Math.round(r.width)} right=${Math.round(r.right)}`
					);
				}
			}
		}
		return { overflowX, culprits: [...new Set(culprits)].slice(0, 4) };
	});
}

for (const vp of VIEWPORTS) {
	await page.setViewportSize({ width: vp.width, height: vp.height });
	for (const route of ROUTES) {
		await page.goto(BASE + route, { waitUntil: 'networkidle' });
		await page.waitForTimeout(350);
		const { overflowX, culprits } = await overflow();
		if (overflowX > 1) {
			issues.push(
				`${vp.name} ${route}: horizontal overflow ${overflowX}px — ${culprits.join(', ')}`
			);
		}
	}
}

// Mobile-specific behaviours
for (const vp of [VIEWPORTS[0], VIEWPORTS[1]]) {
	await page.setViewportSize({ width: vp.width, height: vp.height });
	await page.goto(BASE + '/', { waitUntil: 'networkidle' });

	const asideBox = await page.locator('aside').boundingBox();
	if (asideBox && asideBox.x + asideBox.width > 2) {
		issues.push(
			`${vp.name}: sidebar is on-canvas before opening the drawer (x=${Math.round(asideBox.x)})`
		);
	}

	if (!(await page.getByRole('button', { name: 'Menu' }).isVisible())) {
		issues.push(`${vp.name}: menu button not visible`);
	} else {
		await page.getByRole('button', { name: 'Menu' }).click();
		await page.waitForTimeout(300);
		const openBox = await page.locator('aside').boundingBox();
		if (!openBox || openBox.x < -1) issues.push(`${vp.name}: drawer did not slide in`);
		// scrim closes
		await page.mouse.click(vp.width - 20, vp.height - 20);
		await page.waitForTimeout(350);
		const closedBox = await page.locator('aside').boundingBox();
		if (closedBox && closedBox.x + closedBox.width > 2) {
			issues.push(`${vp.name}: drawer did not close on scrim tap (x=${Math.round(closedBox.x)})`);
		}
	}

	// create dialog fits the viewport
	await page.getByLabel('Create page').click(); // top-bar button (empty-page CTA has visible text)
	await page.waitForTimeout(300);
	const dlg = await page.locator('[role="dialog"]').first().boundingBox();
	if (!dlg) issues.push(`${vp.name}: create dialog did not open`);
	else if (dlg.x < 0 || dlg.x + dlg.width > vp.width + 1 || dlg.y + dlg.height > vp.height + 1) {
		issues.push(
			`${vp.name}: create dialog overflows viewport (x=${Math.round(dlg.x)} w=${Math.round(dlg.width)} y=${Math.round(dlg.y)} h=${Math.round(dlg.height)})`
		);
	}
	await page.keyboard.press('Escape');

	// capture apply dialog: does it fit / scroll?
	await page.goto(BASE + '/capture', { waitUntil: 'networkidle' });
	const applyBtn = page.getByRole('button', { name: 'Apply' }).first();
	if (await applyBtn.count()) {
		await applyBtn.click();
		await page.waitForTimeout(400);
		const box = await page.locator('[role="dialog"]').first().boundingBox();
		if (box && (box.y + box.height > vp.height + 1 || box.x < 0)) {
			issues.push(
				`${vp.name}: apply dialog overflows (y=${Math.round(box.y)} h=${Math.round(box.height)} vh=${vp.height})`
			);
		}
		const canScroll = await page
			.locator('[role="dialog"]')
			.first()
			.evaluate((el) => el.scrollHeight > el.clientHeight + 2);
		const dialogFits = box ? box.y + box.height <= vp.height + 1 : false;
		if (canScroll && !dialogFits) {
			const scrollable = await page
				.locator('[role="dialog"]')
				.first()
				.evaluate((el) => getComputedStyle(el).overflowY !== 'visible');
			if (!scrollable) issues.push(`${vp.name}: apply dialog too tall and not scrollable`);
		}
		await page.keyboard.press('Escape');
	}
}

await browser.close();
console.log(
	issues.length
		? 'ISSUES:\n' + issues.map((i) => '  - ' + i).join('\n')
		: 'no responsive issues found'
);
console.log(
	'\nconsole errors: ' + (consoleErrors.length ? consoleErrors.slice(0, 5).join(' | ') : 'none')
);
