import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import NouvelAppelModal from '../pages/DispatchBoard/NouvelAppelModal';

const mockFetchSectors = vi.fn().mockResolvedValue([{ sector_id: 1, territoire: 'Secteur A', color_code: null }]);
const mockFetchBuildings = vi.fn().mockResolvedValue([{ building_id: 10, adresse: '1580 Perigord', web_building_name: null, sector_id: 1 }]);
const mockFetchUnits = vi.fn().mockResolvedValue([{ unit_id: 100, numero_appartement: '101' }]);
const mockCreateManualRequest = vi.fn();

vi.mock('../api/client', () => ({
  fetchSectors: (...args: unknown[]) => mockFetchSectors(...args),
  fetchBuildings: (...args: unknown[]) => mockFetchBuildings(...args),
  fetchUnits: (...args: unknown[]) => mockFetchUnits(...args),
  createManualRequest: (...args: unknown[]) => mockCreateManualRequest(...args),
}));

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
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

  it('shows building picker when toggle clicked', async () => {
    wrap(<NouvelAppelModal open onClose={vi.fn()} />);
    expect(screen.queryByTestId('building-picker')).toBeNull();
    await userEvent.click(screen.getByText(/sélectionner depuis la liste/i));
    expect(screen.getByTestId('building-picker')).toBeTruthy();
  });

  it('shows validation error when name is empty on submit', async () => {
    wrap(<NouvelAppelModal open onClose={vi.fn()} />);
    await userEvent.type(screen.getByTestId('problem'), 'Robinet qui coule');
    await userEvent.click(screen.getByTestId('submit-btn'));
    expect(screen.getByTestId('error-msg')).toBeTruthy();
  });

  it('calls createManualRequest with caller_name and problem', async () => {
    mockCreateManualRequest.mockResolvedValue({ request_id: 42, building_id: 5, unit_id: 100, match_status: 'exact' });

    wrap(<NouvelAppelModal open onClose={vi.fn()} />);
    await userEvent.type(screen.getByTestId('caller-name'), 'Jean Tenant');
    await userEvent.type(screen.getByTestId('civic'), '1580');
    await userEvent.type(screen.getByTestId('street'), 'Perigord');
    await userEvent.type(screen.getByTestId('problem'), 'Fuite sous évier');
    await userEvent.click(screen.getByTestId('submit-btn'));

    await waitFor(() => expect(mockCreateManualRequest).toHaveBeenCalledOnce());
    const body = mockCreateManualRequest.mock.calls[0][0];
    expect(body.caller_name).toBe('Jean Tenant');
    expect(body.problem).toBe('Fuite sous évier');
    expect(body.civic).toBe('1580');
  });

  it('shows success message and picker on no_match result', async () => {
    mockCreateManualRequest.mockResolvedValue({ request_id: 99, building_id: null, unit_id: null, match_status: 'no_match' });

    wrap(<NouvelAppelModal open onClose={vi.fn()} />);
    await userEvent.type(screen.getByTestId('caller-name'), 'Jean Tenant');
    await userEvent.type(screen.getByTestId('civic'), '9999');
    await userEvent.type(screen.getByTestId('street'), 'RueInconnue');
    await userEvent.type(screen.getByTestId('problem'), 'Problème inconnu');
    await userEvent.click(screen.getByTestId('submit-btn'));

    await waitFor(() => expect(screen.getByTestId('success-msg')).toBeTruthy());
    expect(screen.getByTestId('building-picker')).toBeTruthy();
  });

  it('passes building_id_override when building picker is used', async () => {
    mockCreateManualRequest.mockResolvedValue({ request_id: 42, building_id: 10, unit_id: null, match_status: 'building_only' });

    wrap(<NouvelAppelModal open onClose={vi.fn()} />);
    await userEvent.type(screen.getByTestId('caller-name'), 'Marie Tenant');
    await userEvent.type(screen.getByTestId('problem'), 'Chauffage défaillant');

    // Open picker and select sector/building
    await userEvent.click(screen.getByText(/sélectionner depuis la liste/i));
    await waitFor(() => expect(screen.getByTestId('building-picker')).toBeTruthy());

    const sectorSelect = screen.getAllByRole('combobox')[0];
    await userEvent.selectOptions(sectorSelect, '1');
    await waitFor(() => expect(mockFetchBuildings).toHaveBeenCalledWith(1));

    const buildingSelect = screen.getByTestId('building-select');
    await userEvent.selectOptions(buildingSelect, '10');

    await userEvent.click(screen.getByTestId('submit-btn'));
    await waitFor(() => expect(mockCreateManualRequest).toHaveBeenCalledOnce());

    const body = mockCreateManualRequest.mock.calls[0][0];
    expect(body.building_id_override).toBe(10);
  });

  it('calls onClose when Cancel is clicked', async () => {
    const onClose = vi.fn();
    wrap(<NouvelAppelModal open onClose={onClose} />);
    await userEvent.click(screen.getByText(/annuler/i));
    expect(onClose).toHaveBeenCalled();
  });
});
