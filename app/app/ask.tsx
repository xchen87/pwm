import { useRouter } from 'expo-router';
import { useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';

import { type AnswerView, askWorld } from '../src/api/client';
import { Button } from '../src/components/Button';
import { color, space } from '../src/theme';

const SUGGESTIONS = [
  'What did I promise Tom?',
  'What deadlines do I have coming up?',
  'What is the kitchen quote now?',
  'Why did we choose Blake Renovations?',
  'What is Dana’s new phone number?',
];

export default function Ask() {
  const router = useRouter();
  const [question, setQuestion] = useState('');
  const [asked, setAsked] = useState('');
  const [answer, setAnswer] = useState<AnswerView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const ask = async (text: string) => {
    const trimmed = text.trim();
    if (trimmed.length < 2) return;
    setBusy(true);
    setError(null);
    setQuestion(trimmed);
    try {
      setAnswer(await askWorld(trimmed));
      setAsked(trimmed);
    } catch {
      setError('Can’t reach your world right now.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
      <TextInput
        style={styles.input}
        value={question}
        onChangeText={setQuestion}
        placeholder="Ask about people, promises, dates, decisions…"
        placeholderTextColor={color.muted}
        returnKeyType="search"
        onSubmitEditing={() => ask(question)}
        autoFocus
      />
      <Button label={busy ? 'Looking…' : 'Ask'} kind="primary" onPress={() => ask(question)} disabled={busy} />
      {error && <Text style={styles.error}>{error}</Text>}

      {answer ? (
        <View style={styles.answer}>
          <Text style={styles.asked}>{asked}</Text>
          <Text style={styles.text}>{answer.text}</Text>
          {answer.caveat && <Text style={styles.caveat}>{answer.caveat}</Text>}
          {answer.cited.length > 0 && <Text style={styles.section}>Where this comes from</Text>}
          {answer.cited.map((fact) => (
            <Pressable
              key={fact.assertion_id}
              style={styles.cite}
              accessibilityRole="link"
              onPress={() => router.push({ pathname: '/assertion/[id]', params: { id: fact.assertion_id } })}
            >
              <Text style={styles.quote}>“{fact.evidence_quote}”</Text>
              <Text style={styles.source}>
                {fact.source_label} · {fact.is_fact ? 'confirmed by you' : 'not confirmed'}
              </Text>
            </Pressable>
          ))}
        </View>
      ) : (
        <View style={styles.answer}>
          <Text style={styles.section}>Try asking</Text>
          {SUGGESTIONS.map((suggestion) => (
            <Pressable key={suggestion} onPress={() => ask(suggestion)} accessibilityRole="button">
              <Text style={styles.suggestion}>{suggestion}</Text>
            </Pressable>
          ))}
        </View>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  content: { padding: space.lg, paddingBottom: 64, maxWidth: 640, width: '100%', alignSelf: 'center', gap: space.md },
  input: {
    fontSize: 17,
    color: color.ink,
    backgroundColor: color.card,
    borderWidth: 1,
    borderColor: color.line,
    borderRadius: 12,
    padding: space.lg,
  },
  answer: { marginTop: space.md },
  asked: { fontSize: 14, color: color.muted, marginBottom: space.sm },
  text: { fontSize: 17, lineHeight: 25, color: color.ink },
  caveat: { fontSize: 14, lineHeight: 20, color: color.muted, marginTop: space.md },
  section: { fontSize: 13, fontWeight: '700', letterSpacing: 0.3, textTransform: 'uppercase', color: color.muted, marginTop: space.xl },
  cite: { paddingVertical: space.md, borderBottomWidth: 1, borderBottomColor: color.line },
  quote: { fontSize: 15, lineHeight: 21, color: color.ink },
  source: { fontSize: 13, color: color.muted, marginTop: space.xs },
  suggestion: { fontSize: 16, color: color.accent, paddingVertical: space.md, fontWeight: '600' },
  error: { fontSize: 14, color: color.warn },
});
