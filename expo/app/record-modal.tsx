import { useRouter } from 'expo-router';
import { useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Pressable,
  StyleSheet,
  TextInput,
  View,
} from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { IconSymbol } from '@/components/ui/icon-symbol';
import { Colors } from '@/constants/theme';
import { useColorScheme } from '@/hooks/use-color-scheme';
import {
  saveSignal,
  startRecording,
  stopRecording,
  type RecordingResult,
} from '@/services/device-service';

type Step = 'idle' | 'recording' | 'captured' | 'saving';

export default function RecordModal() {
  const [step, setStep] = useState<Step>('idle');
  const [result, setResult] = useState<RecordingResult | null>(null);
  const [name, setName] = useState('');
  const [slotNumber, setSlotNumber] = useState(1);
  const colorScheme = useColorScheme() ?? 'light';
  const router = useRouter();

  const tint = Colors[colorScheme].tint;
  const cardBg = colorScheme === 'dark' ? '#1e2023' : '#f2f2f7';
  const inputBg = colorScheme === 'dark' ? '#2c2c2e' : '#fff';
  const textColor = Colors[colorScheme].text;

  const handleStartRecording = async () => {
    setStep('recording');
    try {
      await startRecording();
      // Device records for up to 5s; send stop after a delay to retrieve the capture
      await new Promise((r) => setTimeout(r, 5000));
      const captured = await stopRecording();
      setResult(captured);
      setStep('captured');
    } catch {
      Alert.alert('Error', 'Recording failed');
      setStep('idle');
    }
  };

  const handleSave = async () => {
    if (!name.trim()) {
      Alert.alert('Name Required', 'Please enter a name for this signal');
      return;
    }
    if (!result) return;

    setStep('saving');
    try {
      const res = await saveSignal(slotNumber, name.trim(), result);
      if (res.success) {
        router.back();
      } else {
        Alert.alert('Error', 'Failed to save signal');
        setStep('captured');
      }
    } catch {
      Alert.alert('Error', 'Could not save signal');
      setStep('captured');
    }
  };

  return (
    <ThemedView style={styles.container}>
      {step === 'idle' && (
        <View style={styles.center}>
          <ThemedText style={styles.instruction}>
            Press the button below, then activate your remote within 5 seconds.
          </ThemedText>
          <Pressable
            style={({ pressed }) => [
              styles.bigButton,
              { backgroundColor: '#ff3b30', opacity: pressed ? 0.8 : 1 },
            ]}
            onPress={handleStartRecording}
          >
            <IconSymbol name="record.circle" size={48} color="#fff" />
            <ThemedText style={styles.bigButtonText}>Start Recording</ThemedText>
          </Pressable>
        </View>
      )}

      {step === 'recording' && (
        <View style={styles.center}>
          <ActivityIndicator size="large" color="#ff3b30" />
          <ThemedText type="subtitle" style={styles.recordingText}>
            Recording...
          </ThemedText>
          <ThemedText style={styles.instruction}>
            Activate your remote now
          </ThemedText>
        </View>
      )}

      {(step === 'captured' || step === 'saving') && result && (
        <View style={styles.form}>
          <ThemedText type="subtitle">Signal Captured</ThemedText>

          <View style={[styles.resultCard, { backgroundColor: cardBg }]}>
            <ResultRow label="Pulses" value={String(result.pulseCount)} />
            <ResultRow label="Protocol" value={result.protocol} />
          </View>

          <ThemedText style={styles.label}>Signal Name</ThemedText>
          <TextInput
            style={[styles.input, { backgroundColor: inputBg, color: textColor }]}
            placeholder="e.g. Garage Main"
            placeholderTextColor={colorScheme === 'dark' ? '#666' : '#999'}
            value={name}
            onChangeText={setName}
            autoFocus
          />

          <ThemedText style={styles.label}>Slot Number</ThemedText>
          <View style={styles.slotPicker}>
            {[1, 2, 3, 4, 5].map((n) => (
              <Pressable
                key={n}
                style={[
                  styles.slotChip,
                  {
                    backgroundColor: n === slotNumber ? tint : cardBg,
                  },
                ]}
                onPress={() => setSlotNumber(n)}
              >
                <ThemedText
                  style={[
                    styles.slotChipText,
                    { color: n === slotNumber ? '#fff' : textColor },
                  ]}
                >
                  {n}
                </ThemedText>
              </Pressable>
            ))}
          </View>

          <Pressable
            style={({ pressed }) => [
              styles.saveButton,
              { backgroundColor: tint, opacity: pressed ? 0.8 : 1 },
            ]}
            onPress={handleSave}
            disabled={step === 'saving'}
          >
            {step === 'saving' ? (
              <ActivityIndicator color="#fff" />
            ) : (
              <ThemedText style={styles.saveButtonText}>Save Signal</ThemedText>
            )}
          </Pressable>
        </View>
      )}
    </ThemedView>
  );
}

function ResultRow({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.resultRow}>
      <ThemedText style={styles.resultLabel}>{label}</ThemedText>
      <ThemedText type="defaultSemiBold">{value}</ThemedText>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    padding: 20,
  },
  center: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 20,
  },
  instruction: {
    fontSize: 16,
    textAlign: 'center',
    opacity: 0.6,
    paddingHorizontal: 32,
  },
  bigButton: {
    width: 160,
    height: 160,
    borderRadius: 80,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
  },
  bigButtonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
  recordingText: {
    color: '#ff3b30',
  },
  form: {
    flex: 1,
    gap: 12,
    paddingTop: 12,
  },
  resultCard: {
    borderRadius: 12,
    padding: 4,
  },
  resultRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingVertical: 12,
  },
  resultLabel: {
    opacity: 0.6,
  },
  label: {
    fontSize: 14,
    fontWeight: '600',
    marginTop: 4,
  },
  input: {
    borderRadius: 10,
    padding: 14,
    fontSize: 16,
  },
  slotPicker: {
    flexDirection: 'row',
    gap: 10,
  },
  slotChip: {
    width: 48,
    height: 48,
    borderRadius: 24,
    alignItems: 'center',
    justifyContent: 'center',
  },
  slotChipText: {
    fontSize: 18,
    fontWeight: '600',
  },
  saveButton: {
    borderRadius: 12,
    padding: 16,
    alignItems: 'center',
    marginTop: 12,
  },
  saveButtonText: {
    color: '#fff',
    fontSize: 17,
    fontWeight: '600',
  },
});
