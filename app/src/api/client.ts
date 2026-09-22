import { clearToken, getToken } from '../session';
import type { components } from './schema';

// EXPO_PUBLIC_* variables are inlined at build time. Never put secrets in them.
export const API_URL = process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:8000';

export type CommitmentItem = components['schemas']['CommitmentItem'];
export type AssertionDetail = components['schemas']['AssertionDetail'];
export type Correction = components['schemas']['Correction'];
export type Home = components['schemas']['Home'];
export type BriefView = components['schemas']['BriefView'];
export type WrittenItem = components['schemas']['WrittenItem'];
export type NotificationView = components['schemas']['NotificationView'];
export type AnswerView = components['schemas']['AnswerView'];
export type ConnectionsView = components['schemas']['ConnectionsView'];
export type SyncResult = components['schemas']['SyncResult'];
export type PersonView = components['schemas']['PersonView'];
export type AuthConfig = components['schemas']['AuthConfig'];
export type ExportTicket = components['schemas']['ExportTicket'];
export type SessionOut = components['schemas']['SessionOut'];
export type Me = components['schemas']['Me'];
export type Health = components['schemas']['Health'];
export type CommitmentStatus = 'open' | 'done' | 'cancelled';

/** An error from the API, with its status so callers can tell "signed out" from "broken". */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

async function request<T>(method: 'GET' | 'POST' | 'DELETE', path: string, body?: unknown): Promise<T> {
  const token = await getToken();
  const response = await fetch(`${API_URL}${path}`, {
    method,
    headers: {
      Accept: 'application/json',
      ...(body ? { 'Content-Type': 'application/json' } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (response.status === 401 && token) await clearToken(); // the session ended; start over signed out
  if (!response.ok) {
    const detail = await response.json().then((json) => json?.detail, () => undefined);
    throw new ApiError(
      typeof detail === 'string' ? detail : `${method} ${path} failed with ${response.status}`,
      response.status,
    );
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

export const getHome = () => request<Home>('GET', '/home');
export const recordVisit = () => request<unknown>('POST', '/visits');
export const getLatestBrief = () => request<BriefView>('GET', '/briefs/latest');
export const getBrief = (id: string) => request<BriefView>('GET', `/briefs/${id}`);
export const generateBrief = () => request<BriefView>('POST', '/briefs?period=weekly');
export const getNotifications = () => request<NotificationView[]>('GET', '/notifications');
export const markNotificationsRead = () => request<unknown>('POST', '/notifications/read');

export const askWorld = (question: string) => request<AnswerView>('POST', '/ask', { question });
export const rememberThis = (text: string) => request<CommitmentItem>('POST', '/memories', { text });
export const forgetMemory = (id: string) => request<unknown>('DELETE', `/memories/${id}`);

export const getConnections = () => request<ConnectionsView>('GET', '/connections');
export const connectDemo = () => request<SyncResult>('POST', '/connections/demo');
export const disconnect = (connector: string) => request<unknown>('DELETE', `/connections/${connector}`);
export const deleteEverything = () => request<unknown>('DELETE', '/me');

export const getPeople = () => request<PersonView[]>('GET', '/people');
export const confirmSamePerson = (identifierId: string) =>
  request<unknown>('POST', `/people/identifiers/${identifierId}/confirm`);
export const markDifferentPerson = (identifierId: string, name: string) =>
  request<unknown>('POST', `/people/identifiers/${identifierId}/split`, { name });

export const exchangeLoginCode = (code: string, verifier: string, termsVersion: string) =>
  request<SessionOut>('POST', '/auth/session', {
    code,
    verifier,
    terms_version: termsVersion,
    age_confirmed: true, // sign-in cannot start without the attestation (src/signIn.ts)
  });
export const requestExport = () => request<ExportTicket>('POST', '/me/export');
export const getAuthConfig = () => request<AuthConfig>('GET', '/auth/config');
export const getMe = () => request<Me>('GET', '/auth/me');
export const signOut = () => request<unknown>('POST', '/auth/logout');

export const registerDevice = (push_token: string, platform: 'ios' | 'android') =>
  request<unknown>('POST', '/devices', { push_token, platform });
export const unregisterDevice = (push_token: string, platform: 'ios' | 'android') =>
  request<unknown>('DELETE', '/devices', { push_token, platform });

export type EventName =
  | 'brief_opened'
  | 'item_useful'
  | 'item_not_useful'
  | 'item_dismissed'
  | 'item_corrected'
  | 'item_acted'
  | 'notification_opened'
  | 'source_inspected'
  | 'question_asked';

/** Usage measurement. Never blocks or breaks the screen it is called from. */
export const recordEvent = (name: EventName, subjectId?: string) =>
  request<unknown>('POST', '/events', { name, subject_id: subjectId ?? null }).catch(() => undefined);
