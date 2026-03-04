import { BleManager, Device, Subscription, BleError } from 'react-native-ble-plx';
import { Platform } from 'react-native';

const NUS_SERVICE_UUID = '6E400001-B5A3-F393-E0A9-E50E24DCCA9E';
const NUS_RX_UUID = '6E400002-B5A3-F393-E0A9-E50E24DCCA9E';
const NUS_TX_UUID = '6E400003-B5A3-F393-E0A9-E50E24DCCA9E';

const DEVICE_NAME = 'GarageDoor433';
const SCAN_TIMEOUT_MS = 10000; // manual connect scan timeout
const AUTO_SCAN_TIMEOUT_MS = 5000; // background auto-connect scan timeout

export type ConnectionState = 'disconnected' | 'scanning' | 'connecting' | 'connected';
type ConnectionListener = (state: ConnectionState) => void;
type ResponseListener = (json: Record<string, unknown>) => void;

class BLEManager {
  private manager: BleManager;
  private device: Device | null = null;
  private notifySub: Subscription | null = null;
  private disconnectSub: Subscription | null = null;
  private rxBuffer = '';
  private _state: ConnectionState = 'disconnected';
  private connectionListeners: Set<ConnectionListener> = new Set();
  private responseListeners: Set<ResponseListener> = new Set();

  constructor() {
    this.manager = new BleManager();
  }

  get state(): ConnectionState {
    return this._state;
  }

  private setState(state: ConnectionState) {
    this._state = state;
    for (const listener of this.connectionListeners) {
      listener(state);
    }
  }

  onConnectionChange(listener: ConnectionListener): () => void {
    this.connectionListeners.add(listener);
    return () => this.connectionListeners.delete(listener);
  }

  onResponse(listener: ResponseListener): () => void {
    this.responseListeners.add(listener);
    return () => this.responseListeners.delete(listener);
  }

  private async waitForBluetooth(): Promise<void> {
    if (Platform.OS !== 'ios') return;
    const btState = await this.manager.state();
    if (btState === 'PoweredOn') return;
    await new Promise<void>((resolve, reject) => {
      const sub = this.manager.onStateChange((s) => {
        if (s === 'PoweredOn') {
          sub.remove();
          resolve();
        } else if (s === 'Unsupported' || s === 'Unauthorized') {
          sub.remove();
          reject(new Error(`Bluetooth is ${s}`));
        }
      }, true);
    });
  }

  async scan(timeoutMs = SCAN_TIMEOUT_MS): Promise<Device> {
    await this.waitForBluetooth();
    this.setState('scanning');

    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        this.manager.stopDeviceScan();
        this.setState('disconnected');
        reject(new Error('Scan timed out — device not found'));
      }, timeoutMs);

      this.manager.startDeviceScan(
        [NUS_SERVICE_UUID],
        { allowDuplicates: false },
        (error: BleError | null, scanned: Device | null) => {
          if (error) {
            clearTimeout(timeout);
            this.manager.stopDeviceScan();
            this.setState('disconnected');
            reject(error);
            return;
          }
          if (scanned?.name === DEVICE_NAME || scanned?.localName === DEVICE_NAME) {
            clearTimeout(timeout);
            this.manager.stopDeviceScan();
            resolve(scanned);
          }
        },
      );
    });
  }

  async connect(device?: Device): Promise<void> {
    const target = device ?? (await this.scan());
    this.setState('connecting');

    try {
      const connected = await target.connect({ requestMTU: 185 });
      // discoverAllServicesAndCharacteristics will block while the iOS pairing
      // dialog is shown — this is normal on first connection with a new device.
      await connected.discoverAllServicesAndCharacteristics();
      this.device = connected;

      this.disconnectSub = this.manager.onDeviceDisconnected(connected.id, () => {
        this.cleanup();
        this.setState('disconnected');
      });

      this.rxBuffer = '';
      this.notifySub = connected.monitorCharacteristicForService(
        NUS_SERVICE_UUID,
        NUS_TX_UUID,
        (_error, characteristic) => {
          if (_error || !characteristic?.value) return;
          const decoded = atob(characteristic.value);
          this.rxBuffer += decoded;
          this.processBuffer();
        },
      );

      this.setState('connected');
    } catch (err) {
      this.cleanup();
      this.setState('disconnected');
      throw err;
    }
  }

  /**
   * Silently scan for the device and connect if found.
   * Uses a shorter timeout so it doesn't block the UI on startup.
   * Safe to call when already connected or scanning — returns immediately.
   */
  async autoConnect(): Promise<void> {
    if (this._state !== 'disconnected') return;
    try {
      const device = await this.scan(AUTO_SCAN_TIMEOUT_MS);
      await this.connect(device);
    } catch {
      // Device not available — state already reset to 'disconnected'
    }
  }

  async disconnect(): Promise<void> {
    if (this.device) {
      try {
        await this.device.cancelConnection();
      } catch {
        // Already disconnected
      }
    }
    this.cleanup();
    this.setState('disconnected');
  }

  async sendCommand(json: Record<string, unknown>): Promise<void> {
    if (!this.device || this._state !== 'connected') {
      throw new Error('Not connected');
    }
    const payload = JSON.stringify(json) + '\n';
    const encoded = btoa(payload);
    await this.device.writeCharacteristicWithResponseForService(
      NUS_SERVICE_UUID,
      NUS_RX_UUID,
      encoded,
    );
  }

  private processBuffer() {
    let newlineIdx: number;
    while ((newlineIdx = this.rxBuffer.indexOf('\n')) !== -1) {
      const line = this.rxBuffer.slice(0, newlineIdx).trim();
      this.rxBuffer = this.rxBuffer.slice(newlineIdx + 1);
      if (!line) continue;
      try {
        const parsed = JSON.parse(line);
        for (const listener of this.responseListeners) {
          listener(parsed);
        }
      } catch {
        // Ignore malformed JSON
      }
    }
  }

  private cleanup() {
    this.notifySub?.remove();
    this.notifySub = null;
    this.disconnectSub?.remove();
    this.disconnectSub = null;
    this.device = null;
    this.rxBuffer = '';
  }
}

export const bleManager = new BLEManager();
