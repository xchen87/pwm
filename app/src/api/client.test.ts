import { confirmAssertion, getHealth } from './client';

describe('api client', () => {
  afterEach(() => jest.restoreAllMocks());

  it('returns the parsed response', async () => {
    globalThis.fetch = jest.fn().mockResolvedValue({ ok: true, json: async () => ({ status: 'ok' }) });
    await expect(getHealth()).resolves.toEqual({ status: 'ok' });
    expect(globalThis.fetch).toHaveBeenCalledWith('http://localhost:8000/health', expect.anything());
  });

  it('posts review actions', async () => {
    globalThis.fetch = jest.fn().mockResolvedValue({ ok: true, json: async () => ({ review: 'confirmed' }) });
    await confirmAssertion('abc');
    expect(globalThis.fetch).toHaveBeenCalledWith(
      'http://localhost:8000/assertions/abc/confirm',
      expect.objectContaining({ method: 'POST' }),
    );
  });

  it('surfaces the reason the server gave', async () => {
    globalThis.fetch = jest
      .fn()
      .mockResolvedValue({ ok: false, status: 409, json: async () => ({ detail: 'confirm the commitment first' }) });
    await expect(confirmAssertion('abc')).rejects.toThrow('confirm the commitment first');
  });
});
