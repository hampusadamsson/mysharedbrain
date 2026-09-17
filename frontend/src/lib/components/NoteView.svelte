<script lang="ts">
	import { api, ApiError, type Note } from '$lib/api/client';
	import { renderMarkdown } from '$lib/markdown';
	import { formatProperty, pageUrl, splitFrontmatter, tagList } from '$lib/notes';
	import { Badge } from '$lib/components/ui/badge';
	import { Button } from '$lib/components/ui/button';
	import * as Tabs from '$lib/components/ui/tabs';
	import NoteHistory from '$lib/components/NoteHistory.svelte';
	import * as AlertDialog from '$lib/components/ui/alert-dialog';
	import * as Dialog from '$lib/components/ui/dialog';
	import { Input } from '$lib/components/ui/input';
	import { Label } from '$lib/components/ui/label';
	import { Textarea } from '$lib/components/ui/textarea';
	import { onMount } from 'svelte';

	interface Props {
		note: Note;
		/** Navigate after a change; `null` means the page was deleted. */
		onchanged: (id: string | null) => Promise<void>;
		onerror: (message: string) => void;
	}

	let { note, onchanged, onerror }: Props = $props();

	// The file log lives behind the Analytics tab; page content is default.
	let tab = $state('page');

	// Local override for an in-place content save (same id); the prop wins
	// whenever navigation loads a different note.
	let override = $state<Note | null>(null);
	const current = $derived(override && override.id === note.id ? override : note);
	let mode = $state<'view' | 'edit'>('view');
	let draft = $state('');
	let draftId = $state('');
	let error = $state('');
	let busy = $state(false);
	let moveOpen = $state(false);
	let moveTo = $state('');
	let backlinks = $state<string[]>([]);
	// Property values come from the API, which owns the YAML parser.
	let meta = $state<Record<string, unknown>>({});
	// Bumped after a save so the file log refetches without losing its filter.
	let historyVersion = $state(0);

	// The body is what markdown renders; the block itself becomes the panel.
	const { body } = $derived(splitFrontmatter(current.content));
	const tags = $derived(tagList(meta.tags));
	const otherProps = $derived(Object.entries(meta).filter(([key]) => key !== 'tags'));

	// A new note id (navigation) always drops back to view mode on Page.
	$effect(() => {
		void note.id;
		override = null;
		mode = 'view';
		error = '';
		tab = 'page';
	});

	async function loadBacklinks(id: string) {
		try {
			backlinks = (await api.backlinks(id)).links;
		} catch {
			backlinks = [];
		}
	}

	async function loadMeta(id: string) {
		try {
			meta = await api.frontmatter(id);
		} catch {
			meta = {};
		}
	}

	onMount(() => {
		void loadBacklinks(note.id);
		void loadMeta(note.id);
	});
	$effect(() => {
		void loadBacklinks(note.id);
		void loadMeta(note.id);
	});

	function startEdit() {
		draft = current.content;
		draftId = current.id;
		error = '';
		mode = 'edit';
		tab = 'page';
	}

	function cancelEdit() {
		draft = current.content;
		draftId = current.id;
		error = '';
		mode = 'view';
	}

	async function save() {
		const target = draftId.trim();
		if (!target) {
			error = 'Page id must not be empty.';
			return;
		}
		busy = true;
		error = '';
		try {
			await api.updateNote(current.id, draft);
			if (target !== current.id) {
				await api.moveNote(current.id, target);
				await onchanged(target);
			} else {
				override = { id: current.id, content: draft };
				mode = 'view';
				// Editing can rewrite the frontmatter; re-read the properties.
				void loadMeta(current.id);
				historyVersion += 1;
			}
		} catch (e) {
			error = e instanceof ApiError ? e.message : String(e);
			onerror(error);
		} finally {
			busy = false;
		}
	}

	async function remove() {
		try {
			await api.deleteNote(current.id);
			await onchanged(null);
		} catch (e) {
			onerror(e instanceof Error ? e.message : String(e));
		}
	}

	async function move() {
		const target = moveTo.trim();
		if (!target || target === current.id) return;
		try {
			await api.moveNote(current.id, target);
			moveOpen = false;
			await onchanged(target);
		} catch (e) {
			onerror(e instanceof Error ? e.message : String(e));
		}
	}
</script>

