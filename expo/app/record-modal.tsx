import { useRouter } from 'expo-router';
import { useState } from 'react';
import { Alert } from 'react-native';

import {
  Host,
  VStack,
  Text,
  Button,
  Form,
  Section,
  LabeledContent,
  TextField,
  Picker,
  ProgressView,
} from '@expo/ui/swift-ui';
import { multilineTextAlignment, padding } from '@expo/ui/swift-ui/modifiers';

import { useColorScheme } from '@/hooks/use-color-scheme';
import {
  saveSignal,
  startRecording,
  stopRecording,
  type RecordingResult,
} from '@/services/device-service';

type Step = 'idle' | 'recording' | 'captured' | 'saving';

const SLOT_OPTIONS = ['1', '2', '3', '4', '5'];

export default function RecordModal() {
  const [step, setStep] = useState<Step>('idle');
  const [result, setResult] = useState<RecordingResult | null>(null);
  const [name, setName] = useState('');
  const [slotIndex, setSlotIndex] = useState(0);
  const colorScheme = useColorScheme() ?? 'light';
  const router = useRouter();

  const handleStartRecording = async () => {
    setStep('recording');
    try {
      await startRecording();
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
      const slotNumber = slotIndex + 1;
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
    <Host style={{ flex: 1 }} colorScheme={colorScheme}>
      {step === 'idle' && (
        <VStack alignment="center" spacing={24} modifiers={[padding({ all: 24 })]}>
          <Button
            onPress={handleStartRecording}
            variant="borderedProminent"
            controlSize="large"
            color="#ff3b30"
            systemImage="record.circle"
          >
            Start Recording
          </Button>
          <Text color="secondary" size={16} modifiers={[multilineTextAlignment('center')]}>
            Press the button below, then activate your remote within 5 seconds.
          </Text>
        </VStack>
      )}

      {step === 'recording' && (
        <VStack alignment="center" spacing={20}>
          <ProgressView />
          <Text weight="bold" color="#ff3b30" size={20}>
            Recording...
          </Text>
          <Text color="secondary" size={16}>
            Activate your remote now
          </Text>
        </VStack>
      )}

      {(step === 'captured' || step === 'saving') && result && (
        <Form>
          <Section title="Signal Captured">
            <LabeledContent label="Pulses">
              <Text>{String(result.pulseCount)}</Text>
            </LabeledContent>
            <LabeledContent label="Protocol">
              <Text>{result.protocol}</Text>
            </LabeledContent>
          </Section>

          <Section title="Save">
            <TextField
              placeholder="Signal Name"
              onChangeText={setName}
              defaultValue={name}
            />
            <Picker
              label="Slot"
              options={SLOT_OPTIONS}
              selectedIndex={slotIndex}
              variant="segmented"
              onOptionSelected={(e) => setSlotIndex(e.nativeEvent.index)}
            />
            <Button
              onPress={handleSave}
              variant="borderedProminent"
              controlSize="large"
              disabled={step === 'saving'}
            >
              {step === 'saving' ? 'Saving…' : 'Save Signal'}
            </Button>
          </Section>
        </Form>
      )}
    </Host>
  );
}
