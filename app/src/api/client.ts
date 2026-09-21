import type { components } from './schema';

// EXPO_PUBLIC_* variables are inlined at build time. Never put secrets in them.
const BASE_URL = process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:8000';

export type CommitmentItem = components['schemas']['CommitmentItem'];
export type AssertionDetail = components['schemas']['AssertionDetail'];
export type Correction = components['schemas']['Correction'];
export type Health = components['schemas']['Health'];
export type CommitmentStatus = 'open' | 'done' | 'cancelled';

async function request<T>(method: 'GET' | 'POST', path: string, body?: unknown): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    method,
    headers: { Accept: 'application/json', ...(body ? { 'Content-Type': 'application/json' } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) {
    const detail = await response.json().then((json) => json?.detail, () => undefined);
    throw new Error(typeof detail === 'string' ? detail : `${method} ${path} failed with ${response.status}`);
  }
  return (await response.json()) as T;
}

export const getHealth = () => request<Health>('GET', '/health');
export const getCommitments = () => request<CommitmentItem[]>('GET', '/commitments');
export const getAssertion = (id: string) => request<AssertionDetail>('GET', `/assertions/${id}`);
export const confirmAssertion = (id: string) => request<AssertionDetail>('POST', `/assertions/${id}/confirm`);
export const dismissAssertion = (id: string) => request<AssertionDetail>('POST', `/assertions/${id}/dismiss`);
export const correctAssertion = (id: string, correction: Correction) =>
  request<AssertionDetail>('POST', `/assertions/${id}/correct`, correction);
export const setCommitmentStatus = (id: string, status: CommitmentStatus) =>
  request<AssertionDetail>('POST', `/assertions/${id}/status`, { status });
