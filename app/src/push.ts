import Constants from 'expo-constants';
import * as Device from 'expo-device';
import * as Notifications from 'expo-notifications';
import { Platform } from 'react-native';

import { registerDevice, unregisterDevice } from './api/client';

/**
 * Push, on a real phone only. The notification a phone receives is a generic title and a
 * deep link; everything that matters is fetched by the app after it opens. Simulators,
 * emulators and the web have no push, and nothing here runs for them.
 */
let token: string | null = null;

const platform = () => (Platform.OS === 'ios' ? 'ios' : 'android') as 'ios' | 'android';

export async function enablePush(): Promise<boolean> {
  if (Platform.OS === 'web' || !Device.isDevice) return false;
  const projectId = Constants.expoConfig?.extra?.eas?.projectId;
  if (typeof projectId !== 'string') return false; // no EAS project yet: push cannot be addressed
  const permission = await Notifications.getPermissionsAsync();
  const granted = permission.granted || (await Notifications.requestPermissionsAsync()).granted;
  if (!granted) return false;
  if (Platform.OS === 'android') {
    await Notifications.setNotificationChannelAsync('default', {
      name: 'Your World',
      importance: Notifications.AndroidImportance.DEFAULT,
    });
  }
  token = (await Notifications.getExpoPushTokenAsync({ projectId })).data;
  await registerDevice(token, platform());
  return true;
}

/** On sign-out: this phone must stop receiving this account's notifications. */
export async function disablePush(): Promise<void> {
  if (!token) return;
  await unregisterDevice(token, platform()).catch(() => undefined);
  token = null;
}

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowBanner: true,
    shouldShowList: true,
    shouldPlaySound: false,
    shouldSetBadge: false,
  }),
});
