import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import { AppState, type AppStateStatus } from 'react-native';

import { bleManager, type ConnectionState } from '@/services/ble-manager';
import { autoConnect } from '@/services/device-service';

type BleContextValue = {
  connectionState: ConnectionState;
};

const BleContext = createContext<BleContextValue>({ connectionState: 'disconnected' });

/**
 * Provides reactive BLE connection state to the entire app and manages
 * auto-connect on launch and on every app foreground event.
 *
 * First connection: iOS will show a system PIN entry dialog when the device
 * initiates pairing — no extra app code needed.
 * Subsequent connections: bonded device reconnects silently, no PIN shown.
 */
export function BleProvider({ children }: { children: ReactNode }) {
  const [connectionState, setConnectionState] = useState<ConnectionState>(bleManager.state);

  // Keep context state in sync with the BLE manager
  useEffect(() => {
    return bleManager.onConnectionChange(setConnectionState);
  }, []);

  // Auto-connect on mount and on every app foreground transition
  useEffect(() => {
    autoConnect();

    const handleAppState = (nextState: AppStateStatus) => {
      if (nextState === 'active') {
        autoConnect();
      }
    };

    const sub = AppState.addEventListener('change', handleAppState);
    return () => sub.remove();
  }, []);

  return <BleContext.Provider value={{ connectionState }}>{children}</BleContext.Provider>;
}

export function useBleState(): BleContextValue {
  return useContext(BleContext);
}
