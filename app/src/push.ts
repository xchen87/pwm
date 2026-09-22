import Constants from 'expo-constants';
import * as Device from 'expo-device';
import * as Notifications from 'expo-notifications';
import * as SecureStore from 'expo-secure-store';
import { Platform } from 'react-native';

import { registerDevice, unregisterDevice } from './api/client';

/**
 * Push, on a real phone only. The notification a phone receives is a generic title and a
 * deep link; everything that matters is fetched by the app after it opens. Simulators,
 * emulators and the web have no push, and nothing here runs for them.
 *
 * The token is kept on the device so that a sign-out after a restart can still tell the
 * server to stop addressing this phone.
 */
const TOKEN_KEY = 'pwm.push.token';

const platform = () => (Platform.OS === 'ios' ? 'ios' : 'android') as 'ios' | 'android';
const onPhone = () => Platform.OS !== 'web' && Device.isDevice;

/** Register for push if the phone allows it. `ask` controls whether to prompt when undecided. */
export async function enablePush(ask: boolean): Promise<boolean> {
  if (!onPhone()) return false;
  const projectId = Constants.expoConfig?.extra?.eas?.projectId;
  if (typeof projectId !== 'string') return false; // no EAS project yet: push cannot be addressed
  let { granted, canAskAgain } = await Notifications.getPermissionsAsync();
  if (!granted && ask && canAskAgain) granted = (await Notifications.requestPermissionsAsync()).granted;
  if (!granted) return false;
  if (Platform.OS === 'android') {
    await Notifications.setNotificationChannelAsync('default', {
      name: 'Your World',
      importance: Notifications.AndroidImportance.DEFAULT,
    });
  }
  const token = (await Notifications.getExpoPushTokenAsync({ projectId })).data;
  await registerDevice(token, platform());
  await SecureStore.setItemAsync(TOKEN_KEY, token);
  return true;
}

/** On sign-out: this phone must stop receiving this account's notifications. */
export async function disablePush(): Promise<void> {
  if (!onPhone()) return;
  const token = await SecureStore.getItemAsync(TOKEN_KEY).catch(() => null);
  if (!token) return;
  await unregisterDevice(token, platform()).catch(() => undefined);
  await SecureStore.deleteItemAsync(TOKEN_KEY).catch(() => undefined);
}

/** The app path a notification asks for, or null. Only our own scheme is honoured. */
export function pathFromNotification(response: Notifications.NotificationResponse | null): string | null {
  const url = response?.notification.request.content.data?.url;
  if (typeof url !== 'string' || !url.startsWith('pwm://')) return null;
  return '/' + url.slice('pwm://'.length);
}

if (Platform.OS !== 'web') {
  Notifications.setNotificationHandler({
    handleNotification: async () => ({
      shouldShowBanner: true,
      shouldShowList: true,
      shouldPlaySound: false,
      shouldSetBadge: false,
    }),
  });
}
