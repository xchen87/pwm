import { useLocalSearchParams, useRouter } from 'expo-router';
import { useEffect, useState } from 'react';
import { ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';

import { correctAssertion, getAssertion } from '../../src/api/client';
import { Button } from '../../src/components/Button';
import { color, space } from '../../src/theme';

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

export default function Edit() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const [what, setWhat] = useState('');
  const [due, setDue] = useState('');
  const [quote, setQuote] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    getAssertion(id).then(
      (detail) => {
        setWhat(detail.what);
        setDue(detail.due ?? '');
        setQuote(detail.evidence_quote);
      },
      () => setError('Can’t load this right now.'),
    );
  }, [id]);

  const save = async () => {
    if (due && !ISO_DATE.test(due)) {
      setError('Write the date as YYYY-MM-DD, or leave it empty.');
      return;
    }
    setSaving(true);
    try {
      await correctAssertion(id, { what, due: due || null, clear_due: !due });
      router.dismissTo('/');
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : 'That didn’t save. Try again.');
      setSaving(false);
    }
  };

  return (
    <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
      <Text style={styles.hint}>
        Your version replaces mine and counts as confirmed. The original stays on record with its source.
      </Text>
      <Text style={styles.quote}>“{quote}”</Text>

      <Text style={styles.label}>What is the commitment?</Text>
      <TextInput style={[styles.input, styles.multiline]} value={what} onChangeText={setWhat} multiline />

      <Text style={styles.label}>Due (YYYY-MM-DD, optional)</Text>
      <TextInput
        style={styles.input}
        value={due}
        onChangeText={setDue}
        placeholder="2026-09-25"
        autoCapitalize="none"
        autoCorrect={false}
      />

      {error && <Text style={styles.error}>{error}</Text>}
      <View style={styles.actions}>
        <Button label="Save" kind="primary" onPress={save} disabled={saving || !what.trim()} />
        <Button label="Cancel" onPress={() => router.back()} />
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  content: { padding: space.lg, maxWidth: 640, width: '100%', alignSelf: 'center' },
  hint: { fontSize: 14, lineHeight: 20, color: color.muted },
  quote: {
    fontSize: 15,
    lineHeight: 21,
    color: color.ink,
    backgroundColor: color.quote,
    borderRadius: 8,
    padding: space.md,
    marginTop: space.md,
  },
  label: { fontSize: 13, fontWeight: '700', color: color.muted, marginTop: space.xl, marginBottom: space.xs },
  input: {
    fontSize: 16,
    color: color.ink,
    backgroundColor: color.card,
    borderWidth: 1,
    borderColor: color.line,
    borderRadius: 10,
    padding: space.md,
  },
  multiline: { minHeight: 88, textAlignVertical: 'top' },
  error: { fontSize: 14, color: color.warn, marginTop: space.md },
  actions: { flexDirection: 'row', gap: space.sm, marginTop: space.xl },
});
