import { useFocusEffect, useLocalSearchParams, useRouter } from 'expo-router';
import { useCallback, useState } from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';

import {
  type AssertionDetail,
  confirmAssertion,
  dismissAssertion,
  getAssertion,
  setCommitmentStatus,
} from '../../src/api/client';
import { Button } from '../../src/components/Button';
import { color, space } from '../../src/theme';
import { dueLabel, heading, isFact, originLabel, parties } from '../../src/wording';

const CONFIDENCE: Record<string, string> = {
  high: 'High — said plainly by someone you correspond with, or by you',
  medium: 'Medium — said plainly, but by a sender you have not written to',
  low: 'Low — inferred, or the message looks untrustworthy',
};

const RELATION: Record<string, string> = {
  contradicts: 'Another source disagrees',
  supersedes: 'This replaced',
  superseded_by: 'Replaced by',
};

function Evidence({ context, quote }: { context: string; quote: string }) {
  const at = context.indexOf(quote);
  if (at < 0) return <Text style={styles.context}>{context}</Text>;
  return (
    <Text style={styles.context}>
      {context.slice(0, at)}
      <Text style={styles.highlight}>{quote}</Text>
      {context.slice(at + quote.length)}
    </Text>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.fact}>
      <Text style={styles.factLabel}>{label}</Text>
      <Text style={styles.factValue}>{value}</Text>
    </View>
  );
}

export default function Inspect() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const [detail, setDetail] = useState<AssertionDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useFocusEffect(
    useCallback(() => {
      getAssertion(id).then(setDetail, () => setError('Can’t load this right now.'));
    }, [id]),
  );

  const act = (action: () => Promise<AssertionDetail>, leave = false) =>
    action().then(
      (updated) => (leave ? router.back() : setDetail(updated)),
      (problem: Error) => setError(problem.message),
    );

  if (!detail) return <Text style={styles.loading}>{error ?? 'Loading…'}</Text>;

  const observed = new Date(detail.source.observed_at).toLocaleString(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  });
  const replaced = detail.related.some((r) => r.relation === 'superseded_by');
  const due = dueLabel(detail);

  return (
    <ScrollView contentContainerStyle={styles.content}>
      <Text style={[styles.heading, !isFact(detail) && styles.possible]}>{heading(detail)}</Text>
      <Text style={styles.what}>{detail.what}</Text>
      <Text style={styles.parties}>
        {parties(detail)}
        {due ? ` · ${due}` : ''}
      </Text>

      {detail.source_suspicious && (
        <Text style={styles.warning}>
          This message contains text that looks like it was written to manipulate an assistant. Treat it
          with care.
        </Text>
      )}

      <Text style={styles.section}>The evidence</Text>
      <Evidence context={detail.context} quote={detail.evidence_quote} />
      <Text style={styles.sourceLine}>
        {detail.source.sender_name ?? detail.source.sender_address ?? 'You'}
        {detail.source.sender_name && detail.source.sender_address ? ` <${detail.source.sender_address}>` : ''}
      </Text>
      <Text style={styles.sourceLine}>
        {detail.source.subject || 'Note'} · {observed}
      </Text>

      <Text style={styles.section}>How I know</Text>
      <Fact label="Basis" value={originLabel(detail.origin)} />
      <Fact label="Confidence" value={CONFIDENCE[detail.confidence] ?? detail.confidence} />
      <Fact label="Your review" value={isFact(detail) ? 'You confirmed this' : `Not confirmed (${detail.review})`} />
      <Fact label="Found by" value={detail.extraction_method} />

      {detail.related.length > 0 && <Text style={styles.section}>Related</Text>}
      {detail.related.map((other) => (
        <View key={`${other.relation}-${other.id}`} style={styles.related}>
          <Text style={styles.factLabel}>{RELATION[other.relation] ?? other.relation}</Text>
          <Text style={styles.relatedQuote}>“{other.evidence_quote}”</Text>
          <Text style={styles.sourceLine}>
            {other.source.sender_name ?? other.source.sender_address ?? 'You'} · {other.source.subject || 'Note'}
          </Text>
        </View>
      ))}

      {error && <Text style={styles.warning}>{error}</Text>}
      {!replaced && (
        <View style={styles.actions}>
          {isFact(detail) ? (
            detail.status === 'open' && (
              <>
                <Button label="Done" kind="primary" onPress={() => act(() => setCommitmentStatus(id, 'done'), true)} />
                <Button label="No longer needed" onPress={() => act(() => setCommitmentStatus(id, 'cancelled'), true)} />
              </>
            )
          ) : (
            <>
              <Button label="Confirm" kind="primary" onPress={() => act(() => confirmAssertion(id))} />
              <Button label="Dismiss" onPress={() => act(() => dismissAssertion(id), true)} />
            </>
          )}
          <Button label="Edit" onPress={() => router.push({ pathname: '/edit/[id]', params: { id } })} />
        </View>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  content: { padding: space.lg, paddingBottom: 64, maxWidth: 640, width: '100%', alignSelf: 'center' },
  loading: { padding: space.xl, fontSize: 16, color: color.muted },
  heading: { fontSize: 13, fontWeight: '700', letterSpacing: 0.3, textTransform: 'uppercase', color: color.accent },
  possible: { color: color.muted },
  what: { fontSize: 22, lineHeight: 29, fontWeight: '600', color: color.ink, marginTop: space.sm },
  parties: { fontSize: 15, color: color.muted, marginTop: space.sm },
  section: { fontSize: 16, fontWeight: '700', color: color.ink, marginTop: space.xl, marginBottom: space.sm },
  context: {
    fontSize: 15,
    lineHeight: 22,
    color: color.muted,
    backgroundColor: color.quote,
    borderRadius: 10,
    padding: space.md,
  },
  highlight: { color: color.ink, fontWeight: '600', backgroundColor: color.accentSoft },
  sourceLine: { fontSize: 13, color: color.muted, marginTop: space.xs },
  fact: { paddingVertical: space.sm, borderBottomWidth: 1, borderBottomColor: color.line },
  factLabel: { fontSize: 12, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.3, color: color.muted },
  factValue: { fontSize: 15, color: color.ink, marginTop: 2 },
  related: { paddingVertical: space.sm },
  relatedQuote: { fontSize: 15, lineHeight: 21, color: color.ink, marginTop: 2 },
  warning: {
    fontSize: 14,
    color: color.warn,
    backgroundColor: color.warnSoft,
    padding: space.md,
    borderRadius: 10,
    marginTop: space.md,
  },
  actions: { flexDirection: 'row', flexWrap: 'wrap', gap: space.sm, marginTop: space.xl },
});
