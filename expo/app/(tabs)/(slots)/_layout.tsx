import { Stack } from 'expo-router';

export default function SlotsLayout() {
  return (
    <Stack>
      <Stack.Screen name="index" options={{ title: 'Slots' }} />
      <Stack.Screen name="[slot]" options={{ title: 'Signal Detail' }} />
    </Stack>
  );
}
