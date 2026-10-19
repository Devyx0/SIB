import { render, screen, act, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, it, expect, vi } from 'vitest';
import { JustificationProvider, useJustify } from '../components/Justification';
import { appendSpoken, finishSentence } from '../hooks/useDictation';
import type { Justification } from '../api/client';

// Minimal stand-in for the browser speech engine.
class FakeRecognition {
  static last: FakeRecognition | null = null;
  lang = '';
  continuous = false;
  interimResults = false;
  maxAlternatives = 1;
  started = 0;
  onresult: ((e: unknown) => void) | null = null;
  onend: (() => void) | null = null;
  onerror: ((e: unknown) => void) | null = null;
  constructor() { FakeRecognition.last = this; }
  start() { this.started += 1; }
  stop() { this.onend?.(); }
  abort() {}
  emit(chunks: Array<{ text: string; final: boolean }>) {
    const results = chunks.map((c) => Object.assign([{ transcript: c.text }], { isFinal: c.final }));
    this.onresult?.({ resultIndex: 0, results });
  }
}

function Harness({ onResult }: { onResult: (j: Justification | null) => void }) {
  const justify = useJustify();
  return (
    <button onClick={async () => onResult(await justify({ decision: 'Urgence', before: 'Aucune', after: 'AJD' }))}>
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
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  delete (window as any).SpeechRecognition;
  FakeRecognition.last = null;
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
    expect(dialog.textContent).toContain('AJD');
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
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (window as any).SpeechRecognition = FakeRecognition;
    const onResult = setup();
    await userEvent.click(screen.getByText('open'));

    const rec = FakeRecognition.last!;
    expect(rec.started).toBe(1);
    expect(rec.lang).toBe('fr-CA');
    expect(rec.continuous).toBe(true);
    expect(rec.interimResults).toBe(true);

    act(() => rec.emit([{ text: 'dégât d’eau', final: false }]));
    expect(screen.getByTestId('justification-interim').textContent).toBe('dégât d’eau');

    act(() => rec.emit([{ text: 'dégât d’eau actif dans la cuisine', final: true }]));
    expect((screen.getByTestId('justification-text') as HTMLTextAreaElement).value)
      .toBe('Dégât d’eau actif dans la cuisine');

    // The browser ends a session after a pause; dictation picks back up.
    act(() => rec.onend?.());
    expect(rec.started).toBe(2);

    await userEvent.click(screen.getByTestId('justification-confirm'));
    await waitFor(() => expect(onResult).toHaveBeenCalledWith({
      text: 'Dégât d’eau actif dans la cuisine.', input_method: 'voice',
    }));
  });

  it('voice: a blocked microphone shows a clear message and typing still works', async () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (window as any).SpeechRecognition = FakeRecognition;
    setup();
    await userEvent.click(screen.getByText('open'));
    act(() => FakeRecognition.last!.onerror?.({ error: 'not-allowed' }));
    expect(screen.getByRole('alert').textContent).toMatch(/Micro bloqué/);
    fireEvent.change(screen.getByTestId('justification-text'), { target: { value: 'Écrit à la main' } });
    expect((screen.getByTestId('justification-confirm') as HTMLButtonElement).disabled).toBe(false);
  });
});
