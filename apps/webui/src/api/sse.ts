import type { LiveStateSnapshot } from "../types/api";

type SnapshotCallback = (snapshot: LiveStateSnapshot) => void;
type ErrorCallback = (err: Event) => void;

let _source: EventSource | null = null;
let _listeners: SnapshotCallback[] = [];
let _errorListeners: ErrorCallback[] = [];

export function startSSE(interval = 1.0): void {
  if (_source) return;
  const intervalParam = Math.max(0.2, interval);
  _source = new EventSource(`/events?interval=${intervalParam}`);

  _source.onmessage = (ev: MessageEvent) => {
    try {
      const snapshot = JSON.parse(ev.data as string) as LiveStateSnapshot;
      _listeners.forEach((cb) => cb(snapshot));
    } catch {
      // malformed message — ignore
    }
  };

  _source.onerror = (ev: Event) => {
    _errorListeners.forEach((cb) => cb(ev));
    // EventSource will auto-reconnect with exponential backoff — no manual retry
  };
}

export function stopSSE(): void {
  if (_source) {
    _source.close();
    _source = null;
  }
}

export function onSnapshot(cb: SnapshotCallback): () => void {
  _listeners.push(cb);
  return () => {
    _listeners = _listeners.filter((x) => x !== cb);
  };
}

export function onSSEError(cb: ErrorCallback): () => void {
  _errorListeners.push(cb);
  return () => {
    _errorListeners = _errorListeners.filter((x) => x !== cb);
  };
}

export function isSSEConnected(): boolean {
  return _source?.readyState === EventSource.OPEN;
}
