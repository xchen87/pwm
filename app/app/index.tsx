import { useFocusEffect, useRouter } from 'expo-router';
import { useCallback, useState } from 'react';
import { Pressable, RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { type ConnectionsView, getConnections, getHome, type Home, recordVisit } from '../src/api/client';
import { ChangeCard } from '../src/components/ChangeCard';
import { Onboarding } from '../src/components/Onboarding';
import { color, space } from '../src/theme';
import { dueLabel, heading, parties } from '../src/wording';

function sinceLabel(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { weekday: 'long', month: 'short', day: 'numeric' });
}

export default function YourWorld() {
  const router = useRouter();
  const [home, setHome] = useState<Home | null>(null);
  const [connections, setConnections] = useState<ConnectionsView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      const current = await getConnections();
      setConnections(current);
      if (current.connected.length > 0 || current.understood > 0) setHome(await getHome());
      setError(null);
    } catch {
      setError('Can’t reach your world right now. Pull down to try again.');
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      void recordVisit()
        .catch(() => undefined)
        .then(load);
    }, [load]),
  );

  // Onboarding is for an empty world. With nothing connected but notes (or anything else)
  // still held, the user must be able to reach them, and the screen that deletes them.
  if (connections && connections.connected.length === 0 && connections.understood === 0) {
    return <Onboarding connections={connections} onConnected={load} />;
  }

  const open = (id: string) => router.push({ pathname: '/assertion/[id]', params: { id } });

  return (
    <SafeAreaView style={styles.screen} edges={['top']}>
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
        <View style={styles.header}>
          <Text style={styles.title}>Your World</Text>
          <Pressable onPress={() => router.push('/brief')} accessibilityRole="link" accessibilityLabel="Open your World Brief">
            <Text style={styles.link}>
              World Brief{home && home.unread_notifications > 0 ? ' •' : ''}
            </Text>
          </Pressable>
        </View>
        {error && <Text style={styles.error}>{error}</Text>}
        {connections?.connected.length === 0 && (
          <Pressable onPress={() => router.push('/settings')} accessibilityRole="link">
            <Text style={styles.error}>Nothing is connected. Your notes are still here. Manage your data →</Text>
          </Pressable>
        )}

        <Pressable style={styles.ask} onPress={() => router.push('/ask')} accessibilityRole="link">
          <Text style={styles.askText}>Ask your world…</Text>
        </Pressable>

        {home && (
          <>
            <Text style={styles.section}>What changed</Text>
            <Text style={styles.hint}>Since {sinceLabel(home.since)}</Text>
            {home.what_changed.length === 0 && <Text style={styles.empty}>Nothing you need to know about.</Text>}
            {home.what_changed.map((written) => (
              <ChangeCard key={written.item.assertion_id} written={written} onOpen={() => open(written.item.assertion_id)} />
            ))}

            {home.what_changed_total > home.what_changed.length && (
              <Pressable onPress={() => router.push('/brief')} accessibilityRole="link">
                <Text style={styles.link}>
                  {home.what_changed_total - home.what_changed.length} more in your World Brief
                </Text>
              </Pressable>
            )}

            <View style={styles.header}>
              <Text style={styles.section}>Needs attention</Text>
              {home.needs_attention_total > home.needs_attention.length && (
                <Pressable onPress={() => router.push('/attention')} accessibilityRole="link">
                  <Text style={styles.link}>See all {home.needs_attention_total}</Text>
                </Pressable>
              )}
            </View>
            {home.needs_attention.length === 0 && <Text style={styles.empty}>Nothing needs your attention.</Text>}
            {home.needs_attention.map((item) => (
              <Pressable key={item.id} style={styles.row} onPress={() => open(item.id)} accessibilityRole="link">
                <Text style={styles.rowLabel}>
                  {[heading(item), parties(item), dueLabel(item)].filter(Boolean).join(' · ')}
                </Text>
                <Text style={styles.rowText} numberOfLines={2}>
                  {item.what}
                </Text>
              </Pressable>
            ))}

            <Text style={styles.section}>Remembered</Text>
            {home.remembered.length === 0 && (
              <Text style={styles.empty}>Things you ask me to remember will appear here.</Text>
            )}
            {home.remembered.map((item) => (
              <Pressable key={item.id} style={styles.row} onPress={() => open(item.id)} accessibilityRole="link">
                <Text style={styles.rowText}>{item.what}</Text>
              </Pressable>
            ))}
            <Pressable onPress={() => router.push('/remember')} accessibilityRole="link">
              <Text style={[styles.link, styles.add]}>+ Remember something</Text>
            </Pressable>
            <Pressable onPress={() => router.push('/settings')} accessibilityRole="link">
              <Text style={styles.settings}>Connections and your data</Text>
            </Pressable>
          </>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: color.ground },
  content: { padding: space.lg, paddingBottom: 64, maxWidth: 640, width: '100%', alignSelf: 'center' },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'baseline' },
  title: { fontSize: 30, fontWeight: '700', color: color.ink, marginTop: space.xl },
  link: { fontSize: 15, fontWeight: '700', color: color.accent },
  add: { marginTop: space.md },
  settings: { fontSize: 14, color: color.muted, marginTop: 40, textDecorationLine: 'underline' },
  ask: {
    backgroundColor: color.card,
    borderWidth: 1,
    borderColor: color.line,
    borderRadius: 12,
    padding: space.lg,
    marginTop: space.lg,
  },
  askText: { fontSize: 16, color: color.muted },
  section: { fontSize: 20, fontWeight: '700', color: color.ink, marginTop: space.xl, marginBottom: space.xs },
  hint: { fontSize: 14, color: color.muted, marginBottom: space.md },
  empty: { fontSize: 15, color: color.muted, marginTop: space.xs },
  row: { paddingVertical: space.md, borderBottomWidth: 1, borderBottomColor: color.line },
  rowLabel: { fontSize: 12, fontWeight: '700', letterSpacing: 0.3, textTransform: 'uppercase', color: color.muted },
  rowText: { fontSize: 16, lineHeight: 22, color: color.ink, marginTop: 2 },
  error: {
    fontSize: 15,
    color: color.warn,
    backgroundColor: color.warnSoft,
    padding: space.md,
    borderRadius: 10,
    marginTop: space.sm,
  },
});
