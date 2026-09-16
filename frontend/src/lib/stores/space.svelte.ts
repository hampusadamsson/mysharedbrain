// Shared UI state (Svelte 5 runes module).
import { api } from '$lib/api/client';

interface SpaceState {
	pending: number;
	notes: string[];
}

export const space = $state<SpaceState>({ pending: 0, notes: [] });

export async function refreshPending() {
	try {
		// Only the count is needed; ask for one row and read the total.
		space.pending = (await api.listCapture('pending', 1, 0)).total ?? 0;
	} catch {
		/* backend unreachable — badge stays stale */
	}
}

export async function refreshNotes() {
	try {
		space.notes = (await api.listNotes()).notes;
	} catch {
		/* backend unreachable */
	}
}
