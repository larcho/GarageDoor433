import { useEffect, useState } from 'react';
import {
  ActionSheetIOS,
  ActivityIndicator,
  Alert,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import { router, Stack, useLocalSearchParams } from 'expo-router';
import { Button, Host, Spacer, VStack } from '@expo/ui/swift-ui';
import {
  buttonStyle,
  containerRelativeFrame,
  controlSize,
  disabled,
  padding,
  tint as swiftTint,
} from '@expo/ui/swift-ui/modifiers';

import { IconSymbol } from '@/components/ui/icon-symbol';
import { Colors } from '@/constants/theme';
import { useColorScheme } from '@/hooks/use-color-scheme';
import { deleteSlot, getSignalData, playSlot, type SignalData } from '@/services/device-service';

// Waveform rendering constants
const HIGH_HEIGHT = 44;
const LOW_HEIGHT = 3;
const MIN_SEGMENT_PX = 3;
const MAX_SEGMENT_PX = 100;

function clamp(val: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, val));
}

function computeScale(pulses: [number, number][]): number {
  const durations: number[] = [];
  for (const [h, l] of pulses) {
    if (h > 0 && h < 5000) durations.push(h);
    if (l > 0 && l < 5000) durations.push(l);
  }
  if (durations.length === 0) return MIN_SEGMENT_PX / 300;
  const minDur = Math.min(...durations);
  return minDur > 0 ? MIN_SEGMENT_PX / minDur : MIN_SEGMENT_PX / 300;
}

interface Stats {
  totalMs: number;
  minHigh: number;
  maxHigh: number;
  minLow: number;
  maxLow: number;
}

function computeStats(pulses: [number, number][]): Stats | null {
  if (pulses.length === 0) return null;
  const highs = pulses.map(([h]) => h).filter((v) => v > 0);
  const lows = pulses.map(([, l]) => l).filter((v) => v > 0 && v < 5000);
  const totalUs = pulses.reduce((sum, [h, l]) => sum + h + l, 0);
  return {
    totalMs: totalUs / 1000,
    minHigh: Math.min(...highs),
    maxHigh: Math.max(...highs),
    minLow: lows.length ? Math.min(...lows) : 0,
    maxLow: lows.length ? Math.max(...lows) : 0,
  };
}

function StatRow({
  label,
  value,
  textColor,
  secondaryColor,
}: {
  label: string;
  value: string;
  textColor: string;
  secondaryColor: string;
}) {
  return (
    <View style={styles.statRow}>
      <Text style={[styles.statLabel, { color: secondaryColor }]}>{label}</Text>
      <Text style={[styles.statValue, { color: textColor }]}>{value}</Text>
    </View>
  );
}

