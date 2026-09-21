import type { CommitmentItem } from './api/client';

type Worded = Pick<
  CommitmentItem,
  'kind' | 'review' | 'origin' | 'commitment_type' | 'direction' | 'committed_by' | 'committed_to' | 'due' | 'overdue'
>;

/**
 * Only what the user confirmed may be presented as fact. Even something read out of the
 * user's own note is an interpretation until they confirm it.
 */
export function isFact(item: Pick<CommitmentItem, 'review'>): boolean {
  return item.review === 'confirmed';
}

const NOUN: Record<string, string> = {
  commitment: 'commitment',
  event: 'date',
  thing: 'detail',
  person: 'contact detail',
  decision: 'decision',
};

export function heading(item: Worded): string {
  if (item.kind === 'memory') return 'You told me';
  const noun = item.commitment_type === 'deadline' ? 'deadline' : (NOUN[item.kind] ?? 'detail');
  return isFact(item) ? noun[0].toUpperCase() + noun.slice(1) : `Possible ${noun}`;
}

export function parties(item: Worded): string {
  if (item.kind !== 'commitment') return '';
  if (item.commitment_type === 'deadline') return 'For you';
  if (item.direction === 'by_user') return item.committed_to ? `You → ${item.committed_to}` : 'You';
  if (item.direction === 'to_user') return `${item.committed_by ?? 'Someone'} → you`;
  return [item.committed_by, item.committed_to].filter(Boolean).join(' → ');
}

export function dueLabel(item: Worded): string | null {
  if (!item.due) return null;
  const [year, month, day] = item.due.split('-').map(Number);
  const text = new Date(year, month - 1, day).toLocaleDateString(undefined, {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
  });
  return item.overdue ? `Was due ${text}` : `Due ${text}`;
}

const ORIGIN: Record<string, string> = {
  user_stated: 'You said this',
  source_explicit: 'Stated in the message',
  inferred: 'Inferred from the message',
};

export const originLabel = (origin: string) => ORIGIN[origin] ?? origin;
