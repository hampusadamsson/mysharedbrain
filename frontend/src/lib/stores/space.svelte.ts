// Shared UI state (Svelte 5 runes module).
import { api } from '$lib/api/client';

interface SpaceState {
	pending: number;
	notes: string[];
}

export const space = $state<SpaceState>({ pending: 0, notes: [] });

export async function refreshPending() {
	try {
		space.pending = (await api.listCapture('pending')).entries.length;
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
