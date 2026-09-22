import * as LocalAuthentication from 'expo-local-authentication';
import * as SecureStore from 'expo-secure-store';
import { Platform } from 'react-native';

/**
 * Optional app lock: when on, the phone's biometrics or passcode are required each time the
 * app comes to the foreground. Off by default. Not offered on the web, where there is no
 * platform authenticator to ask.
 */
const KEY = 'pwm.lock';

export async function lockAvailable(): Promise<boolean> {
  if (Platform.OS === 'web') return false;
  return (await LocalAuthentication.hasHardwareAsync()) && (await LocalAuthentication.isEnrolledAsync());
}

export async function lockEnabled(): Promise<boolean> {
  if (Platform.OS === 'web') return false;
  try {
    return (await SecureStore.getItemAsync(KEY)) === 'on';
  } catch {
    return false;
  }
}

export async function setLockEnabled(on: boolean): Promise<void> {
  if (on) await SecureStore.setItemAsync(KEY, 'on');
  else await SecureStore.deleteItemAsync(KEY);
}

/** True when the person in front of the phone proved it is theirs (or no lock is set). */
export async function unlock(): Promise<boolean> {
  if (!(await lockEnabled())) return true;
  const result = await LocalAuthentication.authenticateAsync({
    promptMessage: 'Unlock Your World',
    cancelLabel: 'Cancel',
  });
  return result.success;
}
