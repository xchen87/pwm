import { Pressable, StyleSheet, Text, View } from 'react-native';

import type { CommitmentItem } from '../api/client';
import { color, space } from '../theme';
import { dueLabel, heading, isFact, parties } from '../wording';
import { Button } from './Button';

type Props = {
  item: CommitmentItem;
  busy: boolean;
  onOpen: () => void;
  onConfirm: () => void;
  onDismiss: () => void;
  onEdit: () => void;
  onDone: () => void;
};

export function CommitmentCard({ item, busy, onOpen, onConfirm, onDismiss, onEdit, onDone }: Props) {
  const due = dueLabel(item);
  const fact = isFact(item);
  const summarised = item.what !== item.evidence_quote;
  return (
    <View style={styles.card}>
      <Pressable onPress={onOpen} accessibilityRole="link" accessibilityLabel="See where this came from">
        <View style={styles.row}>
          <Text style={[styles.heading, !fact && styles.possible]}>{heading(item)}</Text>
          {due && <Text style={[styles.due, item.overdue && styles.overdue]}>{due}</Text>}
        </View>
        <Text style={styles.parties}>{parties(item)}</Text>
        {summarised && <Text style={styles.what}>{item.what}</Text>}
        <Text style={styles.quote}>“{item.evidence_quote}”</Text>
        <Text style={styles.source}>
          {item.source.sender_name ?? item.source.sender_address ?? 'You'} · {item.source.subject || 'Note'}
          {item.has_conflict ? ' · another source disagrees' : ''}
        </Text>
      </Pressable>
      <View style={styles.actions}>
        {fact ? (
          <Button label="Done" kind="primary" onPress={onDone} disabled={busy} />
        ) : (
          <Button label="Confirm" kind="primary" onPress={onConfirm} disabled={busy} />
        )}
        <Button label="Dismiss" onPress={onDismiss} disabled={busy} />
        <Button label="Edit" onPress={onEdit} disabled={busy} />
      </View>
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
  row: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'baseline', gap: space.sm },
  heading: { fontSize: 13, fontWeight: '700', letterSpacing: 0.3, textTransform: 'uppercase', color: color.accent },
  possible: { color: color.muted },
  due: { fontSize: 13, fontWeight: '600', color: color.ink },
  overdue: { color: color.warn },
  parties: { fontSize: 15, fontWeight: '600', color: color.ink, marginTop: space.sm },
  what: { fontSize: 16, lineHeight: 22, color: color.ink, marginTop: space.xs },
  quote: {
    fontSize: 15,
    lineHeight: 21,
    color: color.ink,
    backgroundColor: color.quote,
    borderRadius: 8,
    padding: space.md,
    marginTop: space.sm,
  },
  source: { fontSize: 13, color: color.muted, marginTop: space.sm },
  actions: { flexDirection: 'row', gap: space.sm, marginTop: space.md, flexWrap: 'wrap' },
});
