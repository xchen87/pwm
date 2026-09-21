import { Pressable, StyleSheet, Text, View } from 'react-native';

import type { WrittenItem } from '../api/client';
import { color, space } from '../theme';

const LABEL: Record<string, string> = {
  due_soon: 'Coming up',
  changed: 'Changed',
  conflict: 'Sources disagree',
  possible_commitment: 'To review',
  consumer: 'Heads up',
  remembered: 'You asked me to remember',
};

type Props = {
  written: WrittenItem;
  onOpen: () => void;
  onUseful?: (useful: boolean) => void;
  rated?: boolean;
};

export function ChangeCard({ written, onOpen, onUseful, rated }: Props) {
  const { item } = written;
  return (
    <View style={styles.card}>
      <Pressable onPress={onOpen} accessibilityRole="link" accessibilityLabel="See where this came from">
        <Text style={[styles.label, item.kind === 'conflict' && styles.warn]}>{LABEL[item.kind] ?? item.kind}</Text>
        <Text style={styles.headline}>{written.headline}</Text>
        <Text style={styles.why}>{written.why_it_matters}</Text>
        {written.suggested_next_step && <Text style={styles.step}>{written.suggested_next_step}</Text>}
        <Text style={styles.quote}>“{item.evidence_quote}”</Text>
        {item.other_evidence_quote && (
          <Text style={styles.quote}>
            {item.kind === 'conflict' ? 'The other source: ' : 'Before: '}“{item.other_evidence_quote}”
          </Text>
        )}
        <Text style={styles.source}>{item.source_label} · tap to see the source</Text>
      </Pressable>
      {onUseful && (
        <View style={styles.rating}>
          {rated ? (
            <Text style={styles.source}>Thanks — noted.</Text>
          ) : (
            <>
              <Text style={styles.source}>Was this useful?</Text>
              <Pressable onPress={() => onUseful(true)} accessibilityRole="button" accessibilityLabel="Useful">
                <Text style={styles.rate}>Yes</Text>
              </Pressable>
              <Pressable onPress={() => onUseful(false)} accessibilityRole="button" accessibilityLabel="Not useful">
                <Text style={styles.rate}>No</Text>
              </Pressable>
            </>
          )}
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: color.card,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: color.line,
    padding: space.lg,
    marginBottom: space.md,
  },
  label: { fontSize: 12, fontWeight: '700', letterSpacing: 0.3, textTransform: 'uppercase', color: color.accent },
  warn: { color: color.warn },
  headline: { fontSize: 17, lineHeight: 23, fontWeight: '600', color: color.ink, marginTop: space.xs },
  why: { fontSize: 14, lineHeight: 20, color: color.muted, marginTop: space.xs },
  step: { fontSize: 14, lineHeight: 20, color: color.ink, marginTop: space.xs },
  quote: {
    fontSize: 14,
    lineHeight: 20,
    color: color.ink,
    backgroundColor: color.quote,
    borderRadius: 8,
    padding: space.sm,
    marginTop: space.sm,
  },
  source: { fontSize: 13, color: color.muted, marginTop: space.sm },
  rating: { flexDirection: 'row', alignItems: 'baseline', gap: space.lg, marginTop: space.xs },
  rate: { fontSize: 14, fontWeight: '700', color: color.accent, paddingVertical: space.sm },
});
