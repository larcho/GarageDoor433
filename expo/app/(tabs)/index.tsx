import { useFocusEffect, useRouter } from 'expo-router';
import { useCallback, useState } from 'react';
import { Alert, Pressable, StyleSheet, View } from 'react-native';

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
  CircularProgress,
  ContentUnavailableView,
} from '@expo/ui/swift-ui';
import { padding } from '@expo/ui/swift-ui/modifiers';

import { IconSymbol } from '@/components/ui/icon-symbol';
import { Colors } from '@/constants/theme';
import { useColorScheme } from '@/hooks/use-color-scheme';
import { getSlots, playSlot, type Slot } from '@/services/device-service';

export default function SlotsScreen() {
  const [slots, setSlots] = useState<Slot[]>([]);
  const [loading, setLoading] = useState(true);
  const [playingSlot, setPlayingSlot] = useState<number | null>(null);
  const colorScheme = useColorScheme() ?? 'light';
  const router = useRouter();

  const tint = Colors[colorScheme].tint;

  useFocusEffect(
    useCallback(() => {
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
    }, [])
  );

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
    <View style={styles.container}>
      <Host style={{ flex: 1 }} colorScheme={colorScheme}>
        <VStack modifiers={[padding({ top: 16, leading: 20, trailing: 20 })]}>
          <Text size={34} weight="bold">
            Slots
          </Text>
        </VStack>

        {loading ? (
          <VStack alignment="center" modifiers={[padding({ top: 80 })]}>
            <CircularProgress />
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
                      <CircularProgress />
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

      <Pressable
        style={({ pressed }) => [
          styles.fab,
          { backgroundColor: tint, opacity: pressed ? 0.8 : 1 },
        ]}
        onPress={() => router.push('/record-modal')}
      >
        <IconSymbol name="plus" size={28} color="#fff" />
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  fab: {
    position: 'absolute',
    right: 20,
    bottom: 16,
    width: 56,
    height: 56,
    borderRadius: 28,
    alignItems: 'center',
    justifyContent: 'center',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 4,
    elevation: 6,
  },
});
