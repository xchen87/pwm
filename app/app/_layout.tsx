import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';

import { color } from '../src/theme';

export default function RootLayout() {
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
        <Stack.Screen name="brief" options={{ title: 'World Brief' }} />
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
