import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import NouvelAppelModal from '../pages/DispatchBoard/NouvelAppelModal';

const mockMatchAddress = vi.fn();
const mockFetchSectors = vi.fn().mockResolvedValue([{ sector_id: 1, territoire: 'Secteur A', color_code: null }]);
const mockFetchBuildings = vi.fn().mockResolvedValue([{ building_id: 10, adresse: '1580 Perigord', web_building_name: null, sector_id: 1 }]);
const mockFetchUnits = vi.fn().mockResolvedValue([{ unit_id: 100, numero_appartement: '101' }]);
const mockCreateManualRequest = vi.fn();

vi.mock('../api/client', () => ({
  matchAddress: (...args: unknown[]) => mockMatchAddress(...args),
  fetchSectors: (...args: unknown[]) => mockFetchSectors(...args),
  fetchBuildings: (...args: unknown[]) => mockFetchBuildings(...args),
  fetchUnits: (...args: unknown[]) => mockFetchUnits(...args),
  createManualRequest: (...args: unknown[]) => mockCreateManualRequest(...args),
}));

const EXACT_MATCH = {
  match_status: 'exact', building_id: 5, unit_id: 100,
  building_adresse: '1580 Perigord', candidate_building_ids: [], candidate_buildings: [],
};

const NO_MATCH = {
  match_status: 'no_match', building_id: null, unit_id: null,
  building_adresse: null, candidate_building_ids: [], candidate_buildings: [],
};

const AMBIGUOUS_MATCH = {
  match_status: 'ambiguous', building_id: null, unit_id: null,
  building_adresse: null, candidate_building_ids: [20, 21],
  candidate_buildings: [
    { building_id: 20, adresse: '1175 Chamonix (1 à 26)' },
    { building_id: 21, adresse: '1175 Chamonix (27 à 52)' },
  ],
};

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

async function fillAndSubmitForm(opts: { civic?: string; street?: string } = {}) {
  await userEvent.type(screen.getByTestId('caller-name'), 'Jean Tenant');
  await userEvent.type(screen.getByTestId('civic'), opts.civic ?? '1580');
  await userEvent.type(screen.getByTestId('street'), opts.street ?? 'Perigord');
  await userEvent.type(screen.getByTestId('problem'), 'Fuite sous évier');
  await userEvent.click(screen.getByTestId('submit-btn'));
}

