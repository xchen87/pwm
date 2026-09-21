import { useRouter } from 'expo-router';
import { useState } from 'react';
import { ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';

import { rememberThis } from '../src/api/client';
import { Button } from '../src/components/Button';
import { color, space } from '../src/theme';

export default function Remember() {
  const router = useRouter();
  const [text, setText] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const save = async () => {
    setSaving(true);
    try {
      await rememberThis(text.trim());
      router.back();
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : 'That didn’t save. Try again.');
      setSaving(false);
    }
  };

  return (
    <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
      <Text style={styles.hint}>
        I’ll keep your words exactly as you write them. If I spot a date or a promise in them, I’ll ask before
        tracking it.
      </Text>
      <TextInput
        style={styles.input}
        value={text}
        onChangeText={setText}
        placeholder="e.g. The spare key is with Marguerite next door."
        placeholderTextColor={color.muted}
        multiline
        autoFocus
      />
      {error && <Text style={styles.error}>{error}</Text>}
      <View style={styles.actions}>
        <Button label="Remember" kind="primary" onPress={save} disabled={saving || text.trim().length < 2} />
        <Button label="Cancel" onPress={() => router.back()} />
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  content: { padding: space.lg, maxWidth: 640, width: '100%', alignSelf: 'center' },
  hint: { fontSize: 14, lineHeight: 20, color: color.muted },
  input: {
    fontSize: 17,
    lineHeight: 24,
    color: color.ink,
    backgroundColor: color.card,
    borderWidth: 1,
    borderColor: color.line,
    borderRadius: 12,
    padding: space.lg,
    marginTop: space.lg,
    minHeight: 120,
    textAlignVertical: 'top',
  },
  error: { fontSize: 14, color: color.warn, marginTop: space.md },
  actions: { flexDirection: 'row', gap: space.sm, marginTop: space.xl },
});
