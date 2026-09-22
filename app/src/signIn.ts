import * as Crypto from 'expo-crypto';
import * as Linking from 'expo-linking';
import * as SecureStore from 'expo-secure-store';
import * as WebBrowser from 'expo-web-browser';
import { Platform } from 'react-native';

import { API_URL, exchangeLoginCode, getAuthConfig } from './api/client';
import { enablePush } from './push';
import { setToken } from './session';

const VERIFIER_KEY = 'pwm.signin.verifier';
const CONSENT_KEY = 'pwm.signin.consent'; // the terms version the person accepted before starting

/** Where Google's sign-in should send the browser back to: this app, on this platform. */
export const appRedirect = () => Linking.createURL('auth');

const hex = (bytes: Uint8Array) => Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');

async function keep(verifier: string, termsVersion: string): Promise<void> {
  if (Platform.OS === 'web') {
    globalThis.sessionStorage?.setItem(VERIFIER_KEY, verifier);
    globalThis.sessionStorage?.setItem(CONSENT_KEY, termsVersion);
  } else {
    await SecureStore.setItemAsync(VERIFIER_KEY, verifier);
    await SecureStore.setItemAsync(CONSENT_KEY, termsVersion);
  }
}

async function takeConsent(): Promise<string | null> {
  if (Platform.OS === 'web') {
    const version = globalThis.sessionStorage?.getItem(CONSENT_KEY) ?? null;
    globalThis.sessionStorage?.removeItem(CONSENT_KEY);
    return version;
  }
  const version = await SecureStore.getItemAsync(CONSENT_KEY);
  await SecureStore.deleteItemAsync(CONSENT_KEY);
  return version;
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
      const termsVersion = await takeConsent();
      if (!verifier || !termsVersion) throw new Error('This sign-in was not started here.');
      const session = await exchangeLoginCode(code, verifier, termsVersion);
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
export type Consent = { termsVersion: string; ageConfirmed: true };

/** For a person who already has an account here (reconnecting Google after the grant ended,
 * or the local development identity linking its Google account): they accepted the current
 * terms when they signed up, and the server checks that again at redemption. */
export async function reconnectGoogle(): Promise<boolean> {
  const config = await getAuthConfig();
  return signInWithGoogle({ termsVersion: config.terms_version, ageConfirmed: true });
}

export async function signInWithGoogle(consent: Consent): Promise<boolean> {
  const verifier = hex(await Crypto.getRandomBytesAsync(32));
  const challenge = await Crypto.digestStringAsync(Crypto.CryptoDigestAlgorithm.SHA256, verifier);
  await keep(verifier, consent.termsVersion);

  const redirect = appRedirect();
  const start =
    `${API_URL}/auth/google/start?redirect=${encodeURIComponent(redirect)}` + `&challenge=${challenge}`;
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
