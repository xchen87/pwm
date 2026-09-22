import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { useEffect, useState } from 'react';
import { AppState, Pressable, StyleSheet, Text, View } from 'react-native';

import { unlock } from '../src/lock';

import { color } from '../src/theme';

export default function RootLayout() {
  // Locked until the lock (if any) is passed; re-locked whenever the app comes back to the front.
  const [locked, setLocked] = useState(true);
  useEffect(() => {
    const tryUnlock = () => unlock().then((ok) => setLocked(!ok), () => setLocked(true));
    void tryUnlock();
    const subscription = AppState.addEventListener('change', (state) => {
      if (state === 'active') void tryUnlock();
      if (state === 'background') setLocked(true);
    });
    return () => subscription.remove();
  }, []);

  if (locked) {
    return (
      <View style={styles.lock}>
        <Text style={styles.lockTitle}>Your World</Text>
        <Pressable onPress={() => unlock().then((ok) => setLocked(!ok))} accessibilityRole="button">
          <Text style={styles.unlock}>Unlock</Text>
        </Pressable>
      </View>
    );
  }

  return (
    <>
      <StatusBar style="auto" />
      <Stack
        screenOptions={{
          headerStyle: { backgroundColor: color.ground },
          headerShadowVisible: false,
          headerTintColor: color.ink,
          contentStyle: { backgroundColor: color.ground },
        }}
      >
        <Stack.Screen name="index" options={{ headerShown: false }} />
        <Stack.Screen name="attention" options={{ title: 'Needs attention' }} />
        <Stack.Screen name="brief/index" options={{ title: 'World Brief' }} />
        <Stack.Screen name="brief/[id]" options={{ headerShown: false }} />
        <Stack.Screen name="ask" options={{ title: 'Ask your world' }} />
        <Stack.Screen name="auth" options={{ headerShown: false }} />
        <Stack.Screen name="settings" options={{ title: 'Connections and your data' }} />
        <Stack.Screen name="remember" options={{ title: 'Remember this', presentation: 'modal' }} />
        <Stack.Screen name="assertion/[id]" options={{ title: 'Where this came from' }} />
        <Stack.Screen name="edit/[id]" options={{ title: 'Edit', presentation: 'modal' }} />
      </Stack>
    </>
  );
}

const styles = StyleSheet.create({
  lock: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 24, backgroundColor: color.ground },
  lockTitle: { fontSize: 30, fontWeight: '700', color: color.ink },
  unlock: { fontSize: 17, fontWeight: '700', color: color.accent, padding: 12 },
});
