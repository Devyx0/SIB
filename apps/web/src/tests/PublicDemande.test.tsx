import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { useEffect } from 'react';
import PublicDemande from '../pages/PublicDemande';

const lookup = vi.fn();
const submit = vi.fn();

vi.mock('../api/client', () => ({
  publicIntakeLookup: (...a: unknown[]) => lookup(...a),
  publicIntakeSubmit: (...a: unknown[]) => submit(...a),
  ApiError: class ApiError extends Error {
    constructor(public code: string, message: string) { super(message); }
  },
}));

// Turnstile hands back a token straight away in tests.
vi.mock('../components/Turnstile', () => ({
  default: function Turnstile({ onToken, resetKey }: { onToken: (t: string) => void; resetKey?: number }) {
    useEffect(() => { onToken('tok'); }, [onToken, resetKey]);
    return null;
  },
}));

vi.mock('../lib/shrinkImage', () => ({
  shrinkImage: async () => ({ mime: 'image/jpeg', data_base64: 'eA==' }),
}));

const profile = {
  session_token: 's', caller_name: 'Sophie Gagnon', phone: '418 555-0142', email: null,
  address_label: '1240 chemin Sainte-Foy, app. 204', unit_label: '204', pets_allowed: false,
};

async function toStep2() {
  render(<PublicDemande lang="fr" onToggleLang={vi.fn()} />);
  await userEvent.type(screen.getByTestId('public-phone'), '418 555-0142');
  await userEvent.click(screen.getByTestId('public-lookup-btn'));
  await screen.findByTestId('public-autofill');
}

describe('PublicDemande', () => {
  beforeEach(() => {
    lookup.mockReset().mockResolvedValue(profile);
    submit.mockReset().mockResolvedValue({ request_id: 4821 });
    globalThis.URL.createObjectURL = vi.fn(() => `blob:${Math.random()}`);
    globalThis.URL.revokeObjectURL = vi.fn();
  });

  it('step 1 uses a phone keyboard and moves to step 2 on a match', async () => {
    await toStep2();
    expect(lookup).toHaveBeenCalledWith(expect.objectContaining({ phone: '418 555-0142', turnstile_token: 'tok' }));
    expect(screen.getByText('Étape 2 sur 2')).toBeTruthy();
    expect(screen.getByText('Sophie Gagnon')).toBeTruthy();
  });

  it('shows each missing answer under its field and focuses the first one', async () => {
    await toStep2();
    await userEvent.click(screen.getByTestId('public-submit-btn'));
    expect(submit).not.toHaveBeenCalled();
    expect(screen.getByText('Décrivez le problème en quelques mots.')).toBeTruthy();
    expect(screen.getByText('Choisissez ce qui est touché.')).toBeTruthy();
    expect(document.activeElement?.id).toBe('pub-problem');
    expect(screen.getByTestId('public-problem').getAttribute('aria-invalid')).toBe('true');
    // Typing clears that field's message.
    await userEvent.type(screen.getByTestId('public-problem'), 'Fuite');
    expect(screen.queryByText('Décrivez le problème en quelques mots.')).toBeNull();
  });

  it('submits with the themed dropdown and the shared photo picker', async () => {
    await toStep2();
    await userEvent.type(screen.getByTestId('public-problem'), "De l'eau sous l'évier");
    const sel = screen.getByTestId('public-element') as HTMLSelectElement;
    fireEvent.change(sel, { target: { value: sel.options[1].value } });
    await userEvent.type(screen.getByLabelText(/Symptôme/), 'Fuite');
    await userEvent.type(screen.getByLabelText(/Composante/), 'Siphon');
    await userEvent.type(screen.getByLabelText(/Emplacement/), 'Cuisine');
    const photo = new File(['x'], 'evier.jpg', { type: 'image/jpeg' });
    fireEvent.change(screen.getByTestId('photo-input'), { target: { files: [photo] } });
    expect(screen.getByRole('button', { name: 'Retirer la photo 1' })).toBeTruthy();
    await userEvent.click(screen.getByTestId('public-submit-btn'));
    await waitFor(() => expect(submit).toHaveBeenCalled());
    expect(submit.mock.calls[0][0]).toMatchObject({
      problem: "De l'eau sous l'évier", symptome: 'Fuite', composante: 'Siphon', emplacement: 'Cuisine',
      photos: [{ mime: 'image/jpeg', data_base64: 'eA==' }],
    });
    expect(await screen.findByTestId('public-demande-done')).toHaveTextContent('#4821');
  });
});
