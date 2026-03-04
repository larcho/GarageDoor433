import { useCallback, useEffect, useState } from 'react';
import { Alert } from 'react-native';

import { useFocusEffect } from 'expo-router';
import {
  Button,
  Host,
  LabeledContent,
  List,
  ProgressView,
  Section,
  Text,
} from '@expo/ui/swift-ui';
import { disabled } from '@expo/ui/swift-ui/modifiers';

import { useBleState } from '@/contexts/ble-context';
import { useColorScheme } from '@/hooks/use-color-scheme';
import { connect, type DeviceStatus,disconnect, getStatus } from '@/services/device-service';

export default function SettingsScreen() {
  const [status, setStatus] = useState<DeviceStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const colorScheme = useColorScheme() ?? 'light';

  const { connectionState } = useBleState();
  const connected = connectionState === 'connected';
  const isSearching = connectionState === 'scanning' || connectionState === 'connecting';

  // Fetch (or clear) device status whenever connection state changes
  useEffect(() => {
    if (connected) {
      getStatus().then(setStatus);
    } else {
      setStatus(null);
    }
  }, [connected]);

  // Re-fetch status when the user navigates back to this tab
  useFocusEffect(
    useCallback(() => {
      if (connected) {
        getStatus().then(setStatus);
      }
    }, [connected]),
  );

  const handleToggleConnection = async () => {
    setBusy(true);
    try {
      if (connected) {
        await disconnect();
      } else {
        await connect();
      }
    } catch {
      Alert.alert(
        connected ? 'Disconnect Failed' : 'Connection Failed',
        connected
          ? 'Could not disconnect from the device.'
          : 'Could not find GarageDoor433. Make sure it is powered on and nearby.\n\nFirst time connecting? A 6-digit PIN will appear on the device display — enter it when prompted by iOS.',
      );
    } finally {
      setBusy(false);
    }
  };

  const statusText = isSearching
    ? connectionState === 'scanning'
      ? 'Searching…'
      : 'Pairing…'
    : connected
      ? 'Connected'
      : 'Disconnected';

  const statusColor = connected ? 'green' : isSearching ? 'orange' : 'red';

  const buttonLabel = busy
    ? connected
      ? 'Disconnecting…'
      : 'Connecting…'
    : connected
      ? 'Disconnect'
      : 'Connect';

  return (
    <Host style={{ flex: 1 }} colorScheme={colorScheme}>
      <List listStyle="insetGrouped">
        <Section title="Connection">
          <LabeledContent label="Status">
            {isSearching ? (
              <ProgressView />
            ) : (
              <Text color={statusColor}>{statusText}</Text>
            )}
          </LabeledContent>
          <Button
            onPress={handleToggleConnection}
            label={buttonLabel}
            modifiers={[disabled(busy || isSearching)]}
          />
        </Section>

        <Section title="Device">
          {connected ? (
            status ? (
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
            )
          ) : (
            <LabeledContent label="Status">
              <Text color="secondary">{isSearching ? 'Looking for device…' : 'Not connected'}</Text>
            </LabeledContent>
          )}
        </Section>
      </List>
    </Host>
  );
}