<div class="text-sm text-muted-foreground">
	<a href="/" class="hover:underline">MySharedBrain</a>
	{#each current.id.split('/') as seg, i (seg + i)}
		<span class="mx-1.5">/</span>
		<a
			href={pageUrl(
				current.id
					.split('/')
					.slice(0, i + 1)
					.join('/')
			)}
			class="hover:underline"
		>
			{seg}
		</a>
	{/each}
</div>

<div class="mt-1 flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
	{#if mode === 'edit'}
		<Input
			bind:value={draftId}
			class="text-2xl font-semibold tracking-tight"
			aria-label="Page id"
			spellcheck="false"
		/>
	{:else}
		<h1 class="text-2xl font-semibold tracking-tight break-words">
			{current.id.split('/').pop()}
		</h1>
	{/if}
	<div class="flex shrink-0 flex-wrap gap-1.5">
		{#if mode === 'edit'}
			<Button onclick={save} disabled={busy}>Save</Button>
			<Button variant="ghost" onclick={cancelEdit}>Cancel</Button>
		{:else}
			<Button variant="outline" onclick={startEdit}>Edit</Button>
			<Button
				variant="outline"
				onclick={() => {
					moveTo = current.id;
					moveOpen = true;
				}}
			>
				Move
			</Button>
			<AlertDialog.Root>
				<AlertDialog.Trigger
					class="inline-flex h-9 items-center rounded-md px-3 text-sm font-medium text-destructive hover:bg-destructive/10"
				>
					Delete
				</AlertDialog.Trigger>
				<AlertDialog.Content>
					<AlertDialog.Header>
						<AlertDialog.Title>Delete page?</AlertDialog.Title>
						<AlertDialog.Description>
							“{current.id}” moves to trash and can be restored from the audit trail.
						</AlertDialog.Description>
					</AlertDialog.Header>
					<AlertDialog.Footer>
						<AlertDialog.Cancel>Cancel</AlertDialog.Cancel>
						<AlertDialog.Action onclick={remove}>Delete</AlertDialog.Action>
					</AlertDialog.Footer>
				</AlertDialog.Content>
			</AlertDialog.Root>
		{/if}
	</div>
</div>

<div class="mt-1 mb-5 flex items-center gap-2 text-sm text-muted-foreground">
	<span
		class="flex size-5.5 items-center justify-center rounded-full bg-blue-600 text-[10px] font-bold text-white"
	>
		Y
	</span>
	Vault page · markdown source
</div>

{#if error}
	<p class="mb-4 rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</p>
{/if}

{#if tags.length > 0 || otherProps.length > 0}
	<dl class="mb-5 flex flex-wrap gap-x-6 gap-y-2 rounded-lg border bg-muted/40 px-3 py-2.5">
		{#if tags.length > 0}
			<div class="flex items-center gap-2">
				<dt class="text-xs font-medium text-muted-foreground">tags</dt>
				<dd class="flex flex-wrap gap-1">
					{#each tags as tag (tag)}
						<a href={`/search?q=${encodeURIComponent(tag)}`} title={`Find notes tagged ${tag}`}>
							<Badge variant="secondary">{tag}</Badge>
						</a>
					{/each}
				</dd>
			</div>
		{/if}
		{#each otherProps as [key, value] (key)}
			<div class="flex items-center gap-2">
				<dt class="text-xs font-medium text-muted-foreground">{key}</dt>
				<dd class="text-sm">{formatProperty(value)}</dd>
			</div>
		{/each}
	</dl>
{/if}

<Tabs.Root value={tab} onValueChange={(v) => (tab = v)} class="mt-5">
	<Tabs.List>
		<Tabs.Trigger value="page">Page</Tabs.Trigger>
		<Tabs.Trigger value="analytics">Analytics</Tabs.Trigger>
	</Tabs.List>
	<Tabs.Content value="page">
		{#if mode === 'edit'}
			<Textarea
				bind:value={draft}
				spellcheck="false"
				aria-label="Page content"
				class="min-h-[26rem] font-mono text-[13.5px] leading-relaxed"
			></Textarea>
		{:else if current.content.trim() === ''}
			<p class="text-sm text-muted-foreground italic">Empty page — hit Edit to write.</p>
		{:else if body.trim() === ''}
			<p class="text-sm text-muted-foreground italic">Only properties — hit Edit to add content.</p>
		{:else}
			<article
				class="wiki-body space-y-3 text-[15px] leading-relaxed [&_a]:text-blue-600 [&_a:hover]:underline [&_blockquote]:border-l-2 [&_blockquote]:pl-3 [&_blockquote]:text-muted-foreground [&_code]:rounded [&_code]:bg-muted [&_code]:px-1.5 [&_code]:py-0.5 [&_h1]:mt-6 [&_h1]:text-2xl [&_h1]:font-semibold [&_h2]:mt-5 [&_h2]:text-xl [&_h2]:font-semibold [&_h3]:mt-4 [&_h3]:text-lg [&_h3]:font-semibold [&_li]:ml-5 [&_li]:list-disc [&_pre]:overflow-auto [&_pre]:rounded-md [&_pre]:border [&_pre]:bg-muted [&_pre]:p-3 [&_table]:my-3 [&_td]:border [&_td]:px-3 [&_td]:py-1.5 [&_th]:border [&_th]:bg-muted [&_th]:px-3 [&_th]:py-1.5"
			>
				{@html renderMarkdown(body)}
			</article>
		{/if}

		{#if backlinks.length > 0}
			<div class="mt-8 border-t pt-4">
				<h2 class="text-xs font-bold tracking-wider text-muted-foreground">BACKLINKS</h2>
				<ul class="mt-2 space-y-1">
					{#each backlinks as link (link)}
						<li>
							<a href={pageUrl(link)} class="text-sm text-blue-600 hover:underline">{link}</a>
						</li>
					{/each}
				</ul>
			</div>
		{/if}
	</Tabs.Content>
	<Tabs.Content value="analytics">
		{#if tab === 'analytics'}
			{#key current.id}
				<NoteHistory noteId={current.id} version={historyVersion} />
			{/key}
		{/if}
	</Tabs.Content>
</Tabs.Root>

<Dialog.Root bind:open={moveOpen}>
	<Dialog.Content>
		<Dialog.Header>
			<Dialog.Title>Move page</Dialog.Title>
			<Dialog.Description>New id — folders are created from the path.</Dialog.Description>
		</Dialog.Header>
		<Label for="move-to" class="sr-only">New page id</Label>
		<Input id="move-to" bind:value={moveTo} onkeydown={(e) => e.key === 'Enter' && move()} />
		<Dialog.Footer>
			<Button variant="ghost" onclick={() => (moveOpen = false)}>Cancel</Button>
			<Button onclick={move}>Move</Button>
		</Dialog.Footer>
	</Dialog.Content>
</Dialog.Root>
