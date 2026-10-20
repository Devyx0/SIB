// Live dictation on AssemblyAI Universal-3.6 Pro streaming.
//
// Microphone → AudioWorklet (raw float samples) → downsample to 16 kHz →
// 16-bit PCM in ~50 ms chunks → WebSocket to AssemblyAI. The server only
// hands out a single-use token (GET /api/v1/speech/token); the API key never
// reaches the browser. Docs: https://www.assemblyai.com/docs/streaming

import { ApiError, fetchSpeechToken } from '../api/client';
import type { Lang } from '../i18n';

export type StreamError = 'not-allowed' | 'no-microphone' | 'unavailable' | 'network';

export interface StreamHandlers {
  /** Words still being recognised (replaces the previous partial). */
  onPartial: (text: string) => void;
  /** A finished, punctuated turn. */
  onFinal: (text: string) => void;
  /** Microphone loudness 0–1, for the waveform. */
  onLevel?: (level: number) => void;
  onError: (code: StreamError) => void;
}

export interface StreamSession {
  /** Flush the last words, then close everything. */
  stop: () => Promise<void>;
}

const WS_URL = 'wss://streaming.assemblyai.com/v3/ws';
const TARGET_RATE = 16000;
const CHUNK_SAMPLES = 800; // 50 ms at 16 kHz

// Sends each render quantum's samples to the main thread.
const WORKLET = `
class PcmCapture extends AudioWorkletProcessor {
  process(inputs) {
    const ch = inputs[0] && inputs[0][0];
    if (ch) this.port.postMessage(ch.slice(0));
    return true;
  }
}
registerProcessor('pcm-capture', PcmCapture);
`;

type AudioCtxCtor = typeof AudioContext;
function audioContextCtor(): AudioCtxCtor | undefined {
  if (typeof window === 'undefined') return undefined;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return window.AudioContext ?? (window as any).webkitAudioContext;
}

export function streamingSupported(): boolean {
  return typeof navigator !== 'undefined'
    && !!navigator.mediaDevices?.getUserMedia
    && typeof WebSocket !== 'undefined'
    && !!audioContextCtor();
}

/** Linear-interpolating resampler with state across chunks. */
function makeResampler(fromRate: number) {
  const ratio = fromRate / TARGET_RATE;
  let pos = 0;
  let prev = 0;
  return (input: Float32Array): Float32Array => {
    const out: number[] = [];
    while (pos < input.length) {
      const i = Math.floor(pos);
      const frac = pos - i;
      const a = i === 0 ? prev : input[i - 1];
      const b = input[i];
      out.push(a + (b - a) * frac);
      pos += ratio;
    }
    pos -= input.length;
    prev = input[input.length - 1] ?? prev;
    return Float32Array.from(out);
  };
}

