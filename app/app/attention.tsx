import { useFocusEffect, useRouter } from 'expo-router';
import { useCallback, useState } from 'react';
import { RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import {
  type CommitmentItem,
  confirmAssertion,
  dismissAssertion,
  getCommitments,
  setCommitmentStatus,
} from '../src/api/client';
import { CommitmentCard } from '../src/components/CommitmentCard';
import { color, space } from '../src/theme';
import { isFact } from '../src/wording';

export default function NeedsAttention() {
  const router = useRouter();
  const [items, setItems] = useState<CommitmentItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      setItems(await getCommitments());
      setError(null);
    } catch {
      setError('Can’t reach your world right now. Pull down to try again.');
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      void load();
    }, [load]),
  );

  const act = async (id: string, action: () => Promise<unknown>) => {
    setBusy(id);
    try {
      await action();
      await load();
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : 'That didn’t work. Try again.');
    } finally {
      setBusy(null);
    }
  };

  const render = (item: CommitmentItem) => (
    <CommitmentCard
      key={item.id}
      item={item}
      busy={busy === item.id}
      onOpen={() => router.push({ pathname: '/assertion/[id]', params: { id: item.id } })}
      onEdit={() => router.push({ pathname: '/edit/[id]', params: { id: item.id } })}
      onConfirm={() => act(item.id, () => confirmAssertion(item.id))}
      onDismiss={() => act(item.id, () => dismissAssertion(item.id))}
      onDone={() => act(item.id, () => setCommitmentStatus(item.id, 'done'))}
    />
  );

  const possible = items?.filter((item) => !isFact(item)) ?? [];
  const confirmed = items?.filter(isFact) ?? [];

  return (
    <SafeAreaView style={styles.screen} edges={[]}>
      <ScrollView
        contentContainerStyle={styles.content}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={async () => {
              setRefreshing(true);
              await load();
              setRefreshing(false);
            }}
          />
        }
      >
        {error && <Text style={styles.error}>{error}</Text>}
        {items && items.length === 0 && !error && (
          <Text style={styles.empty}>Nothing needs your attention.</Text>
        )}
        {confirmed.length > 0 && (
          <View>
            <Text style={styles.section}>On your list</Text>
            {confirmed.map(render)}
          </View>
        )}
        {possible.length > 0 && (
          <View>
            <Text style={styles.section}>Did I get these right?</Text>
            <Text style={styles.hint}>
              Found in your mail and calendar. Nothing is tracked until you confirm it.
            </Text>
            {possible.map(render)}
          </View>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: color.ground },
  content: { padding: space.lg, paddingBottom: 64, maxWidth: 640, width: '100%', alignSelf: 'center' },
  title: { fontSize: 30, fontWeight: '700', color: color.ink, marginTop: space.xl, marginBottom: space.sm },
  section: { fontSize: 18, fontWeight: '700', color: color.ink, marginTop: space.xl, marginBottom: space.xs },
  hint: { fontSize: 14, color: color.muted, marginBottom: space.md },
  empty: { fontSize: 17, color: color.muted, marginTop: space.md },
  error: {
    fontSize: 15,
    color: color.warn,
    backgroundColor: color.warnSoft,
    padding: space.md,
    borderRadius: 10,
    marginTop: space.sm,
  },
});
