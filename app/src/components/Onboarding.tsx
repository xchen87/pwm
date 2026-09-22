import { useState } from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { connectDemo, type ConnectionsView } from '../api/client';
import { reconnectGoogle } from '../signIn';
import { color, space } from '../theme';
import { Button } from './Button';

type Props = { connections: ConnectionsView; onConnected: () => Promise<void> | void };

export function Onboarding({ connections, onConnected }: Props) {
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const connect = async () => {
    setWorking(true);
    setError(null);
    try {
      await connectDemo();
      await onConnected();
    } catch {
      setError('That didn’t work. Is the server running?');
    } finally {
      setWorking(false);
    }
  };

  const google = async () => {
    setWorking(true);
    setError(null);
    try {
      if (await reconnectGoogle()) await onConnected();
    } catch {
      setError('Google sign-in didn’t complete. Try again.');
    } finally {
      setWorking(false);
    }
  };

  const googleAvailable = connections.available.some((s) => s.connector === 'gmail' && s.available);

  return (
    <SafeAreaView style={styles.screen}>
      <ScrollView contentContainerStyle={styles.content}>
        <Text style={styles.title}>Connect your life.</Text>
        <Text style={styles.lead}>
          I’ll read what you connect, remember what matters, tell you what changed, and catch things before
          they become problems.
        </Text>

        <View style={styles.promises}>
          <Text style={styles.promise}>• Read-only. I never send, delete, or change anything.</Text>
          <Text style={styles.promise}>• Every claim shows the exact words it came from.</Text>
          <Text style={styles.promise}>• A guess stays a guess until you confirm it.</Text>
          <Text style={styles.promise}>• Disconnect any time and what it brought in is deleted.</Text>
        </View>

        {googleAvailable && (
          <View style={styles.source}>
            <Text style={styles.sourceLabel}>Gmail and Google Calendar</Text>
            <Text style={styles.note}>
              One Google sign-in, read-only. I start with the last 90 days, newest first, so the first
              things appear within minutes.
            </Text>
            <Button label={working ? 'Opening Google…' : 'Continue with Google'} kind="primary" onPress={google} disabled={working} />
          </View>
        )}
        {connections.available
          .filter((source) => !(googleAvailable && source.connector !== 'demo'))
          .map((source) => (
          <View key={source.connector} style={styles.source}>
            <Text style={styles.sourceLabel}>{source.label}</Text>
            <Text style={styles.note}>{source.note}</Text>
            {source.connector === 'demo' && source.available ? (
              <Button
                label={working ? 'Reading and understanding…' : 'Connect the demo mailbox'}
                kind="primary"
                onPress={connect}
                disabled={working}
              />
            ) : (
              <Text style={styles.soon}>Not available yet</Text>
            )}
          </View>
          ))}
        {error && <Text style={styles.error}>{error}</Text>}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: color.ground },
  content: { padding: space.xl, paddingBottom: 64, maxWidth: 640, width: '100%', alignSelf: 'center' },
  title: { fontSize: 34, fontWeight: '700', color: color.ink, marginTop: 48 },
  lead: { fontSize: 18, lineHeight: 26, color: color.ink, marginTop: space.md },
  promises: { marginTop: space.xl, gap: space.sm },
  promise: { fontSize: 15, lineHeight: 21, color: color.muted },
  source: {
    backgroundColor: color.card,
    borderWidth: 1,
    borderColor: color.line,
    borderRadius: 14,
    padding: space.lg,
    marginTop: space.lg,
    gap: space.sm,
  },
  sourceLabel: { fontSize: 17, fontWeight: '700', color: color.ink },
  note: { fontSize: 14, lineHeight: 20, color: color.muted },
  soon: { fontSize: 13, fontWeight: '700', color: color.muted, textTransform: 'uppercase', letterSpacing: 0.3 },
  error: { fontSize: 14, color: color.warn, marginTop: space.md },
});
