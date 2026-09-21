import * as SecureStore from 'expo-secure-store';
import { Platform } from 'react-native';

/**
 * The session token. On phones it lives in the platform's secure storage (Keychain /
 * Keystore). In a browser it lives in sessionStorage: gone when the tab closes, and never
 * in localStorage, where it would outlive the visit. Google's own tokens are never here at
 * all: they stay on the server.
 */
const KEY = 'pwm.session';
let cached: string | null | undefined;

export async function getToken(): Promise<string | null> {
  if (cached !== undefined) return cached;
  try {
    cached =
      Platform.OS === 'web'
        ? (globalThis.sessionStorage?.getItem(KEY) ?? null)
        : await SecureStore.getItemAsync(KEY);
  } catch {
    cached = null;
  }
  return cached;
}

export async function setToken(token: string): Promise<void> {
  cached = token;
  if (Platform.OS === 'web') globalThis.sessionStorage?.setItem(KEY, token);
  else await SecureStore.setItemAsync(KEY, token);
}

export async function clearToken(): Promise<void> {
  cached = null;
  try {
    if (Platform.OS === 'web') globalThis.sessionStorage?.removeItem(KEY);
    else await SecureStore.deleteItemAsync(KEY);
  } catch {
    // Nothing useful to do: the in-memory copy is already gone.
  }
}
