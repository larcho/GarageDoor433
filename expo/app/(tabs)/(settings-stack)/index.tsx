import { useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { Alert } from 'react-native';

import {
  Host,
  List,
  Section,
  LabeledContent,
  Text,
  Button,
  ProgressView,
} from '@expo/ui/swift-ui';
import { disabled } from '@expo/ui/swift-ui/modifiers';

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
    <Host style={{ flex: 1 }} colorScheme={colorScheme}>
      <List listStyle="insetGrouped">
        <Section title="Connection">
          <LabeledContent label="Status">
            <Text color={connected ? 'green' : 'red'}>
              {connected ? 'Connected' : 'Disconnected'}
            </Text>
          </LabeledContent>
          <Button
            onPress={handleToggleConnection}
            label={busy ? 'Connecting…' : connected ? 'Disconnect' : 'Connect'}
            modifiers={[disabled(busy)]}
          />
        </Section>

        <Section title="Device">
          {status ? (
            <>
              <LabeledContent label="State">
                <Text>{status.state}</Text>
              </LabeledContent>
              <LabeledContent label="Battery">
                <Text>{`${status.batteryVoltage.toFixed(2)} V`}</Text>
              </LabeledContent>
              <LabeledContent label="Saved Signals">
                <Text>{String(status.savedSignals)}</Text>
              </LabeledContent>
            </>
          ) : (
            <ProgressView />
          )}
        </Section>
      </List>
    </Host>
  );
}
