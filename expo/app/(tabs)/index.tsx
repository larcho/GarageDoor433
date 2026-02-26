import { useFocusEffect, useRouter } from 'expo-router';
import { useCallback, useState } from 'react';
import { Alert } from 'react-native';

import {
  Host,
  List,
  Section,
  HStack,
  VStack,
  Text,
  Button,
  Image,
  Spacer,
  ProgressView,
  ContentUnavailableView,
} from '@expo/ui/swift-ui';
import { padding } from '@expo/ui/swift-ui/modifiers';

import { useColorScheme } from '@/hooks/use-color-scheme';
import { Colors } from '@/constants/theme';
import { getSlots, playSlot, type Slot } from '@/services/device-service';

export default function SlotsScreen() {
  const [slots, setSlots] = useState<Slot[]>([]);
  const [loading, setLoading] = useState(true);
  const [playingSlot, setPlayingSlot] = useState<number | null>(null);
  const colorScheme = useColorScheme() ?? 'light';
  const router = useRouter();

  const tint = Colors[colorScheme].tint;

  const refreshSlots = useCallback(() => {
    let cancelled = false;
    setLoading(true);
    getSlots().then((data) => {
      if (!cancelled) {
        setSlots(data);
        setLoading(false);
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);

  useFocusEffect(refreshSlots);

  const handlePlay = async (slot: Slot) => {
    setPlayingSlot(slot.slot);
    try {
      const result = await playSlot(slot.slot);
      if (!result.success) {
        Alert.alert('Error', `Failed to play slot ${slot.slot}`);
      }
    } catch {
      Alert.alert('Error', 'Could not communicate with device');
    } finally {
      setPlayingSlot(null);
    }
  };

  return (
    <Host style={{ flex: 1, backgroundColor: colorScheme === 'dark' ? '#151718' : '#fff' }} colorScheme={colorScheme}>
      <HStack modifiers={[padding({ top: 16, leading: 20, trailing: 20, bottom: 8 })]}>
        <Text size={34} weight="bold">
          Slots
        </Text>
        <Spacer />
        <Button
          onPress={() => router.push('/record-modal')}
          systemImage="plus"
          variant="plain"
        >
          {''}
        </Button>
      </HStack>

      {loading ? (
        <VStack alignment="center" modifiers={[padding({ top: 80 })]}>
          <ProgressView />
        </VStack>
      ) : slots.length === 0 ? (
        <ContentUnavailableView
          title="No Saved Signals"
          systemImage="antenna.radiowaves.left.and.right"
          description="Tap + to record a new signal"
        />
      ) : (
        <List listStyle="insetGrouped">
          <Section>
            {slots.map((slot) => (
              <Button
                key={slot.slot}
                onPress={() => handlePlay(slot)}
                disabled={playingSlot !== null}
                variant="plain"
              >
                <HStack spacing={12}>
                  {playingSlot === slot.slot ? (
                    <ProgressView />
                  ) : (
                    <Image systemName="play.fill" size={22} color={tint} />
                  )}
                  <VStack alignment="leading" spacing={2}>
                    <Text weight="semibold">{slot.name}</Text>
                    <Text size={13} color="secondary">
                      {`Slot ${slot.slot} · ${slot.protocol} · ${slot.pulseCount} pulses`}
                    </Text>
                  </VStack>
                  <Spacer />
                </HStack>
              </Button>
            ))}
          </Section>
        </List>
      )}
    </Host>
  );
}
