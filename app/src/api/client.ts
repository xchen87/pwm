import type { paths } from './schema';

// EXPO_PUBLIC_* variables are inlined at build time. Never put secrets in them.
const BASE_URL = process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:8000';

type JsonOf<P extends keyof paths> = paths[P] extends {
  get: { responses: { 200: { content: { 'application/json': infer Body } } } };
}
  ? Body
  : never;

async function get<P extends keyof paths>(path: P): Promise<JsonOf<P>> {
  const response = await fetch(`${BASE_URL}${path}`, { headers: { Accept: 'application/json' } });
  if (!response.ok) {
    throw new Error(`GET ${path} failed with ${response.status}`);
  }
  return (await response.json()) as JsonOf<P>;
}

export function getHealth() {
  return get('/health');
}
