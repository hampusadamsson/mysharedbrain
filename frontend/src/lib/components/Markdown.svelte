<script lang="ts">
	import { renderMarkdown } from '$lib/markdown';

	interface Props {
		/** Markdown source. Rendered through DOMPurify before it hits the DOM. */
		content: string;
		class?: string;
		/** Keep single newlines as line breaks (feedback text, not note bodies). */
		breaks?: boolean;
	}

	let { content, class: className = '', breaks = false }: Props = $props();
	// Typography lives in layout.css under `.wiki-body` (one place for every
	// markdown surface: notes, ask answers, capture feedback).
	const html = $derived(renderMarkdown(content, breaks));
</script>

<article class="wiki-body {className}">
	{@html html}
</article>
