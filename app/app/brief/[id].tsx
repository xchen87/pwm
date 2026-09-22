import { useLocalSearchParams, useRouter } from 'expo-router';
import { useEffect } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { recordEvent } from '../../src/api/client';
import { color } from '../../src/theme';

/** Where a notification's deep link (pwm://brief/<id>) lands. The brief screen shows the
 * latest brief, which is the one that was announced; the tap itself is counted. */
export default function BriefFromNotification() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  useEffect(() => {
    void recordEvent('notification_opened', id);
    router.replace('/brief');
  }, [id, router]);
  return (
    <View style={styles.screen}>
      <Text style={styles.text}>Opening your brief…</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: color.ground },
  text: { fontSize: 16, color: color.muted },
});
