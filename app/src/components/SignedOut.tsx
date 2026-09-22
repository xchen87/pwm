import { useState } from 'react';
import { Linking, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { acceptTerms, type AuthConfig } from '../api/client';
import { SafeAreaView } from 'react-native-safe-area-context';

import { signInWithGoogle } from '../signIn';
import { color, space } from '../theme';
import { Button } from './Button';

type Props = {
  config: AuthConfig;
  onSignedIn: () => Promise<void> | void;
  // Set when someone is already signed in but the terms changed: accept, do not sign in again.
  reaccept?: boolean;
};

/** Shown whenever there is no valid session. Depends on nothing that needs one. */
export function SignedOut({ config, onSignedIn, reaccept = false }: Props) {
  const [working, setWorking] = useState(false);
  const [ofAge, setOfAge] = useState(false);
  const [agreed, setAgreed] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const signIn = async () => {
    setWorking(true);
    setError(null);
    try {
      if (reaccept) {
        await acceptTerms(config.terms_version);
        await onSignedIn();
        return;
      }
      if (await signInWithGoogle({ termsVersion: config.terms_version, ageConfirmed: true })) await onSignedIn();
    } catch {
      setError('Google sign-in didn’t complete. Try again.');
    } finally {
      setWorking(false);
    }
  };

  return (
    <SafeAreaView style={styles.screen}>
      <ScrollView contentContainerStyle={styles.content}>
        <Text style={styles.title}>{reaccept ? 'The terms have changed.' : 'Connect your life.'}</Text>
        <Text style={styles.lead}>
          {reaccept
            ? 'Please read and accept the updated terms and privacy policy to continue. Your data is untouched until you do.'
            : 'I’ll read what you connect, remember what matters, tell you what changed, and catch things before they become problems.'}
        </Text>
        <View style={styles.promises}>
          <Text style={styles.promise}>• Read-only. I never send, delete, or change anything.</Text>
          <Text style={styles.promise}>• Every claim shows the exact words it came from.</Text>
          <Text style={styles.promise}>• A guess stays a guess until you confirm it.</Text>
          <Text style={styles.promise}>• Disconnect any time and what it brought in is deleted.</Text>
        </View>
        {config.google || reaccept ? (
          <>
            <Pressable onPress={() => setOfAge(!ofAge)} accessibilityRole="checkbox" accessibilityState={{ checked: ofAge }} aria-checked={ofAge} style={styles.check}>
              <Text style={styles.box}>{ofAge ? '☑' : '☐'}</Text>
              <Text style={styles.checkText}>I am {config.minimum_age} or older.</Text>
            </Pressable>
            <Pressable onPress={() => setAgreed(!agreed)} accessibilityRole="checkbox" accessibilityState={{ checked: agreed }} aria-checked={agreed} style={styles.check}>
              <Text style={styles.box}>{agreed ? '☑' : '☐'}</Text>
              <Text style={styles.checkText}>
                I agree to the{' '}
                <Text style={styles.link} onPress={() => Linking.openURL(config.terms_url)}>
                  Terms
                </Text>{' '}
                and the{' '}
                <Text style={styles.link} onPress={() => Linking.openURL(config.privacy_url)}>
                  Privacy Policy
                </Text>
                .
              </Text>
            </Pressable>
            <Button
              label={reaccept ? 'Accept and continue' : working ? 'Opening Google…' : 'Continue with Google'}
              kind="primary"
              onPress={signIn}
              disabled={working || !ofAge || !agreed}
            />
          </>
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
  check: { flexDirection: 'row', alignItems: 'flex-start', gap: space.sm },
  box: { fontSize: 20, lineHeight: 24, color: color.ink },
  checkText: { flex: 1, fontSize: 15, lineHeight: 22, color: color.ink },
  link: { color: color.accent, fontWeight: '700' },
  error: { fontSize: 14, color: color.warn },
});