export default function SlotDetailScreen() {
  const { slot } = useLocalSearchParams<{ slot: string }>();
  const slotNum = parseInt(slot, 10);
  const colorScheme = (useColorScheme() ?? 'light') as 'light' | 'dark';
  const isDark = colorScheme === 'dark';
  const tint = Colors[colorScheme].tint;

  const [signal, setSignal] = useState<SignalData | null>(null);
  const [loading, setLoading] = useState(true);
  const [playing, setPlaying] = useState(false);

  useEffect(() => {
    getSignalData(slotNum).then((data) => {
      setSignal(data);
      setLoading(false);
    });
  }, [slotNum]);

  const handleMoreOptions = () => {
    ActionSheetIOS.showActionSheetWithOptions(
      {
        options: ['Cancel', 'Delete Signal'],
        destructiveButtonIndex: 1,
        cancelButtonIndex: 0,
      },
      async (buttonIndex) => {
        if (buttonIndex === 1) {
          try {
            await deleteSlot(slotNum);
            router.back();
          } catch {
            Alert.alert('Error', 'Could not delete signal');
          }
        }
      },
    );
  };

  const handlePlay = async () => {
    setPlaying(true);
    try {
      await playSlot(slotNum);
    } catch {
      Alert.alert('Error', 'Could not communicate with device');
    } finally {
      setPlaying(false);
    }
  };

  const bg = isDark ? '#151718' : '#f2f2f7';
  const cardBg = isDark ? '#1c1c1e' : '#fff';
  const textColor = isDark ? '#fff' : '#000';
  const secondaryColor = isDark ? '#ababab' : '#6e6e73';

  if (loading) {
    return (
      <View style={[styles.centered, { backgroundColor: bg }]}>
        <ActivityIndicator />
      </View>
    );
  }

  if (!signal) {
    return (
      <>
        <Stack.Screen options={{ title: `Slot ${slotNum}` }} />
        <View style={[styles.centered, { backgroundColor: bg }]}>
          <Text style={{ color: secondaryColor }}>Slot not found or not connected</Text>
        </View>
      </>
    );
  }

  const scale = computeScale(signal.pulses);
  const stats = computeStats(signal.pulses);

  return (
    <>
      <Stack.Screen
        options={{
          title: signal.name || `Slot ${slotNum}`,
          headerRight: () => (
            <Pressable onPress={handleMoreOptions}>
              <IconSymbol name="ellipsis" size={22} color={tint} />
            </Pressable>
          ),
        }}
      />
      <View style={[styles.screen, { backgroundColor: bg }]}>
        {/* Info + waveform cards */}
        <View style={styles.content}>
          <View style={[styles.card, { backgroundColor: cardBg }]}>
            <StatRow
              label="Pulses"
              value={String(signal.pulseCount)}
              textColor={textColor}
              secondaryColor={secondaryColor}
            />
            {stats && (
              <>
                <StatRow
                  label="Duration"
                  value={`${stats.totalMs.toFixed(1)} ms`}
                  textColor={textColor}
                  secondaryColor={secondaryColor}
                />
                <StatRow
                  label="High range"
                  value={`${stats.minHigh}–${stats.maxHigh} µs`}
                  textColor={textColor}
                  secondaryColor={secondaryColor}
                />
                <StatRow
                  label="Low range"
                  value={`${stats.minLow}–${stats.maxLow} µs`}
                  textColor={textColor}
                  secondaryColor={secondaryColor}
                />
              </>
            )}
          </View>

          <View style={[styles.card, { backgroundColor: '#1a1a1a' }]}>
            <Text style={styles.waveformLabel}>Signal Waveform</Text>
            <ScrollView horizontal showsHorizontalScrollIndicator={false}>
              <View style={styles.waveformContainer}>
                {signal.pulses.map(([high, low], i) => {
                  const highW = clamp(Math.round(high * scale), MIN_SEGMENT_PX, MAX_SEGMENT_PX);
                  const lowW = clamp(Math.round(low * scale), MIN_SEGMENT_PX, MAX_SEGMENT_PX);
                  return (
                    <View key={i} style={styles.pulseGroup}>
                      <View style={[styles.highBar, { width: highW }]} />
                      <View style={[styles.lowBar, { width: lowW }]} />
                    </View>
                  );
                })}
              </View>
            </ScrollView>
          </View>
        </View>

        {/* Play button — flex:1 so SwiftUI sees the full safe area height */}
        <Host style={{ flex: 1 }} colorScheme={colorScheme}>
          <VStack modifiers={[padding({ bottom: 16 })]}>
            <Spacer />
            <Button
              onPress={handlePlay}
              systemImage="play.circle"
              label="Play"
              modifiers={[
                buttonStyle('bordered'),
                controlSize('large'),
                containerRelativeFrame({ axes: 'horizontal' }),
                swiftTint(tint),
                disabled(playing),
              ]}
            />
          </VStack>
        </Host>
      </View>
    </>
  );
}

const styles = StyleSheet.create({
  centered: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  screen: {
    flex: 1,
  },
  content: {
    padding: 16,
    gap: 16,
  },
  card: {
    borderRadius: 12,
    padding: 16,
    overflow: 'hidden',
  },
  statRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 7,
  },
  statLabel: {
    fontSize: 15,
  },
  statValue: {
    fontSize: 15,
    fontWeight: '500',
  },
  // Waveform
  waveformLabel: {
    fontSize: 11,
    fontWeight: '600',
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    color: '#888',
    marginBottom: 12,
  },
  waveformContainer: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    paddingVertical: 4,
    minHeight: HIGH_HEIGHT + 16,
  },
  pulseGroup: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    marginRight: 1,
  },
  highBar: {
    height: HIGH_HEIGHT,
    backgroundColor: '#4CAF50',
    borderTopLeftRadius: 2,
    borderTopRightRadius: 2,
  },
  lowBar: {
    height: LOW_HEIGHT,
    backgroundColor: '#444',
  },
});
