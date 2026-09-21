import { useLocalSearchParams, useRouter } from 'expo-router';
import { useEffect, useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { Button } from '../src/components/Button';
import { finishSignIn } from '../src/signIn';
import { color, space } from '../src/theme';

/** Where the browser lands after Google sign-in, carrying a single-use code. */
export default function AuthReturn() {
  const { code } = useLocalSearchParams<{ code?: string }>();
  const router = useRouter();
  const [rejected, setRejected] = useState(false);
  const failed = rejected || typeof code !== 'string';

  useEffect(() => {
    if (typeof code !== 'string') return;
    finishSignIn(code).then(
      () => router.replace('/'),
      () => setRejected(true),
    );
  }, [code, router]);

  return (
    <View style={styles.screen}>
      <Text style={styles.text}>{failed ? 'That sign-in didn’t complete.' : 'Signing you in…'}</Text>
      {failed && <Button label="Back" onPress={() => router.replace('/')} />}
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: space.lg, backgroundColor: color.ground },
  text: { fontSize: 17, color: color.ink },
});