function toPcm16(samples: Float32Array): ArrayBuffer {
  const pcm = new Int16Array(samples.length);
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    pcm[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  return pcm.buffer;
}

function micError(err: unknown): StreamError {
  const name = (err as { name?: string })?.name;
  if (name === 'NotAllowedError' || name === 'SecurityError') return 'not-allowed';
  if (name === 'NotFoundError' || name === 'OverconstrainedError' || name === 'NotReadableError') return 'no-microphone';
  return 'unavailable';
}

export async function startAssemblyStream(lang: Lang, h: StreamHandlers): Promise<StreamSession | null> {
  const Ctx = audioContextCtor();
  if (!Ctx) { h.onError('unavailable'); return null; }

  // Ask for the microphone and the token at the same time.
  const [micRes, tokenRes] = await Promise.allSettled([
    navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    }),
    fetchSpeechToken(),
  ]);
  if (micRes.status === 'rejected') {
    h.onError(micError(micRes.reason));
    return null;
  }
  const stream = micRes.value;
  const releaseMic = () => stream.getTracks().forEach((t) => t.stop());
  if (tokenRes.status === 'rejected') {
    releaseMic();
    h.onError(tokenRes.reason instanceof ApiError ? 'unavailable' : 'network');
    return null;
  }

  const params = new URLSearchParams({
    speech_model: 'universal-3-6-pro',
    encoding: 'pcm_s16le',
    sample_rate: String(TARGET_RATE),
    language_codes: JSON.stringify([lang === 'fr' ? 'fr' : 'en']),
    token: tokenRes.value.token,
  });
  const ws = new WebSocket(`${WS_URL}?${params.toString()}`);
  ws.binaryType = 'arraybuffer';

  const ctx = new Ctx();
  const source = ctx.createMediaStreamSource(stream);
  const analyser = ctx.createAnalyser();
  analyser.fftSize = 512;
  source.connect(analyser);
  const sink = ctx.createGain();
  sink.gain.value = 0; // keep the graph pulling without playing anything back
  sink.connect(ctx.destination);

  const resample = makeResampler(ctx.sampleRate);
  let pending = new Float32Array(0);
  const queued: ArrayBuffer[] = [];
  let stopping = false;
  let closed = false;

  function send(buf: ArrayBuffer) {
    if (ws.readyState === WebSocket.OPEN) ws.send(buf);
    else if (ws.readyState === WebSocket.CONNECTING) queued.push(buf);
  }

  function onSamples(chunk: Float32Array) {
    if (stopping) return;
    const down = resample(chunk);
    const merged = new Float32Array(pending.length + down.length);
    merged.set(pending);
    merged.set(down, pending.length);
    let offset = 0;
    while (merged.length - offset >= CHUNK_SAMPLES) {
      send(toPcm16(merged.subarray(offset, offset + CHUNK_SAMPLES)));
      offset += CHUNK_SAMPLES;
    }
    pending = merged.slice(offset);
  }

  // Capture: AudioWorklet where available, ScriptProcessor as a fallback.
  let teardownCapture = () => {};
  try {
    const url = URL.createObjectURL(new Blob([WORKLET], { type: 'application/javascript' }));
    await ctx.audioWorklet.addModule(url);
    URL.revokeObjectURL(url);
    const node = new AudioWorkletNode(ctx, 'pcm-capture');
    node.port.onmessage = (e: MessageEvent<Float32Array>) => onSamples(e.data);
    source.connect(node);
    node.connect(sink);
    teardownCapture = () => { node.port.onmessage = null; node.disconnect(); };
  } catch {
    const proc = ctx.createScriptProcessor(4096, 1, 1);
    proc.onaudioprocess = (e) => onSamples(e.inputBuffer.getChannelData(0));
    source.connect(proc);
    proc.connect(sink);
    teardownCapture = () => { proc.onaudioprocess = null; proc.disconnect(); };
  }

  // Loudness for the waveform.
  let raf = 0;
  if (h.onLevel) {
    const buf = new Uint8Array(analyser.fftSize);
    const tick = () => {
      analyser.getByteTimeDomainData(buf);
      let sum = 0;
      for (const v of buf) { const d = (v - 128) / 128; sum += d * d; }
      h.onLevel?.(Math.min(1, Math.sqrt(sum / buf.length) * 4));
      raf = requestAnimationFrame(tick);
    };
    tick();
  }

  let lastFinalTurn = -1;
  let resolveTermination: () => void = () => {};
  const terminated = new Promise<void>((r) => { resolveTermination = r; });

  ws.onopen = () => {
    for (const b of queued) ws.send(b);
    queued.length = 0;
  };
  ws.onmessage = (ev) => {
    if (typeof ev.data !== 'string') return;
    let msg: { type?: string; transcript?: string; end_of_turn?: boolean; turn_order?: number };
    try { msg = JSON.parse(ev.data); } catch { return; }
    if (msg.type === 'Turn') {
      const text = (msg.transcript ?? '').trim();
      if (msg.end_of_turn) {
        // A turn can be re-sent once formatted; keep only the first final.
        if (msg.turn_order != null && msg.turn_order <= lastFinalTurn) return;
        if (msg.turn_order != null) lastFinalTurn = msg.turn_order;
        h.onPartial('');
        if (text) h.onFinal(text);
      } else {
        h.onPartial(text);
      }
    } else if (msg.type === 'Termination') {
      resolveTermination();
    }
  };
  ws.onerror = () => { if (!stopping) h.onError('network'); };
  ws.onclose = () => {
    resolveTermination();
    if (!stopping && !closed) h.onError('network');
  };

  function release() {
    if (closed) return;
    closed = true;
    cancelAnimationFrame(raf);
    teardownCapture();
    releaseMic();
    void ctx.close().catch(() => {});
    if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) ws.close();
  }

  return {
    async stop() {
      if (stopping) return;
      stopping = true;
      if (pending.length) send(toPcm16(pending));
      pending = new Float32Array(0);
      if (ws.readyState === WebSocket.OPEN) {
        // Terminate makes AssemblyAI finalise the open turn before closing.
        ws.send(JSON.stringify({ type: 'Terminate' }));
        await Promise.race([terminated, new Promise((r) => setTimeout(r, 2500))]);
      }
      release();
    },
  };
}
