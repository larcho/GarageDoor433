import { useState } from 'react';
import { Alert } from 'react-native';

import {
  BottomSheet,
  Button,
  Form,
  Group,
  LabeledContent,
  Picker,
  ProgressView,
  Section,
  Text,
  TextField,
  VStack,
} from '@expo/ui/swift-ui';
import {
  buttonStyle,
  controlSize,
  disabled,
  multilineTextAlignment,
  padding,
  presentationDetents,
  presentationDragIndicator,
  scaleEffect,
  tint,
} from '@expo/ui/swift-ui/modifiers';

import {
  isConnected,
  type RecordingResult,
  recordMultiPress,
  saveSignal,
} from '@/services/device-service';

type Step = 'idle' | 'recording' | 'captured' | 'saving';

const SLOT_OPTIONS = ['1', '2', '3', '4', '5'];

type RecordSheetProps = {
  isPresented: boolean;
  onIsPresentedChange: (isPresented: boolean) => void;
  onSaved: () => void;
};

export function RecordSheet({ isPresented, onIsPresentedChange, onSaved }: RecordSheetProps) {
  const [step, setStep] = useState<Step>('idle');
  const [result, setResult] = useState<RecordingResult | null>(null);
  const [name, setName] = useState('');
  const [slotIndex, setSlotIndex] = useState(0);
  const [pressProgress, setPressProgress] = useState({ captured: 0, target: 3 });

  const reset = () => {
    setStep('idle');
    setResult(null);
    setName('');
    setSlotIndex(0);
    setPressProgress({ captured: 0, target: 3 });
  };

  const handleClose = (presented: boolean) => {
    if (!presented) {
      reset();
    }
    onIsPresentedChange(presented);
  };

  const handleStartRecording = async () => {
    if (!isConnected()) {
      Alert.alert('Not Connected', 'Connect to the device before recording a signal.');
      return;
    }
    setStep('recording');
    setPressProgress({ captured: 0, target: 3 });
    try {
      const captured = await recordMultiPress(3, (captured, target) => {
        setPressProgress({ captured, target });
      });
      setResult(captured);
      setStep('captured');
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      Alert.alert('Recording Failed', message);
      setStep('idle');
    }
  };

  const handleSave = async () => {
    if (!name.trim()) {
      Alert.alert('Name Required', 'Please enter a name for this signal.');
      return;
    }
    if (!result) return;

    setStep('saving');
    try {
      const slotNumber = slotIndex + 1;
      const res = await saveSignal(slotNumber, name.trim(), result);
      if (res.success) {
        onIsPresentedChange(false);
        reset();
        onSaved();
      } else {
        Alert.alert('Save Failed', `Could not save to slot ${slotIndex + 1}.`);
        setStep('captured');
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      Alert.alert('Save Failed', message);
      setStep('captured');
    }
  };

  return (
    <BottomSheet isPresented={isPresented} onIsPresentedChange={handleClose}>
      <Group modifiers={[presentationDetents(['medium']), presentationDragIndicator('visible')]}>
        {step === 'idle' && (
          <VStack alignment="center" spacing={24} modifiers={[padding({ all: 24 })]}>
            <Button
              onPress={handleStartRecording}
              label="Start Recording"
              systemImage="record.circle"
              modifiers={[buttonStyle('borderedProminent'), controlSize('large'), tint('#ff3b30')]}
            />
            <Text color="secondary" size={16} modifiers={[multilineTextAlignment('center')]}>
              Press the button below, then activate your remote within 5 seconds.
            </Text>
          </VStack>
        )}

        {step === 'recording' && (
          <VStack alignment="center" spacing={24} modifiers={[padding({ top: 40 })]}>
            <ProgressView modifiers={[scaleEffect(2)]} />
            <VStack alignment="center" spacing={8}>
              <Text weight="bold" size={24}>
                {pressProgress.captured === 0
                  ? 'Press your remote'
                  : pressProgress.captured < pressProgress.target
                    ? `Got ${pressProgress.captured} of ${pressProgress.target}`
                    : 'Processing...'}
              </Text>
              <Text color="secondary" size={16} modifiers={[multilineTextAlignment('center')]}>
                {pressProgress.captured < pressProgress.target
                  ? `Press ${pressProgress.captured + 1} of ${pressProgress.target}`
                  : 'Averaging signal...'}
              </Text>
            </VStack>
          </VStack>
        )}

        {(step === 'captured' || step === 'saving') && result && (
          <>
            <Form modifiers={[padding({ top: 16 })]}>
              <Section title="Signal Captured">
                <LabeledContent label="Pulses">
                  <Text>{String(result.pulseCount)}</Text>
                </LabeledContent>
                <LabeledContent label="Protocol">
                  <Text>{result.protocol}</Text>
                </LabeledContent>
              </Section>

              <Section title="Save">
                <TextField placeholder="Signal Name" onChangeText={setName} defaultValue={name} />
                <Picker
                  label="Slot"
                  options={SLOT_OPTIONS}
                  selectedIndex={slotIndex}
                  variant="segmented"
                  onOptionSelected={(e) => setSlotIndex(e.nativeEvent.index)}
                />
              </Section>
            </Form>
            <Button
              onPress={handleSave}
              label={step === 'saving' ? 'Saving…' : 'Save Signal'}
              modifiers={[
                buttonStyle('borderedProminent'),
                controlSize('large'),
                disabled(step === 'saving'),
                padding({ horizontal: 20, bottom: 16 }),
              ]}
            />
          </>
        )}
      </Group>
    </BottomSheet>
  );
}
