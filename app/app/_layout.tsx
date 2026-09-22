import * as Notifications from 'expo-notifications';
import { Stack, useRouter } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { useEffect, useState } from 'react';
import { AppState, Platform, Pressable, StyleSheet, Text, View } from 'react-native';

import { lockEnabled, unlock } from '../src/lock';
import { pathFromNotification } from '../src/push';
import { color } from '../src/theme';

export default function RootLayout() {
  const router = useRouter();
  // The lock is an overlay: the screens underneath stay mounted, so coming back from the
  // background (or from the sign-in browser) returns to where the person was.
  const [locked, setLocked] = useState(false);

  useEffect(() => {
    let active = true;
    const attempt = () =>
      unlock().then(
        (ok) => active && setLocked(!ok),
        () => active && setLocked(true),
      );
    void attempt();
    const subscription = AppState.addEventListener('change', (state) => {
      if (state === 'active') void attempt();
      if (state === 'background') void lockEnabled().then((on) => active && on && setLocked(true));
    });
    return () => {
      active = false;
      subscription.remove();
    };
  }, []);

  useEffect(() => {
    if (Platform.OS === 'web') return;
    // A tapped notification carries the path to open: on a cold start, and while running.
    const open = (response: Notifications.NotificationResponse | null) => {
      const path = pathFromNotification(response);
      if (path) router.push(path as never);
    };
    void Notifications.getLastNotificationResponseAsync().then(open, () => undefined);
    const listener = Notifications.addNotificationResponseReceivedListener(open);
    return () => listener.remove();
  }, [router]);

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
      {locked && (
        <View style={styles.lock}>
          <Text style={styles.lockTitle}>Your World</Text>
          <Pressable onPress={() => unlock().then((ok) => setLocked(!ok))} accessibilityRole="button">
            <Text style={styles.unlock}>Unlock</Text>
          </Pressable>
        </View>
      )}
    </>
  );
}

const styles = StyleSheet.create({
  lock: {
    position: 'absolute',
    top: 0,
    right: 0,
    bottom: 0,
    left: 0,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 24,
    backgroundColor: color.ground,
  },
  lockTitle: { fontSize: 30, fontWeight: '700', color: color.ink },
  unlock: { fontSize: 17, fontWeight: '700', color: color.accent, padding: 12 },
});
