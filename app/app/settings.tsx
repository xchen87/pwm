import { useFocusEffect, useRouter } from 'expo-router';
import { useCallback, useState } from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';

import {
  confirmSamePerson,
  type ConnectionsView,
  deleteEverything,
  disconnect,
  getConnections,
  getMe,
  getPeople,
  markDifferentPerson,
  type Me,
  type PersonView,
  signOut,
} from '../src/api/client';
import { Button } from '../src/components/Button';
import { lockAvailable, lockEnabled, setLockEnabled } from '../src/lock';
import { disablePush, enablePush } from '../src/push';
import { clearToken } from '../src/session';
import { signInWithGoogle } from '../src/signIn';
import { color, space } from '../src/theme';

export default function Settings() {
  const router = useRouter();
  const [state, setState] = useState<ConnectionsView | null>(null);
  const [people, setPeople] = useState<PersonView[]>([]);
  const [me, setMe] = useState<Me | null>(null);
  const [lock, setLock] = useState<{ available: boolean; on: boolean }>({ available: false, on: false });
  const [push, setPush] = useState<string | null>(null);
  const [confirming, setConfirming] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    getConnections().then(setState, () => setError('Can’t reach your world right now.'));
    getPeople().then(setPeople, () => undefined);
    getMe().then(setMe, () => undefined);
    Promise.all([lockAvailable(), lockEnabled()]).then(([available, on]) => setLock({ available, on }));
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
      {me?.signed_in_with_google && (
        <View style={styles.card}>
          <Text style={styles.label}>{me.name ?? me.email}</Text>
          <Text style={styles.muted}>Signed in with Google as {me.email}</Text>
          <Button
            label="Sign out"
            onPress={() => run(() => disablePush().then(signOut).finally(clearToken), true)}
          />
        </View>
      )}

      <Text style={styles.section}>Connected</Text>
      {state?.connected.length === 0 && <Text style={styles.muted}>Nothing is connected.</Text>}
      {state?.connected.map((c) => (
        <View key={c.connector} style={styles.card}>
          <Text style={styles.label}>{c.label}</Text>
          <Text style={styles.muted}>
            {c.sources} items read · connected {new Date(c.connected_at).toLocaleDateString()}
            {c.status === 'syncing' ? ' · still reading older mail' : ''}
          </Text>
          {c.status === 'needs_reconnect' && (
            <>
              <Text style={styles.error}>
                Google says my access has ended (you removed it, or it expired). Nothing new is being read.
              </Text>
              <Button label="Reconnect with Google" kind="primary" onPress={() => run(signInWithGoogle, false)} />
            </>
          )}
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

      <Text style={styles.section}>On this phone</Text>
      {lock.available ? (
        <View style={styles.card}>
          <Text style={styles.label}>App lock {lock.on ? 'is on' : 'is off'}</Text>
          <Text style={styles.muted}>Ask for your fingerprint, face or passcode whenever the app opens.</Text>
          <Button
            label={lock.on ? 'Turn off' : 'Turn on'}
            onPress={() => setLockEnabled(!lock.on).then(() => setLock({ ...lock, on: !lock.on }))}
          />
        </View>
      ) : (
        <Text style={styles.muted}>App lock needs a phone with a fingerprint, face or passcode set up.</Text>
      )}
      <View style={styles.card}>
        <Text style={styles.label}>Notifications</Text>
        <Text style={styles.muted}>
          A note when a new World Brief is ready. The notification says only that; nothing personal ever goes to a lock screen.
        </Text>
        <Button
          label="Allow notifications"
          onPress={() =>
            enablePush(true).then(
              (on) => setPush(on ? 'On for this phone.' : 'Not available here (a real phone with a store build is needed).'),
              () => setPush('That didn’t work.'),
            )
          }
        />
        {push && <Text style={styles.muted}>{push}</Text>}
      </View>

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
