// Markdown → sanitized HTML. Replaces the hand-written renderer.
// Security: DOMPurify sanitizes everything; wiki links carry data-target.
import DOMPurify from 'dompurify';
import { marked } from 'marked';

const WIKI_RE = /\[\[([^\]|]+)(?:\|([^\]]*))?\]\]/g;

/** `[[target]]` / `[[target|alias]]` → anchor with a data-target attribute. */
export function preprocessWikiLinks(src: string): string {
	return src.replace(WIKI_RE, (_m, target: string, alias?: string) => {
		const label = (alias ?? target).trim();
		const clean = target.trim().replace(/"/g, '&quot;');
		return `<a class="wiki-link" data-target="${clean}">${label}</a>`;
	});
}

// External links open in a new tab with a safe rel (set once, at module load).
let hooked = false;
function installHook() {
	if (hooked) return;
	hooked = true;
	DOMPurify.addHook('afterSanitizeAttributes', (node) => {
		if (node.tagName === 'A' && /^https?:/i.test(node.getAttribute('href') ?? '')) {
			node.setAttribute('target', '_blank');
			node.setAttribute('rel', 'noopener noreferrer');
		}
	});
}

/** Render markdown to sanitized HTML (safe to inject with {@html}).
 *
 * ``breaks`` turns single newlines into line breaks — right for feedback text
 * that is written as lines, wrong for note bodies where a newline is just a
 * soft wrap.
 */
export function renderMarkdown(src: string, breaks = false): string {
	installHook();
	const html = marked.parse(preprocessWikiLinks(src), {
		async: false,
		gfm: true,
		breaks
	}) as string;
	return DOMPurify.sanitize(html, {
		ADD_ATTR: ['data-target'],
		USE_PROFILES: { html: true }
	});
}
