import { getHealth } from './client';

describe('api client', () => {
  afterEach(() => jest.restoreAllMocks());

  it('returns the parsed health response', async () => {
    globalThis.fetch = jest.fn().mockResolvedValue({ ok: true, json: async () => ({ status: 'ok' }) });
    await expect(getHealth()).resolves.toEqual({ status: 'ok' });
    expect(globalThis.fetch).toHaveBeenCalledWith('http://localhost:8000/health', expect.anything());
  });

  it('throws on a non-2xx response', async () => {
    globalThis.fetch = jest.fn().mockResolvedValue({ ok: false, status: 503 });
    await expect(getHealth()).rejects.toThrow('503');
  });
});