describe('NouvelAppelModal', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockFetchSectors.mockResolvedValue([{ sector_id: 1, territoire: 'Secteur A', color_code: null }]);
    mockFetchBuildings.mockResolvedValue([{ building_id: 10, adresse: '1580 Perigord', web_building_name: null, sector_id: 1 }]);
    mockFetchUnits.mockResolvedValue([{ unit_id: 100, numero_appartement: '101' }]);
  });

  it('renders nothing when closed', () => {
    wrap(<NouvelAppelModal open={false} onClose={vi.fn()} />);
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('renders the form when open', () => {
    wrap(<NouvelAppelModal open onClose={vi.fn()} />);
    expect(screen.getByRole('dialog')).toBeTruthy();
    expect(screen.getByTestId('caller-name')).toBeTruthy();
    expect(screen.getByTestId('problem')).toBeTruthy();
    expect(screen.getByTestId('submit-btn')).toBeTruthy();
  });

  it('shows validation error when name is empty on submit', async () => {
    wrap(<NouvelAppelModal open onClose={vi.fn()} />);
    await userEvent.type(screen.getByTestId('problem'), 'Robinet qui coule');
    await userEvent.click(screen.getByTestId('submit-btn'));
    expect(screen.getByTestId('error-msg')).toBeTruthy();
  });

  it('shows validation error when civic/street is empty on submit', async () => {
    wrap(<NouvelAppelModal open onClose={vi.fn()} />);
    await userEvent.type(screen.getByTestId('caller-name'), 'Jean Tenant');
    await userEvent.type(screen.getByTestId('problem'), 'Robinet qui coule');
    // civic and street left empty
    await userEvent.click(screen.getByTestId('submit-btn'));
    expect(screen.getByTestId('error-msg')).toBeTruthy();
    expect(mockMatchAddress).not.toHaveBeenCalled();
  });

  it('step 1 calls matchAddress (not createManualRequest)', async () => {
    mockMatchAddress.mockResolvedValue(EXACT_MATCH);
    wrap(<NouvelAppelModal open onClose={vi.fn()} />);
    await fillAndSubmitForm();
    await waitFor(() => expect(mockMatchAddress).toHaveBeenCalledOnce());
    expect(mockCreateManualRequest).not.toHaveBeenCalled();
  });

  it('exact match shows confirm phase with building address', async () => {
    mockMatchAddress.mockResolvedValue(EXACT_MATCH);
    wrap(<NouvelAppelModal open onClose={vi.fn()} />);
    await fillAndSubmitForm();
    await waitFor(() => expect(screen.getByText(/Adresse trouvée exactement/)).toBeTruthy());
    expect(screen.getByText(/1580 Perigord/)).toBeTruthy();
  });

  it('exact match: confirm calls createManualRequest once with building_id_override', async () => {
    mockMatchAddress.mockResolvedValue(EXACT_MATCH);
    mockCreateManualRequest.mockResolvedValue({ request_id: 42, building_id: 5, unit_id: 100, match_status: 'exact' });
    wrap(<NouvelAppelModal open onClose={vi.fn()} />);
    await fillAndSubmitForm();
    await waitFor(() => screen.getByText(/Adresse trouvée exactement/));
    // Confirmer et créer button
    await userEvent.click(screen.getByTestId('submit-btn'));
    await waitFor(() => expect(mockCreateManualRequest).toHaveBeenCalledOnce());
    const body = mockCreateManualRequest.mock.calls[0][0];
    expect(body.building_id_override).toBe(5);
    expect(body.unit_id_override).toBe(100);
    expect(body.caller_name).toBe('Jean Tenant');
    expect(body.problem).toBe('Fuite sous évier');
  });

  it('submit button disabled while saving (double-submit protection)', async () => {
    mockMatchAddress.mockResolvedValue(EXACT_MATCH);
    let resolveSave!: () => void;
    mockCreateManualRequest.mockReturnValue(
      new Promise(r => { resolveSave = () => r({ request_id: 42, building_id: 5, unit_id: 100, match_status: 'exact' }); })
    );
    wrap(<NouvelAppelModal open onClose={vi.fn()} />);
    await fillAndSubmitForm();
    await waitFor(() => screen.getByText(/Adresse trouvée exactement/));
    await userEvent.click(screen.getByTestId('submit-btn'));
    // Button must be disabled while the save promise is unresolved
    expect((screen.getByTestId('submit-btn') as HTMLButtonElement).disabled).toBe(true);
    resolveSave();
    await waitFor(() => expect(mockCreateManualRequest).toHaveBeenCalledOnce());
  });

  it('no_match shows manual picker, not success message or créée sans bâtiment', async () => {
    mockMatchAddress.mockResolvedValue(NO_MATCH);
    wrap(<NouvelAppelModal open onClose={vi.fn()} />);
    await fillAndSubmitForm({ civic: '9999', street: 'RueInconnue' });
    await waitFor(() => expect(screen.getByText(/Adresse introuvable/)).toBeTruthy());
    expect(screen.queryByTestId('success-msg')).toBeNull();
    // Confirm button disabled without a building selection
    const confirmBtn = screen.getByTestId('submit-btn') as HTMLButtonElement;
    expect(confirmBtn.disabled).toBe(true);
  });

  it('ambiguous shows "Plusieurs bâtiments correspondent" with candidate labels', async () => {
    mockMatchAddress.mockResolvedValue(AMBIGUOUS_MATCH);
    wrap(<NouvelAppelModal open onClose={vi.fn()} />);
    await fillAndSubmitForm({ civic: '1175', street: 'Chamonix' });
    await waitFor(() => expect(screen.getByText(/Plusieurs bâtiments correspondent/)).toBeTruthy());
    expect(screen.getByText(/1175 Chamonix \(1 à 26\)/)).toBeTruthy();
    expect(screen.getByText(/1175 Chamonix \(27 à 52\)/)).toBeTruthy();
  });

  it('ambiguous: confirm button disabled until building selected', async () => {
    mockMatchAddress.mockResolvedValue(AMBIGUOUS_MATCH);
    wrap(<NouvelAppelModal open onClose={vi.fn()} />);
    await fillAndSubmitForm({ civic: '1175', street: 'Chamonix' });
    await waitFor(() => screen.getByText(/Plusieurs bâtiments correspondent/));
    const confirmBtn = screen.getByTestId('submit-btn') as HTMLButtonElement;
    expect(confirmBtn.disabled).toBe(true);
  });

  it('← Modifier goes back to form and does not re-submit', async () => {
    mockMatchAddress.mockResolvedValue(EXACT_MATCH);
    wrap(<NouvelAppelModal open onClose={vi.fn()} />);
    await fillAndSubmitForm();
    await waitFor(() => screen.getByText(/Adresse trouvée exactement/));
    await userEvent.click(screen.getByText(/Modifier/));
    // Back to form: submit-btn text changes to "Vérifier l'adresse"
    expect(screen.getByTestId('caller-name')).toBeTruthy();
    expect(mockCreateManualRequest).not.toHaveBeenCalled();
  });

  it('calls onClose when Cancel is clicked', async () => {
    const onClose = vi.fn();
    wrap(<NouvelAppelModal open onClose={onClose} />);
    await userEvent.click(screen.getByText(/annuler/i));
    expect(onClose).toHaveBeenCalled();
  });

  it('shows units-error when fetchUnits rejects — never a silent empty list', async () => {
    mockMatchAddress.mockResolvedValue(EXACT_MATCH);
    mockFetchUnits.mockRejectedValue(new Error('Network error'));
    wrap(<NouvelAppelModal open onClose={vi.fn()} />);
    await fillAndSubmitForm();
    await waitFor(() => screen.getByText(/Adresse trouvée exactement/));
    await waitFor(() => expect(screen.getByTestId('units-error')).toBeTruthy());
  });
});
