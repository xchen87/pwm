import { useFocusEffect, useRouter } from 'expo-router';
import { useCallback, useState } from 'react';
import { ScrollView, StyleSheet, Text } from 'react-native';

import {
  type BriefView,
  generateBrief,
  getLatestBrief,
  markNotificationsRead,
  recordEvent,
} from '../src/api/client';
import { Button } from '../src/components/Button';
import { ChangeCard } from '../src/components/ChangeCard';
import { color, space } from '../src/theme';

export default function WorldBrief() {
  const router = useRouter();
  const [brief, setBrief] = useState<BriefView | null>(null);
  const [missing, setMissing] = useState(false);
  const [rated, setRated] = useState<Record<string, boolean>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const show = (loaded: BriefView) => {
    setBrief(loaded);
    setMissing(false);
    setError(null);
    void recordEvent('brief_opened', loaded.id);
    void markNotificationsRead().catch(() => undefined);
  };

  useFocusEffect(
    useCallback(() => {
      getLatestBrief().then(show, (problem: Error) => {
        // "No brief yet" is an answer; a network failure is not the same thing.
        if (/no brief yet/i.test(problem.message)) {
          setBrief(null); // it may have been removed since this screen last showed it
          setMissing(true);
        } else setError('Can’t reach your world right now.');
      });
    }, []),
  );

  const create = async () => {
    setBusy(true);
    setError(null);
    try {
      show(await generateBrief());
    } catch {
      setError('Couldn’t make a brief just now. Try again.');
    } finally {
      setBusy(false);
    }
  };

  const made = brief
    ? new Date(brief.created_at).toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric' })
    : '';

  return (
    <ScrollView contentContainerStyle={styles.content}>
      {brief && (
        <>
          <Text style={styles.date}>{made}</Text>
          {brief.items.length === 0 && <Text style={styles.empty}>A quiet week. Nothing you need to know about.</Text>}
          {brief.items.map((written) => (
            <ChangeCard
              key={written.item.assertion_id}
              written={written}
              rated={rated[written.item.assertion_id]}
              onOpen={() => router.push({ pathname: '/assertion/[id]', params: { id: written.item.assertion_id } })}
              onUseful={(useful) => {
                setRated((current) => ({ ...current, [written.item.assertion_id]: true }));
                void recordEvent(useful ? 'item_useful' : 'item_not_useful', written.item.assertion_id);
              }}
            />
          ))}
        </>
      )}
      {missing && <Text style={styles.empty}>No brief yet.</Text>}
      {error && <Text style={styles.error}>{error}</Text>}
      <Button label={brief ? 'Make a fresh brief' : 'Make my first brief'} onPress={create} disabled={busy} />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  content: { padding: space.lg, paddingBottom: 64, maxWidth: 640, width: '100%', alignSelf: 'center' },
  date: { fontSize: 14, color: color.muted, marginBottom: space.md },
  empty: { fontSize: 16, color: color.muted, marginBottom: space.lg },
  error: { fontSize: 14, color: color.warn, marginBottom: space.lg },
});
