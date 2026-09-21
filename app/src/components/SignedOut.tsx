import { useState } from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { signInWithGoogle } from '../signIn';
import { color, space } from '../theme';
import { Button } from './Button';

type Props = { googleAvailable: boolean; onSignedIn: () => Promise<void> | void };

/** Shown whenever there is no valid session. Depends on nothing that needs one. */
export function SignedOut({ googleAvailable, onSignedIn }: Props) {
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const signIn = async () => {
    setWorking(true);
    setError(null);
    try {
      if (await signInWithGoogle()) await onSignedIn();
    } catch {
      setError('Google sign-in didn’t complete. Try again.');
    } finally {
      setWorking(false);
    }
  };

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
        {googleAvailable ? (
          <Button
            label={working ? 'Opening Google…' : 'Continue with Google'}
            kind="primary"
            onPress={signIn}
            disabled={working}
          />
        ) : (
          <Text style={styles.note}>Sign-in isn’t set up on this server yet.</Text>
        )}
        {error && <Text style={styles.error}>{error}</Text>}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: color.ground },
  content: { padding: space.xl, paddingBottom: 64, maxWidth: 640, width: '100%', alignSelf: 'center', gap: space.lg },
  title: { fontSize: 34, fontWeight: '700', color: color.ink, marginTop: 48 },
  lead: { fontSize: 18, lineHeight: 26, color: color.ink },
  promises: { gap: space.sm },
  promise: { fontSize: 15, lineHeight: 21, color: color.muted },
  note: { fontSize: 15, color: color.muted },
  error: { fontSize: 14, color: color.warn },
});
