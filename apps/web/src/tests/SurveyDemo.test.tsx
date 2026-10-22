import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import SurveyPage from '../pages/Survey';

const fetchSurvey = vi.fn();
const submitSurvey = vi.fn();

vi.mock('../api/client', () => ({
  fetchSurvey: (...a: unknown[]) => fetchSurvey(...a),
  submitSurvey: (...a: unknown[]) => submitSurvey(...a),
  ApiError: class ApiError extends Error {},
}));

function wrap(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes><Route path="/sondage/:token" element={<SurveyPage lang="fr" onToggleLang={() => {}} />} /></Routes>
    </MemoryRouter>,
  );
}

describe('Survey demo (dev only)', () => {
  it('/sondage/demo shows a sample survey and never calls the API', async () => {
    wrap('/sondage/demo');
    expect(await screen.findByText(/Marc Tremblay/)).toBeTruthy();
    expect(screen.getByTestId('survey-demo-note')).toBeTruthy();
    await userEvent.click(screen.getByTestId('survey-star-4'));
    await userEvent.click(screen.getAllByRole('radio', { name: 'Oui' })[0]);
    await userEvent.click(screen.getAllByRole('radio', { name: 'Oui' })[1]);
    await userEvent.click(screen.getByTestId('survey-submit'));
    expect(await screen.findByTestId('survey-done')).toBeTruthy();
    expect(fetchSurvey).not.toHaveBeenCalled();
    expect(submitSurvey).not.toHaveBeenCalled();
  });

  it('names each unanswered question and focuses the first one', async () => {
    wrap('/sondage/demo');
    await screen.findByText(/Marc Tremblay/);
    await userEvent.click(screen.getAllByRole('radio', { name: 'Oui' })[0]);
    await userEvent.click(screen.getByTestId('survey-submit'));
    expect(screen.getByText('Choisissez une note de 1 à 5 étoiles.')).toBeTruthy();
    expect(screen.getAllByText('Répondez par oui ou non.')).toHaveLength(1);
    expect(document.activeElement?.id).toBe('survey-star-1');
    expect(screen.queryByTestId('survey-done')).toBeNull();
  });

  it('a real token still loads from the API', async () => {
    fetchSurvey.mockResolvedValue({ token: 'abc', request_id: 1, building_address: null, technician_name: 'Luc', already_submitted: false });
    wrap('/sondage/abc');
    expect(await screen.findByText('Luc')).toBeTruthy();
    expect(fetchSurvey).toHaveBeenCalledWith('abc');
    expect(screen.queryByTestId('survey-demo-note')).toBeNull();
  });
});
