import { render, screen, act, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, it, expect, vi } from 'vitest';
import { JustificationProvider, useJustify } from '../components/Justification';
import { appendSpoken, finishSentence } from '../hooks/useDictation';
import type { Justification } from '../api/client';

// Fake AssemblyAI stream: tests drive partial/final turns and errors.
const stream = vi.hoisted(() => ({
  supported: false,
  handlers: null as null | {
    onPartial: (t: string) => void; onFinal: (t: string) => void;
    onLevel?: (n: number) => void; onError: (c: string) => void;
  },
  starts: 0,
  stop: vi.fn(async () => {}),
  failWith: null as null | string,
}));
vi.mock('../lib/assemblyStream', () => ({
  streamingSupported: () => stream.supported,
  startAssemblyStream: async (_lang: string, h: typeof stream.handlers) => {
    stream.starts += 1;
    stream.handlers = h;
    if (stream.failWith) { h!.onError(stream.failWith); return null; }
    return { stop: stream.stop };
  },
}));

function Harness({ onResult }: { onResult: (j: Justification | null) => void }) {
  const justify = useJustify();
  return (
    <button onClick={async () => onResult(await justify({ decision: 'Urgence', before: 'Aucune', after: 'URGENT' }))}>
      open
    </button>
  );
}

function setup() {
  const onResult = vi.fn();
  render(
    <JustificationProvider lang="fr">
      <Harness onResult={onResult} />
    </JustificationProvider>,
  );
  return onResult;
}

afterEach(() => {
  stream.supported = false;
  stream.handlers = null;
  stream.starts = 0;
  stream.failWith = null;
  stream.stop.mockClear();
});

describe('text helpers', () => {
  it('capitalises a new sentence and joins with a space', () => {
    expect(appendSpoken('', 'le locataire est absent')).toBe('Le locataire est absent');
    expect(appendSpoken('Le locataire est absent', 'jusqu’à jeudi')).toBe('Le locataire est absent jusqu’à jeudi');
    expect(appendSpoken('Absent.', 'rappeler lundi')).toBe('Absent. Rappeler lundi');
  });

  it('closes the last sentence once', () => {
    expect(finishSentence('Rappeler lundi')).toBe('Rappeler lundi.');
    expect(finishSentence('Rappeler lundi.')).toBe('Rappeler lundi.');
    expect(finishSentence('')).toBe('');
  });
});

describe('JustificationProvider', () => {
  it('typed fallback: shows the change, requires 10 chars, resolves typed', async () => {
    const onResult = setup();
    await userEvent.click(screen.getByText('open'));
    const dialog = screen.getByTestId('justification-dialog');
    expect(dialog.textContent).toContain('Aucune');
    expect(dialog.textContent).toContain('URGENT');
    expect(screen.queryByTestId('justification-mic')).toBeNull(); // no engine in jsdom
    fireEvent.change(screen.getByTestId('justification-text'), { target: { value: 'Dégât d’eau actif' } });
    await userEvent.click(screen.getByTestId('justification-confirm'));
    expect(onResult).toHaveBeenCalledWith({ text: 'Dégât d’eau actif.', input_method: 'typed' });
    expect(screen.queryByTestId('justification-dialog')).toBeNull();
  });

  it('cancel resolves null', async () => {
    const onResult = setup();
    await userEvent.click(screen.getByText('open'));
    await userEvent.click(screen.getByRole('button', { name: 'Annuler' }));
    expect(onResult).toHaveBeenCalledWith(null);
  });

  it('voice: starts listening on open, streams live words, saves as voice', async () => {
    stream.supported = true;
    const onResult = setup();
    await userEvent.click(screen.getByText('open'));
    await waitFor(() => expect(stream.starts).toBe(1));

    act(() => stream.handlers!.onPartial('dégât d’eau'));
    expect(screen.getByTestId('justification-interim').textContent).toBe('dégât d’eau');

    act(() => { stream.handlers!.onPartial(''); stream.handlers!.onFinal('dégât d’eau actif dans la cuisine'); });
    expect((screen.getByTestId('justification-text') as HTMLTextAreaElement).value)
      .toBe('Dégât d’eau actif dans la cuisine');

    // Confirm waits for the stream to flush its last words.
    await userEvent.click(screen.getByTestId('justification-confirm'));
    await waitFor(() => expect(onResult).toHaveBeenCalledWith({
      text: 'Dégât d’eau actif dans la cuisine.', input_method: 'voice',
    }));
    expect(stream.stop).toHaveBeenCalled();
  });

  it('voice: a blocked microphone shows a clear message and typing still works', async () => {
    stream.supported = true;
    stream.failWith = 'not-allowed';
    setup();
    await userEvent.click(screen.getByText('open'));
    await waitFor(() => expect(screen.getByRole('alert').textContent).toMatch(/Micro bloqué/));
    fireEvent.change(screen.getByTestId('justification-text'), { target: { value: 'Écrit à la main' } });
    expect((screen.getByTestId('justification-confirm') as HTMLButtonElement).disabled).toBe(false);
  });

  it('voice: dictation service down says so and falls back to typing', async () => {
    stream.supported = true;
    stream.failWith = 'unavailable';
    setup();
    await userEvent.click(screen.getByText('open'));
    await waitFor(() => expect(screen.getByRole('alert').textContent).toMatch(/Dictée indisponible/));
  });
});
