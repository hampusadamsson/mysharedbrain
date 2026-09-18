<script lang="ts">
	import * as AlertDialog from '$lib/components/ui/alert-dialog';
	import { buttonVariants, type ButtonSize } from '$lib/components/ui/button';
	import { cn } from '$lib/utils';

	interface Props {
		/** What is being removed, named specifically enough to tell rows apart
		 * (a job's name, a server's name, a mapping's key…). */
		label: string;
		/** Shown under the title; defaults to a generic "cannot be undone". */
		description?: string;
		/** Trigger button text; defaults to "Remove". */
		triggerText?: string;
		triggerSize?: ButtonSize;
		onconfirm: () => void;
	}

	let {
		label,
		description = '',
		triggerText = 'Remove',
		triggerSize = 'sm',
		onconfirm
	}: Props = $props();
</script>

<AlertDialog.Root>
	<AlertDialog.Trigger
		class={cn(buttonVariants({ variant: 'ghost', size: triggerSize }), 'text-destructive')}
	>
		{triggerText}
	</AlertDialog.Trigger>
	<AlertDialog.Content>
		<AlertDialog.Header>
			<AlertDialog.Title>Remove {label}?</AlertDialog.Title>
			<AlertDialog.Description>
				{description || 'This cannot be undone.'}
			</AlertDialog.Description>
		</AlertDialog.Header>
		<AlertDialog.Footer>
			<AlertDialog.Cancel>Cancel</AlertDialog.Cancel>
			<AlertDialog.Action onclick={onconfirm}>Remove</AlertDialog.Action>
		</AlertDialog.Footer>
	</AlertDialog.Content>
</AlertDialog.Root>
