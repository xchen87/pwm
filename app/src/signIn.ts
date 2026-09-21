import * as Linking from 'expo-linking';
import * as WebBrowser from 'expo-web-browser';
import { Platform } from 'react-native';

import { API_URL, exchangeLoginCode } from './api/client';
import { setToken } from './session';

/** Where Google's sign-in should send the browser back to: this app, on this platform. */
export const appRedirect = () => Linking.createURL('auth');

export async function finishSignIn(code: string): Promise<void> {
  const session = await exchangeLoginCode(code);
  await setToken(session.token);
}

/**
 * Sign in with Google through the system browser: never an embedded web view, which Google
 * rejects and which would teach people to type their Google password into our app.
 * Returns true when signed in. On the web the page navigates away instead, and the
 * /auth route finishes the job when Google sends the browser back.
 */
export async function signInWithGoogle(): Promise<boolean> {
  const redirect = appRedirect();
  const start = `${API_URL}/auth/google/start?redirect=${encodeURIComponent(redirect)}`;
  if (Platform.OS === 'web') {
    globalThis.location.assign(start);
    return false;
  }
  const result = await WebBrowser.openAuthSessionAsync(start, redirect);
  if (result.type !== 'success') return false;
  const code = Linking.parse(result.url).queryParams?.code;
  if (typeof code !== 'string') return false;
  await finishSignIn(code);
  return true;
}
