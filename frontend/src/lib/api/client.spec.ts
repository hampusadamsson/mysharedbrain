import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, api } from './client';

function jsonResponse(body: unknown, status = 200) {
	return {
		ok: status >= 200 && status < 300,
		status,
		statusText: 'Error',
		json: async () => body
	} as Response;
}

describe('api client', () => {
	beforeEach(() => {
		vi.stubGlobal('fetch', vi.fn());
	});

	it('builds list/search URLs with pagination params', async () => {
		const fetchMock = vi.mocked(fetch);
		fetchMock.mockResolvedValueOnce(jsonResponse({ notes: ['a'] }));
		await api.listNotes('projects', 50, 10);
		expect(fetchMock).toHaveBeenCalledWith(
			'/api/notes?prefix=projects&offset=10&limit=50',
			expect.objectContaining({})
		);

		fetchMock.mockResolvedValueOnce(jsonResponse({ names: [], content: [] }));
		await api.search('q', 5, 2);
		expect(fetchMock.mock.calls[1][0]).toBe('/api/search?q=q&limit=5&offset=2');
	});

	it('encodes note ids in paths', async () => {
		const fetchMock = vi.mocked(fetch);
		fetchMock.mockResolvedValueOnce(jsonResponse({ id: 'a/b', content: '' }));
		await api.readNote('a/b');
		expect(fetchMock.mock.calls[0][0]).toBe('/api/notes/a%2Fb');
	});

	it('throws ApiError with the backend detail', async () => {
		vi.mocked(fetch).mockResolvedValueOnce(jsonResponse({ detail: 'note not found' }, 404));
		const err = await api.readNote('gone').catch((e) => e);
		expect(err).toBeInstanceOf(ApiError);
		expect((err as ApiError).status).toBe(404);
		expect((err as Error).message).toBe('note not found');
	});

	it('resolves 204 as null', async () => {
		vi.mocked(fetch).mockResolvedValueOnce({
			ok: true,
			status: 204,
			json: async () => null
		} as Response);
		await expect(api.deleteNote('x')).resolves.toBeNull();
	});
});
