// Stub BLE device service — returns mock data matching the ESP32 JSON API.
// Swap this out for real BLE communication later.

export interface Slot {
  slot: number;
  name: string;
  protocol: string;
  pulseCount: number;
  frequency: number;
}

export interface DeviceStatus {
  state: string;
  batteryVoltage: number;
  savedSignals: number;
  firmwareVersion: string;
}

export interface RecordingResult {
  pulseCount: number;
  protocol: string;
  frequency: number;
}

let connected = false;

const mockSlots: Map<number, Slot> = new Map([
  [1, { slot: 1, name: 'Garage Main', protocol: 'OOK', pulseCount: 128, frequency: 433.92 }],
  [3, { slot: 3, name: 'Side Gate', protocol: 'OOK', pulseCount: 96, frequency: 433.92 }],
]);

export async function getSlots(): Promise<Slot[]> {
  await delay(300);
  return Array.from(mockSlots.values());
}

export async function playSlot(slot: number): Promise<{ success: boolean }> {
  await delay(500);
  if (!mockSlots.has(slot)) {
    return { success: false };
  }
  return { success: true };
}

export async function startRecording(): Promise<void> {
  await delay(200);
}

export async function stopRecording(): Promise<RecordingResult> {
  await delay(1500);
  return {
    pulseCount: 64 + Math.floor(Math.random() * 128),
    protocol: 'OOK',
    frequency: 433.92,
  };
}

export async function saveSignal(
  slot: number,
  name: string,
  recording: RecordingResult
): Promise<{ success: boolean }> {
  await delay(400);
  mockSlots.set(slot, {
    slot,
    name,
    protocol: recording.protocol,
    pulseCount: recording.pulseCount,
    frequency: recording.frequency,
  });
  return { success: true };
}

export async function deleteSlot(slot: number): Promise<{ success: boolean }> {
  await delay(300);
  mockSlots.delete(slot);
  return { success: true };
}

export async function getStatus(): Promise<DeviceStatus> {
  await delay(200);
  return {
    state: connected ? 'idle' : 'disconnected',
    batteryVoltage: 3.72,
    savedSignals: mockSlots.size,
    firmwareVersion: '0.1.0',
  };
}

export async function connect(): Promise<void> {
  await delay(800);
  connected = true;
}

export async function disconnect(): Promise<void> {
  await delay(300);
  connected = false;
}

export function isConnected(): boolean {
  return connected;
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
