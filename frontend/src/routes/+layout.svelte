<script lang="ts">
	import Sidebar from '$lib/components/Sidebar.svelte';
	import TopBar from '$lib/components/TopBar.svelte';
	import { Toaster } from '$lib/components/ui/sonner';
	import { refreshNotes, refreshPending } from '$lib/stores/space.svelte';
	import { onMount } from 'svelte';

	let { children } = $props();
	let drawer = $state(false);

	onMount(() => {
		refreshNotes();
		refreshPending();
	});
</script>

<TopBar onmenu={() => (drawer = !drawer)} />

<div class="flex min-h-[calc(100vh-3.5rem)]">
	{#if drawer}
		<button
			aria-label="Close menu"
			class="fixed inset-x-0 top-14 bottom-0 z-40 bg-black/30 md:hidden"
			onclick={() => (drawer = false)}
		></button>
	{/if}
	<aside
		class="fixed top-14 bottom-0 left-0 z-50 flex w-[min(300px,85vw)] flex-col border-r bg-muted/40 transition-transform md:static md:z-auto md:w-70 md:translate-x-0 {drawer
			? 'translate-x-0 shadow-xl'
			: '-translate-x-full'}"
	>
		<Sidebar />
	</aside>
	<main class="mx-auto w-full max-w-4xl flex-1 px-4 py-6 md:px-10">
		{@render children()}
	</main>
</div>

<Toaster />
