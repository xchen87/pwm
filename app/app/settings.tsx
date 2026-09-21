import { useFocusEffect, useRouter } from 'expo-router';
import { useCallback, useState } from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';

import {
  confirmSamePerson,
  type ConnectionsView,
  deleteEverything,
  disconnect,
  getConnections,
  getPeople,
  markDifferentPerson,
  type PersonView,
} from '../src/api/client';
import { Button } from '../src/components/Button';
import { color, space } from '../src/theme';

export default function Settings() {
  const router = useRouter();
  const [state, setState] = useState<ConnectionsView | null>(null);
  const [people, setPeople] = useState<PersonView[]>([]);
  const [confirming, setConfirming] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    getConnections().then(setState, () => setError('Can’t reach your world right now.'));
    getPeople().then(setPeople, () => undefined);
  }, []);
  useFocusEffect(load);

  const run = async (action: () => Promise<unknown>, leave: boolean) => {
    if (busy) return; // a second tap must not repeat a destructive call
    setBusy(true);
    setError(null);
    try {
      await action();
      setConfirming(null);
      if (leave) router.dismissTo('/');
      else load();
    } catch {
      setError('That didn’t work. Try again.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <ScrollView contentContainerStyle={styles.content}>
      <Text style={styles.section}>Connected</Text>
      {state?.connected.length === 0 && <Text style={styles.muted}>Nothing is connected.</Text>}
      {state?.connected.map((c) => (
        <View key={c.connector} style={styles.card}>
          <Text style={styles.label}>{c.label}</Text>
          <Text style={styles.muted}>
            {c.sources} items read · connected {new Date(c.connected_at).toLocaleDateString()}
          </Text>
          {confirming === c.connector ? (
            <View style={styles.row}>
              <Button
                label="Yes, disconnect and delete"
                kind="primary"
                onPress={() => run(() => disconnect(c.connector), true)}
              />
              <Button label="Keep it" onPress={() => setConfirming(null)} />
            </View>
          ) : (
            <Button label="Disconnect and delete its data" onPress={() => setConfirming(c.connector)} />
          )}
          <Text style={styles.muted}>
            Removes everything this connection brought in and everything I understood from it. Notes you
            typed yourself are kept.
          </Text>
        </View>
      ))}

      {people.some((p) => p.identifiers.some((i) => i.link === 'inferred')) && (
        <Text style={styles.section}>Is this the same person?</Text>
      )}
      {people.flatMap((person) =>
        person.identifiers
          .filter((identifier) => identifier.link === 'inferred')
          .map((identifier) => (
            <View key={identifier.id} style={styles.card}>
              <Text style={styles.label}>{identifier.address}</Text>
              <Text style={styles.muted}>
                This looks like another address for {person.name}. Until you say so, it can’t change
                anything {person.name} told you — anyone can sign a message with someone else’s name.
              </Text>
              <View style={styles.row}>
                <Button
                  label={`Yes, that’s ${person.name.split(' ')[0]}`}
                  kind="primary"
                  onPress={() => run(() => confirmSamePerson(identifier.id), false)}
                />
                <Button
                  label="No, someone else"
                  onPress={() => run(() => markDifferentPerson(identifier.id, identifier.address), false)}
                />
              </View>
            </View>
          )),
      )}

      <Text style={styles.section}>What I hold</Text>
      <Text style={styles.muted}>{state?.understood ?? 0} things understood from what you connected.</Text>

      <Text style={styles.section}>Delete everything</Text>
      <Text style={styles.muted}>Removes every source, everything understood, your notes, and your briefs.</Text>
      {confirming === 'everything' ? (
        <View style={styles.row}>
          <Button label="Yes, delete everything" kind="primary" onPress={() => run(deleteEverything, true)} />
          <Button label="Cancel" onPress={() => setConfirming(null)} />
        </View>
      ) : (
        <Button label="Delete everything" onPress={() => setConfirming('everything')} />
      )}
      {error && <Text style={styles.error}>{error}</Text>}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  content: { padding: space.lg, paddingBottom: 64, maxWidth: 640, width: '100%', alignSelf: 'center', gap: space.sm },
  section: { fontSize: 18, fontWeight: '700', color: color.ink, marginTop: space.xl },
  card: {
    backgroundColor: color.card,
    borderWidth: 1,
    borderColor: color.line,
    borderRadius: 14,
    padding: space.lg,
    gap: space.sm,
  },
  label: { fontSize: 16, fontWeight: '700', color: color.ink },
  muted: { fontSize: 14, lineHeight: 20, color: color.muted },
  row: { flexDirection: 'row', flexWrap: 'wrap', gap: space.sm },
  error: { fontSize: 14, color: color.warn, marginTop: space.md },
});
