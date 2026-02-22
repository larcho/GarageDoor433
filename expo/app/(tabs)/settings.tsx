import { useFocusEffect } from 'expo-router';
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
import {
  connect,
  disconnect,
  getStatus,
  isConnected,
  type DeviceStatus,
} from '@/services/device-service';

export default function SettingsScreen() {
  const [status, setStatus] = useState<DeviceStatus | null>(null);
  const [connected, setConnected] = useState(false);
  const [busy, setBusy] = useState(false);
  const colorScheme = useColorScheme() ?? 'light';
  const insets = useSafeAreaInsets();

  const tint = Colors[colorScheme].tint;
  const cardBg = colorScheme === 'dark' ? '#1e2023' : '#f2f2f7';

  useFocusEffect(
    useCallback(() => {
      let cancelled = false;
      setConnected(isConnected());
      getStatus().then((s) => {
        if (!cancelled) setStatus(s);
      });
      return () => {
        cancelled = true;
      };
    }, [])
  );

  const handleToggleConnection = async () => {
    setBusy(true);
    try {
      if (connected) {
        await disconnect();
      } else {
        await connect();
      }
      setConnected(isConnected());
      const s = await getStatus();
      setStatus(s);
    } catch {
      Alert.alert('Error', 'Connection failed');
    } finally {
      setBusy(false);
    }
  };

  return (
    <ThemedView style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + 8 }]}>
        <ThemedText type="title">Settings</ThemedText>
      </View>

      <ScrollView contentContainerStyle={styles.content}>
        {/* Connection Section */}
        <ThemedText type="subtitle" style={styles.sectionHeader}>
          Connection
        </ThemedText>
        <View style={[styles.section, { backgroundColor: cardBg }]}>
          <View style={styles.row}>
            <IconSymbol
              name={connected ? 'wifi' : 'wifi.slash'}
              size={22}
              color={connected ? '#34c759' : '#ff3b30'}
            />
            <ThemedText style={styles.rowLabel}>Status</ThemedText>
            <ThemedText style={[styles.rowValue, { color: connected ? '#34c759' : '#ff3b30' }]}>
              {connected ? 'Connected' : 'Disconnected'}
            </ThemedText>
          </View>

          <View style={[styles.separator, { backgroundColor: colorScheme === 'dark' ? '#333' : '#e0e0e0' }]} />

          <Pressable
            style={({ pressed }) => [styles.row, { opacity: pressed ? 0.6 : 1 }]}
            onPress={handleToggleConnection}
            disabled={busy}
          >
            {busy ? (
              <ActivityIndicator size="small" color={tint} />
            ) : (
              <ThemedText style={[styles.actionText, { color: tint }]}>
                {connected ? 'Disconnect' : 'Connect'}
              </ThemedText>
            )}
          </Pressable>
        </View>

        {/* Device Status Section */}
        <ThemedText type="subtitle" style={styles.sectionHeader}>
          Device
        </ThemedText>
        <View style={[styles.section, { backgroundColor: cardBg }]}>
          {status ? (
            <>
              <StatusRow label="State" value={status.state} cardBg={cardBg} colorScheme={colorScheme} />
              <StatusRow label="Battery" value={`${status.batteryVoltage.toFixed(2)} V`} cardBg={cardBg} colorScheme={colorScheme} />
              <StatusRow label="Saved Signals" value={String(status.savedSignals)} cardBg={cardBg} colorScheme={colorScheme} />
              <StatusRow label="Firmware" value={status.firmwareVersion} cardBg={cardBg} colorScheme={colorScheme} last />
            </>
          ) : (
            <View style={styles.row}>
              <ActivityIndicator size="small" color={tint} />
            </View>
          )}
        </View>
      </ScrollView>
    </ThemedView>
  );
}

function StatusRow({
  label,
  value,
  colorScheme,
  last,
}: {
  label: string;
  value: string;
  cardBg: string;
  colorScheme: string;
  last?: boolean;
}) {
  return (
    <>
      <View style={styles.row}>
        <ThemedText style={styles.rowLabel}>{label}</ThemedText>
        <ThemedText style={styles.rowValue}>{value}</ThemedText>
      </View>
      {!last && (
        <View style={[styles.separator, { backgroundColor: colorScheme === 'dark' ? '#333' : '#e0e0e0' }]} />
      )}
    </>
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
  content: {
    padding: 16,
    gap: 4,
  },
  sectionHeader: {
    marginTop: 12,
    marginBottom: 8,
    marginLeft: 4,
  },
  section: {
    borderRadius: 12,
    overflow: 'hidden',
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 14,
    gap: 12,
  },
  rowLabel: {
    flex: 1,
    fontSize: 16,
  },
  rowValue: {
    fontSize: 16,
    opacity: 0.6,
  },
  separator: {
    height: StyleSheet.hairlineWidth,
    marginLeft: 16,
  },
  actionText: {
    fontSize: 16,
    fontWeight: '600',
  },
});
