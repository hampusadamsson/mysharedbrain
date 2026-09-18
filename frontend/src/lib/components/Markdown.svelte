<script lang="ts">
	import { renderMarkdown } from '$lib/markdown';

	interface Props {
		/** Markdown source. Rendered through DOMPurify before it hits the DOM. */
		content: string;
		class?: string;
	}

	let { content, class: className = '' }: Props = $props();
	// Typography lives in layout.css under `.wiki-body` (one place for every
	// markdown surface: notes and the ask answer).
	const html = $derived(renderMarkdown(content));
</script>

<article class="wiki-body {className}">
	{@html html}
</article>
