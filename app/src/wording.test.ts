import { dueLabel, heading, isFact, parties } from './wording';

const base = {
  kind: 'commitment',
  review: 'unreviewed',
  origin: 'source_explicit',
  commitment_type: 'promise',
  direction: 'to_user',
  committed_by: 'Tom Okafor',
  committed_to: 'Alex Rivera',
  due: '2026-09-14',
  overdue: false,
};

describe('wording', () => {
  it('never presents an unreviewed item as fact', () => {
    expect(isFact(base)).toBe(false);
    expect(heading(base)).toBe('Possible commitment');
    expect(heading({ ...base, commitment_type: 'deadline' })).toBe('Possible deadline');
  });

  it('presents only confirmed items as fact', () => {
    expect(heading({ ...base, review: 'confirmed' })).toBe('Commitment');
    expect(heading({ ...base, origin: 'user_stated' })).toBe('Possible commitment');
    expect(heading({ ...base, review: 'rejected', origin: 'user_stated' })).toBe('Possible commitment');
  });

  it('names other kinds of fact for what they are', () => {
    expect(heading({ ...base, kind: 'thing', commitment_type: null })).toBe('Possible detail');
    expect(heading({ ...base, kind: 'decision', commitment_type: null, review: 'confirmed' })).toBe('Decision');
    expect(heading({ ...base, kind: 'memory', commitment_type: null })).toBe('You told me');
    expect(parties({ ...base, kind: 'thing' })).toBe('');
  });

  it('says who owes whom', () => {
    expect(parties(base)).toBe('Tom Okafor → you');
    expect(parties({ ...base, direction: 'by_user', committed_by: 'Alex Rivera', committed_to: 'Tom Okafor' })).toBe(
      'You → Tom Okafor',
    );
  });

  it('marks overdue dates', () => {
    expect(dueLabel(base)).toMatch(/^Due /);
    expect(dueLabel({ ...base, overdue: true })).toMatch(/^Was due /);
    expect(dueLabel({ ...base, due: null })).toBeNull();
  });
});
