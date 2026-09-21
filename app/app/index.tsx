import { useEffect, useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { getHealth } from '../src/api/client';

type Connection = 'checking' | 'connected' | 'unreachable';

const MESSAGE: Record<Connection, string> = {
  checking: 'Connecting…',
  connected: 'Connected. Nothing needs your attention yet.',
  unreachable: 'Can’t reach your world right now.',
};

// Phase 0 placeholder. "Needs attention" (Slice 1) replaces the body of this screen.
export default function Home() {
  const [connection, setConnection] = useState<Connection>('checking');

  useEffect(() => {
    let active = true;
    getHealth()
      .then((health) => active && setConnection(health.status === 'ok' ? 'connected' : 'unreachable'))
      .catch(() => active && setConnection('unreachable'));
    return () => {
      active = false;
    };
  }, []);

  return (
    <SafeAreaView style={styles.screen}>
      <View style={styles.content}>
        <Text style={styles.title}>Your World</Text>
        <Text style={styles.body}>{MESSAGE[connection]}</Text>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: '#FAFAF7' },
  content: { flex: 1, padding: 24, maxWidth: 560, width: '100%', alignSelf: 'center' },
  title: { fontSize: 32, fontWeight: '600', color: '#1C1C1A', marginTop: 48 },
  body: { fontSize: 17, lineHeight: 24, color: '#55554F', marginTop: 12 },
});
