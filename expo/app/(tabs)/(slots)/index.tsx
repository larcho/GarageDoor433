import { useCallback, useState } from 'react';
import { ActivityIndicator, Alert, Pressable, View } from 'react-native';

import { router,Stack, useFocusEffect } from 'expo-router';
import {
  Button,
  ContentUnavailableView,
  Host,
  HStack,
  Image,
  List,
  ProgressView,
  Section,
  Spacer,
  Text,
  VStack,
} from '@expo/ui/swift-ui';
import { buttonStyle, disabled, frame, progressViewStyle } from '@expo/ui/swift-ui/modifiers';

import { RecordSheet } from '@/components/record-sheet';
import { IconSymbol } from '@/components/ui/icon-symbol';
import { Colors } from '@/constants/theme';
import { useColorScheme } from '@/hooks/use-color-scheme';
import { getSlots, playSlot, type Slot } from '@/services/device-service';

export default function SlotsScreen() {
  const [slots, setSlots] = useState<Slot[]>([]);
  const [loading, setLoading] = useState(true);
  const [playingSlot, setPlayingSlot] = useState<number | null>(null);
  const [sheetOpen, setSheetOpen] = useState(false);
  const colorScheme = useColorScheme() ?? 'light';

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
    <>
      <Stack.Screen
        options={{
          headerRight: () => (
            <Pressable onPress={() => setSheetOpen(true)}>
              <IconSymbol name="plus" size={22} color={tint} />
            </Pressable>
          ),
        }}
      />
      <View style={{ flex: 1 }}>
        <Host style={{ flex: 1, backgroundColor: colorScheme === 'dark' ? '#151718' : '#fff' }} colorScheme={colorScheme}>
          {!loading && (slots.length === 0 ? (
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
                    onPress={() => router.push({ pathname: '/(tabs)/(slots)/[slot]', params: { slot: slot.slot } })}
                    modifiers={[buttonStyle('plain')]}
                  >
                    <HStack spacing={12}>
                      <Image systemName="waveform" size={20} color={tint} />
                      <VStack alignment="leading" spacing={2}>
                        <Text weight="semibold">{slot.name}</Text>
                        <Text size={13} color="secondary">
                          {`Slot ${slot.slot} · ${slot.pulseCount} pulses`}
                        </Text>
                      </VStack>
                      <Spacer />
                      <Button
                        onPress={() => handlePlay(slot)}
                        modifiers={[buttonStyle('plain'), disabled(playingSlot === slot.slot)]}
                      >
                        {playingSlot === slot.slot ? (
                          <ProgressView modifiers={[progressViewStyle('circular'), frame({ width: 20, height: 20 })]} />
                        ) : (
                          <Image systemName="play.fill" size={20} color={tint} />
                        )}
                      </Button>
                    </HStack>
                  </Button>
                ))}
              </Section>
            </List>
          ))}
          <RecordSheet
            isPresented={sheetOpen}
            onIsPresentedChange={setSheetOpen}
            onSaved={refreshSlots}
          />
        </Host>
        {loading && (
          <View style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, alignItems: 'center', justifyContent: 'center' }}>
            <ActivityIndicator size="large" color={tint} />
          </View>
        )}
      </View>
    </>
  );
}
