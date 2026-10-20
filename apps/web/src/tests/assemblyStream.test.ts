import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// Token comes from our backend — mocked here.
const fetchSpeechToken = vi.fn();
vi.mock('../api/client', () => ({
  fetchSpeechToken: () => fetchSpeechToken(),
  ApiError: class ApiError extends Error {},
}));

import { startAssemblyStream } from '../lib/assemblyStream';

class FakeWS {
  static CONNECTING = 0;
  static OPEN = 1;
  static last: FakeWS | null = null;
  readyState = FakeWS.CONNECTING;
  binaryType = '';
  sent: unknown[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((e: { data: unknown }) => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: (() => void) | null = null;
  constructor(public url: string) { FakeWS.last = this; }
  send(d: unknown) { this.sent.push(d); }
  close() { this.readyState = 3; }
  open() { this.readyState = FakeWS.OPEN; this.onopen?.(); }
  emit(msg: object) { this.onmessage?.({ data: JSON.stringify(msg) }); }
}

let processor: { onaudioprocess: ((e: unknown) => void) | null; connect: () => void; disconnect: () => void };
class FakeAudioContext {
  sampleRate = 48000;
  destination = {};
  audioWorklet = { addModule: () => Promise.reject(new Error('no worklet in tests')) };
  createMediaStreamSource() { return { connect: vi.fn() }; }
  createAnalyser() { return { fftSize: 512, connect: vi.fn(), getByteTimeDomainData: vi.fn() }; }
  createGain() { return { gain: { value: 1 }, connect: vi.fn() }; }
  createScriptProcessor() {
    processor = { onaudioprocess: null, connect: vi.fn(), disconnect: vi.fn() };
    return processor;
  }
  close() { return Promise.resolve(); }
}

const track = { stop: vi.fn() };
const handlers = () => ({ onPartial: vi.fn(), onFinal: vi.fn(), onError: vi.fn() });

beforeEach(() => {
  vi.stubGlobal('WebSocket', FakeWS);
  vi.stubGlobal('AudioContext', FakeAudioContext);
  vi.stubGlobal('navigator', {
    mediaDevices: { getUserMedia: vi.fn(async () => ({ getTracks: () => [track] })) },
  });
  URL.createObjectURL = vi.fn(() => 'blob:worklet');
  URL.revokeObjectURL = vi.fn();
  fetchSpeechToken.mockResolvedValue({ token: 'tmp-1', expires_in_seconds: 60 });
  track.stop.mockClear();
});
afterEach(() => { vi.unstubAllGlobals(); });

describe('startAssemblyStream', () => {
  it('connects to Universal-3.6 Pro in French with the temporary token', async () => {
    await startAssemblyStream('fr', handlers());
    const url = new URL(FakeWS.last!.url);
    expect(url.origin + url.pathname).toBe('wss://streaming.assemblyai.com/v3/ws');
    expect(url.searchParams.get('speech_model')).toBe('universal-3-6-pro');
    expect(url.searchParams.get('encoding')).toBe('pcm_s16le');
    expect(url.searchParams.get('sample_rate')).toBe('16000');
    expect(url.searchParams.get('language_codes')).toBe('["fr"]');
    expect(url.searchParams.get('token')).toBe('tmp-1');
  });

  it('sends 16 kHz 16-bit PCM in 50 ms chunks, queued until the socket opens', async () => {
    await startAssemblyStream('fr', handlers());
    const ws = FakeWS.last!;
    // 4800 samples at 48 kHz = 100 ms → 1600 samples at 16 kHz → two 800-sample chunks.
    processor.onaudioprocess!({ inputBuffer: { getChannelData: () => new Float32Array(4800).fill(0.5) } });
    expect(ws.sent).toHaveLength(0); // still connecting
    ws.open();
    expect(ws.sent).toHaveLength(2);
    expect((ws.sent[0] as ArrayBuffer).byteLength).toBe(1600);
    expect(new Int16Array(ws.sent[0] as ArrayBuffer)[400]).toBe(Math.round(0.5 * 0x7fff - 0.5));
  });

  it('turns partial and final Turn messages into words, without duplicates', async () => {
    const h = handlers();
    await startAssemblyStream('fr', h);
    const ws = FakeWS.last!;
    ws.open();
    ws.emit({ type: 'Turn', turn_order: 0, end_of_turn: false, transcript: 'fuite sous' });
    expect(h.onPartial).toHaveBeenLastCalledWith('fuite sous');
    ws.emit({ type: 'Turn', turn_order: 0, end_of_turn: true, transcript: 'Fuite sous l’évier.' });
    ws.emit({ type: 'Turn', turn_order: 0, end_of_turn: true, transcript: 'Fuite sous l’évier.' });
    expect(h.onFinal).toHaveBeenCalledTimes(1);
    expect(h.onFinal).toHaveBeenCalledWith('Fuite sous l’évier.');
  });

  it('stop sends Terminate, waits for Termination, then releases the microphone', async () => {
    const session = await startAssemblyStream('fr', handlers());
    const ws = FakeWS.last!;
    ws.open();
    const done = session!.stop();
    expect(ws.sent[ws.sent.length - 1]).toBe(JSON.stringify({ type: 'Terminate' }));
    ws.emit({ type: 'Termination' });
    await done;
    expect(track.stop).toHaveBeenCalled();
  });

  it('reports a blocked microphone and never opens a socket', async () => {
    FakeWS.last = null;
    vi.stubGlobal('navigator', {
      mediaDevices: { getUserMedia: vi.fn(async () => { throw Object.assign(new Error('no'), { name: 'NotAllowedError' }); }) },
    });
    const h = handlers();
    expect(await startAssemblyStream('fr', h)).toBeNull();
    expect(h.onError).toHaveBeenCalledWith('not-allowed');
    expect(FakeWS.last).toBeNull();
  });

  it('reports the service as unavailable when no token can be had, and frees the mic', async () => {
    const { ApiError } = await import('../api/client');
    fetchSpeechToken.mockRejectedValue(new (ApiError as unknown as new (m: string) => Error)('down'));
    const h = handlers();
    expect(await startAssemblyStream('fr', h)).toBeNull();
    expect(h.onError).toHaveBeenCalledWith('unavailable');
    expect(track.stop).toHaveBeenCalled();
  });
});
