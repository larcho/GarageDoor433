import { useFocusEffect, useRouter } from 'expo-router';
import { useCallback, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Pressable,
  ScrollView,
  StyleSheet,
  View,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
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
  const insets = useSafeAreaInsets();

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

  const tint = Colors[colorScheme].tint;
  const cardBg = colorScheme === 'dark' ? '#1e2023' : '#f2f2f7';

  return (
    <ThemedView style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + 8 }]}>
        <ThemedText type="title">Slots</ThemedText>
      </View>

      {loading ? (
        <View style={styles.center}>
          <ActivityIndicator size="large" color={tint} />
        </View>
      ) : slots.length === 0 ? (
        <View style={styles.center}>
          <ThemedText style={styles.emptyText}>No saved signals</ThemedText>
          <ThemedText style={styles.emptySubtext}>
            Tap + to record a new signal
          </ThemedText>
        </View>
      ) : (
        <ScrollView contentContainerStyle={styles.grid}>
          {slots.map((slot) => (
            <Pressable
              key={slot.slot}
              style={({ pressed }) => [
                styles.card,
                { backgroundColor: cardBg, opacity: pressed ? 0.7 : 1 },
              ]}
              onPress={() => handlePlay(slot)}
              disabled={playingSlot !== null}
            >
              {playingSlot === slot.slot ? (
                <ActivityIndicator size="large" color={tint} />
              ) : (
                <IconSymbol name="play.fill" size={40} color={tint} />
              )}
              <ThemedText type="defaultSemiBold" style={styles.slotName}>
                {slot.name}
              </ThemedText>
              <ThemedText style={styles.slotDetail}>
                Slot {slot.slot} · {slot.protocol} · {slot.pulseCount} pulses
              </ThemedText>
            </Pressable>
          ))}
        </ScrollView>
      )}

      <Pressable
        style={({ pressed }) => [
          styles.fab,
          { backgroundColor: tint, opacity: pressed ? 0.8 : 1, bottom: 16 },
        ]}
        onPress={() => router.push('/record-modal')}
      >
        <IconSymbol name="plus" size={28} color="#fff" />
      </Pressable>
    </ThemedView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  header: {
    paddingHorizontal: 20,
    paddingBottom: 12,
  },
  center: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  emptyText: {
    fontSize: 18,
    opacity: 0.6,
  },
  emptySubtext: {
    fontSize: 14,
    opacity: 0.4,
    marginTop: 4,
  },
  grid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    padding: 12,
    gap: 12,
  },
  card: {
    width: '47%',
    aspectRatio: 1,
    borderRadius: 16,
    padding: 16,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
  },
  slotName: {
    textAlign: 'center',
  },
  slotDetail: {
    fontSize: 12,
    opacity: 0.5,
    textAlign: 'center',
  },
  fab: {
    position: 'absolute',
    right: 20,
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
