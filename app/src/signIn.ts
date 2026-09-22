import * as Crypto from 'expo-crypto';
import * as Linking from 'expo-linking';
import * as SecureStore from 'expo-secure-store';
import * as WebBrowser from 'expo-web-browser';
import { Platform } from 'react-native';

import { API_URL, exchangeLoginCode, getMe } from './api/client';
import { enablePush } from './push';
import { setToken } from './session';

const VERIFIER_KEY = 'pwm.signin.verifier';

/** Where Google's sign-in should send the browser back to: this app, on this platform. */
export const appRedirect = () => Linking.createURL('auth');

const hex = (bytes: Uint8Array) => Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');

async function keep(verifier: string): Promise<void> {
  if (Platform.OS === 'web') globalThis.sessionStorage?.setItem(VERIFIER_KEY, verifier);
  else await SecureStore.setItemAsync(VERIFIER_KEY, verifier);
}

async function takeVerifier(): Promise<string | null> {
  if (Platform.OS === 'web') {
    const verifier = globalThis.sessionStorage?.getItem(VERIFIER_KEY) ?? null;
    globalThis.sessionStorage?.removeItem(VERIFIER_KEY);
    return verifier;
  }
  const verifier = await SecureStore.getItemAsync(VERIFIER_KEY);
  await SecureStore.deleteItemAsync(VERIFIER_KEY);
  return verifier;
}

/**
 * Finish a sign-in this app started. The login code in the redirect is only redeemable
 * together with the secret made in `signInWithGoogle`, so a code from a link someone sent,
 * or one intercepted by another app, is worth nothing. With no secret on hand, this app
 * did not start the sign-in, and refuses.
 */
const redeeming = new Map<string, Promise<void>>();

export function finishSignIn(code: string): Promise<void> {
  // On a phone both the auth-session result and the deep-link route deliver the same code,
  // and React may run an effect twice. They share one redemption instead of racing for it.
  let pending = redeeming.get(code);
  if (!pending) {
    pending = (async () => {
      const verifier = await takeVerifier();
      if (!verifier) throw new Error('This sign-in was not started here.');
      const session = await exchangeLoginCode(code, verifier);
      await setToken(session.token);
      // If this phone already allows notifications, it should hear about briefs from now on.
      void enablePush(false).catch(() => undefined);
    })();
    redeeming.set(code, pending);
  }
  return pending;
}

/**
 * Sign in with Google through the system browser: never an embedded web view, which Google
 * rejects and which would teach people to type their Google password into our app.
 * Returns true when signed in. On the web the page navigates away instead, and the
 * /auth route finishes the job when Google sends the browser back.
 */
/** What the person ticked before starting. Sent with the start of sign-in, so it is on
 * record before anything is read (the server refuses to start without it). */
export type Consent = { termsVersion: string; ageConfirmed: boolean };

/** For a person who already has an account here (reconnecting Google after the grant ended,
 * or the local development identity linking its Google account). They can only be here with
 * the current terms accepted: a stale account is stopped at the consent screen first, so
 * the version they last accepted is the current one. */
export async function reconnectGoogle(): Promise<boolean> {
  const me = await getMe();
  if (!me.terms_current || !me.terms_version) throw new Error('Please accept the current terms first.');
  return signInWithGoogle({ termsVersion: me.terms_version, ageConfirmed: true });
}

export async function signInWithGoogle(consent: Consent): Promise<boolean> {
  const verifier = hex(await Crypto.getRandomBytesAsync(32));
  const challenge = await Crypto.digestStringAsync(Crypto.CryptoDigestAlgorithm.SHA256, verifier);
  await keep(verifier);

  const redirect = appRedirect();
  const query = new URLSearchParams({
    redirect,
    challenge,
    terms_version: consent.termsVersion,
    age_confirmed: String(consent.ageConfirmed),
  });
  const start = `${API_URL}/auth/google/start?${query}`;
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
