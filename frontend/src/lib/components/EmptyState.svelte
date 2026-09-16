<script lang="ts">
	import CreateDialog from '$lib/components/CreateDialog.svelte';

	let createOpen = $state(false);
</script>

<div class="py-16 text-center text-muted-foreground">
	<div class="text-5xl">📄</div>
	<h2 class="mt-4 text-xl font-semibold text-foreground">Select a page, or create one</h2>
	<p class="mx-auto mt-2 max-w-md text-sm">
		Pages live as markdown files — flat or in folders. Ask the librarian when you can't find
		something.
	</p>
	<button
		class="mt-6 inline-flex items-center rounded-md bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700"
		onclick={() => (createOpen = true)}
	>
		Create page
	</button>
</div>

<CreateDialog bind:open={createOpen} />
