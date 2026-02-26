import { bleManager } from './ble-manager';

export interface Slot {
  slot: number;
  name: string;
  protocol: string;
  pulseCount: number;
}

export interface DeviceStatus {
  state: string;
  batteryVoltage: number;
  savedSignals: number;
}

export interface RecordingResult {
  pulseCount: number;
  protocol: string;
}

const COMMAND_TIMEOUT_MS = 5000;

function sendAndAwait(
  command: Record<string, unknown>,
  matchAction: string,
): Promise<Record<string, unknown>> {
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => {
      unsub();
      reject(new Error(`Command "${matchAction}" timed out`));
    }, COMMAND_TIMEOUT_MS);

    const unsub = bleManager.onResponse((json) => {
      if (json.action === matchAction) {
        clearTimeout(timeout);
        unsub();
        if (json.status === 'error') {
          reject(new Error((json.message as string) ?? 'Device returned error'));
        } else {
          resolve(json);
        }
      }
    });

    bleManager.sendCommand(command).catch((err) => {
      clearTimeout(timeout);
      unsub();
      reject(err);
    });
  });
}

export async function connect(): Promise<void> {
  await bleManager.connect();
}

export async function disconnect(): Promise<void> {
  await bleManager.disconnect();
}

export function isConnected(): boolean {
  return bleManager.state === 'connected';
}

export function onConnectionChange(listener: (state: string) => void): () => void {
  return bleManager.onConnectionChange(listener);
}

export async function getSlots(): Promise<Slot[]> {
  if (!isConnected()) return [];
  const resp = await sendAndAwait({ action: 'get_slots' }, 'get_slots');
  const raw = resp.slots as Array<Record<string, unknown>> | undefined;
  if (!raw) return [];
  return raw.map((s) => ({
    slot: s.slot as number,
    name: s.name as string,
    protocol: (s.protocol as string) ?? 'unknown',
    pulseCount: (s.pulse_count as number) ?? 0,
  }));
}

export async function playSlot(slot: number): Promise<{ success: boolean }> {
  await sendAndAwait({ action: 'play', slot }, 'play');
  return { success: true };
}

export async function startRecording(): Promise<void> {
  await sendAndAwait({ action: 'record' }, 'record');
}

export async function stopRecording(): Promise<RecordingResult> {
  const resp = await sendAndAwait({ action: 'stop' }, 'stop');
  return {
    pulseCount: (resp.pulse_count as number) ?? 0,
    protocol: (resp.protocol as string) ?? 'unknown',
  };
}

export async function saveSignal(
  slot: number,
  name: string,
  _recording: RecordingResult,
): Promise<{ success: boolean }> {
  await sendAndAwait({ action: 'save', slot, name }, 'save');
  return { success: true };
}

export async function deleteSlot(slot: number): Promise<{ success: boolean }> {
  await sendAndAwait({ action: 'delete', slot }, 'delete');
  return { success: true };
}

export async function getStatus(): Promise<DeviceStatus | null> {
  if (!isConnected()) return null;
  const resp = await sendAndAwait({ action: 'status' }, 'status');
  return {
    state: (resp.state as string) ?? 'unknown',
    batteryVoltage: (resp.battery as number) ?? 0,
    savedSignals: (resp.signals as number) ?? 0,
  };
}
