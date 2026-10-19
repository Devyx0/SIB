import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import NouvelAppelModal from '../pages/DispatchBoard/NouvelAppelModal';

const mockFetchSectors = vi.fn().mockResolvedValue([{ sector_id: 1, territoire: 'Secteur A', color_code: null }]);
const mockFetchBuildings = vi.fn().mockResolvedValue([{ building_id: 10, adresse: '1580 Perigord', web_building_name: null, sector_id: 1 }]);
const mockFetchUnits = vi.fn().mockResolvedValue([{ unit_id: 100, numero_appartement: '101', rue: '1580, rue Perigord' }]);
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

async function selectBuilding(buildingId = '10') {
  await waitFor(() => expect(mockFetchSectors).toHaveBeenCalled());
  const sectorSelect = screen.getByTestId('sector-select');
  await userEvent.selectOptions(sectorSelect, '1');
  const buildingSelect = await screen.findByTestId('building-select');
  await userEvent.selectOptions(buildingSelect, buildingId);
}

async function fillRequired(opts: { phone?: string; problem?: string } = {}) {
  await userEvent.type(screen.getByTestId('caller-name'), 'Jean Tenant');
  await userEvent.type(screen.getByTestId('phone-1'), opts.phone ?? '418-555-0101');
  await userEvent.type(screen.getByTestId('problem'), opts.problem ?? 'Fuite sous évier');
  await selectBuilding();
}

describe('NouvelAppelModal', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockFetchSectors.mockResolvedValue([{ sector_id: 1, territoire: 'Secteur A', color_code: null }]);
    mockFetchBuildings.mockResolvedValue([{ building_id: 10, adresse: '1580 Perigord', web_building_name: null, sector_id: 1 }]);
    mockFetchUnits.mockResolvedValue([{ unit_id: 100, numero_appartement: '101', rue: '1580, rue Perigord' }]);
  });

  it('renders nothing when closed', () => {
    wrap(<NouvelAppelModal open={false} onClose={vi.fn()} />);
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('renders the form when open', async () => {
    wrap(<NouvelAppelModal open onClose={vi.fn()} />);
    expect(screen.getByRole('dialog')).toBeTruthy();
    expect(screen.getByTestId('caller-name')).toBeTruthy();
    expect(screen.getByTestId('phone-1')).toBeTruthy();
    expect(screen.getByTestId('phone-2')).toBeTruthy();
    expect(screen.getByTestId('access-group')).toBeTruthy();
    expect(screen.getByTestId('animals-group')).toBeTruthy();
    expect(screen.getByTestId('category')).toBeTruthy();
    await waitFor(() => expect(mockFetchSectors).toHaveBeenCalled());
  });

  it('shows validation error when phone is empty', async () => {
    wrap(<NouvelAppelModal open onClose={vi.fn()} />);
    await userEvent.type(screen.getByTestId('caller-name'), 'Jean');
    await userEvent.type(screen.getByTestId('problem'), 'Fuite');
    await selectBuilding();
    await userEvent.click(screen.getByTestId('submit-btn'));
    expect(screen.getByTestId('error-msg')).toBeTruthy();
    expect(mockCreateManualRequest).not.toHaveBeenCalled();
  });

  it('rejects mismatched email confirmation', async () => {
    wrap(<NouvelAppelModal open onClose={vi.fn()} />);
    await fillRequired();
    await userEvent.type(screen.getByTestId('caller-email'), 'a@example.com');
    await userEvent.type(screen.getByTestId('caller-email-confirm'), 'b@example.com');
    await userEvent.click(screen.getByTestId('submit-btn'));
    expect(screen.getByTestId('error-msg').textContent).toMatch(/courriels|emails/i);
    expect(mockCreateManualRequest).not.toHaveBeenCalled();
  });

  it('requires access instructions when yes_instructions selected', async () => {
    wrap(<NouvelAppelModal open onClose={vi.fn()} />);
    await fillRequired();
    const radios = screen.getByTestId('access-group').querySelectorAll('input[type="radio"]');
    await userEvent.click(radios[1]); // yes_instructions
    await waitFor(() => expect(screen.getByTestId('access-details')).toBeTruthy());
    await userEvent.click(screen.getByTestId('submit-btn'));
    expect(screen.getByTestId('error-msg')).toBeTruthy();
    expect(mockCreateManualRequest).not.toHaveBeenCalled();
  });

  it('creates with phone_2, secondary contact, category', async () => {
    mockCreateManualRequest.mockResolvedValue({ request_id: 42, building_id: 10, unit_id: 100, match_status: 'exact' });
    wrap(<NouvelAppelModal open onClose={vi.fn()} />);
    await fillRequired();
    await userEvent.type(screen.getByTestId('phone-2'), '418-555-0202');
    await userEvent.type(screen.getByTestId('caller-email'), 'a@example.com');
    await userEvent.type(screen.getByTestId('caller-email-confirm'), 'a@example.com');
    await userEvent.type(screen.getByTestId('secondary-name'), 'Marie');
    await userEvent.type(screen.getByTestId('secondary-email'), 'marie@example.com');
    await waitFor(() => expect(screen.getByTestId('unit-select')).toBeTruthy());
    await userEvent.selectOptions(screen.getByTestId('unit-select'), '100');
    await userEvent.click(screen.getByTestId('submit-btn'));
    await waitFor(() => expect(mockCreateManualRequest).toHaveBeenCalledOnce());
    const body = mockCreateManualRequest.mock.calls[0][0];
    expect(body.building_id).toBe(10);
    expect(body.unit_id).toBe(100);
    expect(body.phone_1).toBe('418-555-0101');
    expect(body.phone_2).toBe('418-555-0202');
    expect(body.caller_email).toBe('a@example.com');
    expect(body.secondary_name).toBe('Marie');
    expect(body.secondary_email).toBe('marie@example.com');
    expect(body.category).toBe('Entretien général et maintenance');
    expect(body.access).toBe('yes');
  });

  it('submit button disabled while saving', async () => {
    let resolveSave!: () => void;
    mockCreateManualRequest.mockReturnValue(
      new Promise(r => { resolveSave = () => r({ request_id: 42, building_id: 10, unit_id: null, match_status: 'building_only' }); })
    );
    wrap(<NouvelAppelModal open onClose={vi.fn()} />);
    await fillRequired({ problem: 'Fuite' });
    await userEvent.click(screen.getByTestId('submit-btn'));
    expect((screen.getByTestId('submit-btn') as HTMLButtonElement).disabled).toBe(true);
    resolveSave();
    await waitFor(() => expect(mockCreateManualRequest).toHaveBeenCalledOnce());
  });

  it('calls onClose when Cancel is clicked', async () => {
    const onClose = vi.fn();
    wrap(<NouvelAppelModal open onClose={onClose} />);
    await userEvent.click(screen.getByText(/annuler/i));
    expect(onClose).toHaveBeenCalled();
  });

  it('shows units-error when fetchUnits rejects', async () => {
    mockFetchUnits.mockRejectedValue(new Error('Network error'));
    wrap(<NouvelAppelModal open onClose={vi.fn()} />);
    await selectBuilding();
    await waitFor(() => expect(screen.getByTestId('units-error')).toBeTruthy());
  });

  it('shows Aucune unité message when building has no units', async () => {
    mockFetchUnits.mockResolvedValue([]);
    wrap(<NouvelAppelModal open onClose={vi.fn()} />);
    await selectBuilding();
    await waitFor(() => expect(screen.getByTestId('no-units-msg')).toBeTruthy());
    expect(screen.queryByTestId('unit-select')).toBeNull();
  });
});
