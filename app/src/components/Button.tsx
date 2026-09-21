import { Pressable, StyleSheet, Text } from 'react-native';

import { color, space } from '../theme';

type Props = {
  label: string;
  onPress: () => void;
  kind?: 'primary' | 'quiet';
  disabled?: boolean;
};

export function Button({ label, onPress, kind = 'quiet', disabled = false }: Props) {
  const primary = kind === 'primary';
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      disabled={disabled}
      onPress={onPress}
      style={({ pressed }) => [
        styles.base,
        primary ? styles.primary : styles.quiet,
        (pressed || disabled) && styles.dim,
      ]}
    >
      <Text style={[styles.label, primary && styles.primaryLabel]}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  base: { paddingVertical: 10, paddingHorizontal: space.lg, borderRadius: 10, minHeight: 44, justifyContent: 'center' },
  primary: { backgroundColor: color.accent },
  quiet: { backgroundColor: color.card, borderWidth: 1, borderColor: color.line },
  dim: { opacity: 0.55 },
  label: { fontSize: 15, fontWeight: '600', color: color.ink, textAlign: 'center' },
  primaryLabel: { color: '#FFFFFF' },
});
