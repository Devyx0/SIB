import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import NouvelAppelModal from '../pages/DispatchBoard/NouvelAppelModal';

const mockFetchSectors = vi.fn().mockResolvedValue([{ sector_id: 1, territoire: 'Secteur A', color_code: null }]);
const mockFetchBuildings = vi.fn().mockResolvedValue([{ building_id: 10, adresse: '1580 Perigord', web_building_name: null, sector_id: 1 }]);
const mockFetchUnits = vi.fn().mockResolvedValue([{ unit_id: 100, numero_appartement: '101', rue: '1580, rue Perigord' }]);
const mockSearchUnitNumbers = vi.fn();
const mockFetchUnitContext = vi.fn();
const mockCreateManualRequest = vi.fn();

vi.mock('../api/client', () => ({
  fetchSectors: (...args: unknown[]) => mockFetchSectors(...args),
  fetchBuildings: (...args: unknown[]) => mockFetchBuildings(...args),
  fetchUnits: (...args: unknown[]) => mockFetchUnits(...args),
  searchUnitNumbers: (...args: unknown[]) => mockSearchUnitNumbers(...args),
  fetchUnitContext: (...args: unknown[]) => mockFetchUnitContext(...args),
  createManualRequest: (...args: unknown[]) => mockCreateManualRequest(...args),
}));

// jsdom has no canvas/image decoding: stub the shrink step and object URLs.
const mockShrink = vi.fn(async (f: File) => ({ mime: 'image/jpeg' as const, data_base64: `b64-${f.name}` }));
vi.mock('../lib/shrinkImage', () => ({ shrinkImage: (f: File) => mockShrink(f) }));
let urlSeq = 0;
URL.createObjectURL = vi.fn(() => `blob:preview-${++urlSeq}`);
URL.revokeObjectURL = vi.fn();
const photo = (name: string) => new File(['x'], name, { type: 'image/jpeg' });

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

async function fillTaxonomy() {
  await userEvent.selectOptions(screen.getByTestId('element'), "Infiltration d'eau");
  await userEvent.type(screen.getByTestId('symptome'), 'Fuite');
  await userEvent.type(screen.getByTestId('composante'), 'Robinet');
  await userEvent.type(screen.getByTestId('emplacement'), 'Cuisine');
}

async function fillRequired(opts: { phone?: string; problem?: string } = {}) {
  await userEvent.type(screen.getByTestId('caller-name'), 'Jean Tenant');
  await userEvent.type(screen.getByTestId('phone-1'), opts.phone ?? '418-555-0101');
  await userEvent.type(screen.getByTestId('problem'), opts.problem ?? 'Fuite sous évier');
  await fillTaxonomy();
  await selectBuilding();
  await waitFor(() => expect(screen.getByTestId('unit-select')).toBeTruthy());
  await userEvent.selectOptions(screen.getByTestId('unit-select'), '100');
}

async function pickUnitFromSearch(opts: {
  query: string;
  hit: { unit_id: number; unique_unit_number: string; building_adresse: string | null; numero_appartement: string | null };
  context: Record<string, unknown>;
}) {
  mockSearchUnitNumbers.mockResolvedValue([opts.hit]);
  mockFetchUnitContext.mockResolvedValue(opts.context);
  await userEvent.type(screen.getByTestId('unique-unit-number'), opts.query);
  await waitFor(() => expect(mockSearchUnitNumbers).toHaveBeenCalled());
  const list = await screen.findByTestId('unique-unit-suggestions');
  await userEvent.click(list.querySelector('button')!);
  await waitFor(() => expect(mockFetchUnitContext).toHaveBeenCalledWith(opts.hit.unit_id));
}

describe('NouvelAppelModal', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockFetchSectors.mockResolvedValue([{ sector_id: 1, territoire: 'Secteur A', color_code: null }]);
    mockFetchBuildings.mockResolvedValue([{ building_id: 10, adresse: '1580 Perigord', web_building_name: null, sector_id: 1 }]);
    mockFetchUnits.mockResolvedValue([{ unit_id: 100, numero_appartement: '101', rue: '1580, rue Perigord' }]);
    mockSearchUnitNumbers.mockResolvedValue([]);
    mockFetchUnitContext.mockResolvedValue({
      unit_id: 100,
      building_id: 10,
      sector_id: 1,
      unique_unit_number: null,
      numero_appartement: '101',
      rue: null,
      building_adresse: '1580 Perigord',
      pets_allowed: false,
      tenants: [],
    });
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
    expect(screen.getByTestId('unique-unit-number')).toBeTruthy();
    expect(screen.getByTestId('element')).toBeTruthy();
    expect(screen.getByTestId('symptome')).toBeTruthy();
    expect(screen.getByTestId('composante')).toBeTruthy();
    expect(screen.getByTestId('emplacement')).toBeTruthy();
    expect(screen.queryByTestId('intake-urgent')).toBeNull(); // urgent checkbox removed
    expect(screen.queryByTestId('animals-group')).toBeNull();
    expect(screen.queryByTestId('category')).toBeNull();
    await waitFor(() => expect(mockFetchSectors).toHaveBeenCalled());
  });

  it('blocks submit when phone is empty and lists the reason', async () => {
    wrap(<NouvelAppelModal open onClose={vi.fn()} />);
    await userEvent.type(screen.getByTestId('caller-name'), 'Jean');
    await userEvent.type(screen.getByTestId('problem'), 'Fuite');
    await fillTaxonomy();
    await selectBuilding();
    await waitFor(() => expect(screen.getByTestId('unit-select')).toBeTruthy());
    await userEvent.selectOptions(screen.getByTestId('unit-select'), '100');
    await userEvent.click(screen.getByTestId('submit-btn'));
    expect(screen.getByTestId('error-msg').textContent).toMatch(/téléphone|phone/i);
    expect(screen.queryByTestId('block-reasons')).toBeNull();
    expect(mockCreateManualRequest).not.toHaveBeenCalled();
  });

  it('names the missing unit + taxonomy fields on submit, then creates once filled', async () => {
    wrap(<NouvelAppelModal open onClose={vi.fn()} />);
    await userEvent.type(screen.getByTestId('caller-name'), 'Jean');
    await userEvent.type(screen.getByTestId('phone-1'), '418-555-0101');
    await userEvent.type(screen.getByTestId('problem'), 'Fuite');
    await selectBuilding();
    await userEvent.click(screen.getByTestId('submit-btn'));
    expect(screen.getByTestId('error-msg').textContent).toMatch(/unité|unit/i);
    await waitFor(() => expect(screen.getByTestId('unit-select')).toBeTruthy());
    await userEvent.selectOptions(screen.getByTestId('unit-select'), '100');
    await userEvent.selectOptions(screen.getByTestId('element'), "Infiltration d'eau");
    await userEvent.type(screen.getByTestId('symptome'), 'Fuite');
    await userEvent.type(screen.getByTestId('composante'), 'Robinet');
    await userEvent.click(screen.getByTestId('submit-btn'));
    expect(screen.getByTestId('error-msg').textContent).toMatch(/taxonomie|taxonomy/i);
    expect(mockCreateManualRequest).not.toHaveBeenCalled();
    await userEvent.type(screen.getByTestId('emplacement'), 'Cuisine');
    expect((screen.getByTestId('submit-btn') as HTMLButtonElement).disabled).toBe(false);
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
    expect(screen.getByTestId('error-msg').textContent).toMatch(/accès|access/i);
    expect(mockCreateManualRequest).not.toHaveBeenCalled();
  });

  it('searches unique unit numbers and autofills single tenant + pets', async () => {
    wrap(<NouvelAppelModal open onClose={vi.fn()} />);
    await waitFor(() => expect(mockFetchSectors).toHaveBeenCalled());
    await pickUnitFromSearch({
      query: 'U-1',
      hit: {
        unit_id: 100,
        unique_unit_number: 'U-101',
        building_adresse: '1580 Perigord',
        numero_appartement: '101',
      },
      context: {
        unit_id: 100,
        building_id: 10,
        sector_id: 1,
        unique_unit_number: 'U-101',
        numero_appartement: '101',
        rue: '1580, rue Perigord',
        building_adresse: '1580 Perigord',
        pets_allowed: true,
        tenants: [{
          tenant_id: 1,
          name: 'Marie Locataire',
          phone: '418-555-9999',
          email: 'marie@example.com',
        }],
      },
    });
    expect((screen.getByTestId('caller-name') as HTMLInputElement).value).toBe('Marie Locataire');
    expect((screen.getByTestId('phone-1') as HTMLInputElement).value).toBe('418 555-9999');
    expect((screen.getByTestId('caller-email') as HTMLInputElement).value).toBe('marie@example.com');
    expect(screen.getByTestId('animals-group')).toBeTruthy();
    expect(screen.queryByTestId('tenant-select')).toBeNull();
    // The manual address part below the « OU » shows it was filled for you.
    expect(screen.getByTestId('address-autofilled')).toBeTruthy();
    expect((screen.getByTestId('sector-select') as HTMLSelectElement).value).toBe('1');
  });

  it('shows the manual address picker under an OU divider, not marked auto-filled', async () => {
    wrap(<NouvelAppelModal open onClose={vi.fn()} />);
    await waitFor(() => expect(mockFetchSectors).toHaveBeenCalled());
    expect(screen.getByRole('separator', { name: 'ou' }).textContent).toBe('OU');
    expect(screen.getByTestId('sector-select')).toBeTruthy();
    expect(screen.queryByTestId('address-autofilled')).toBeNull();
  });

  it('shows tenant picker when multiple occupants and fills on choose', async () => {
    wrap(<NouvelAppelModal open onClose={vi.fn()} />);
    await waitFor(() => expect(mockFetchSectors).toHaveBeenCalled());
    // First: single-tenant unit fills caller fields.
    await pickUnitFromSearch({
      query: 'Old',
      hit: {
        unit_id: 99,
        unique_unit_number: 'Old-1',
        building_adresse: 'Old St',
        numero_appartement: '1',
      },
      context: {
        unit_id: 99,
        building_id: 10,
        sector_id: 1,
        unique_unit_number: 'Old-1',
        numero_appartement: '1',
        rue: null,
        building_adresse: 'Old St',
        pets_allowed: false,
        tenants: [{
          tenant_id: 50,
          name: 'Myriam Sanogo',
          phone: '418-555-9999',
          email: 'old@example.com',
        }],
      },
    });
    expect((screen.getByTestId('caller-name') as HTMLInputElement).value).toBe('Myriam Sanogo');

    // Then: multi-tenant unit must clear previous caller before pick.
    await userEvent.clear(screen.getByTestId('unique-unit-number'));
    await pickUnitFromSearch({
      query: 'U-1',
      hit: {
        unit_id: 100,
        unique_unit_number: 'U-101',
        building_adresse: '1580 Perigord',
        numero_appartement: '101',
      },
      context: {
        unit_id: 100,
        building_id: 10,
        sector_id: 1,
        unique_unit_number: 'U-101',
        numero_appartement: '101',
        rue: null,
        building_adresse: '1580 Perigord',
        pets_allowed: false,
        tenants: [
          { tenant_id: 1, name: 'Alice', phone: '418-555-0001', email: 'a@example.com' },
          { tenant_id: 2, name: 'Bob', phone: '418-555-0002', email: 'b@example.com' },
        ],
      },
    });
    await waitFor(() => expect(screen.getByTestId('tenant-select')).toBeTruthy());
    expect((screen.getByTestId('caller-name') as HTMLInputElement).value).toBe('');
    expect((screen.getByTestId('phone-1') as HTMLInputElement).value).toBe('');
    expect((screen.getByTestId('caller-email') as HTMLInputElement).value).toBe('');
    await userEvent.selectOptions(screen.getByTestId('tenant-select'), '2');
    expect((screen.getByTestId('caller-name') as HTMLInputElement).value).toBe('Bob');
    expect((screen.getByTestId('phone-1') as HTMLInputElement).value).toBe('418 555-0002');
    expect((screen.getByTestId('caller-email') as HTMLInputElement).value).toBe('b@example.com');
  });

  it('loads pets from lease when unit picked from dropdown', async () => {
    mockFetchUnitContext.mockResolvedValue({
      unit_id: 100,
      building_id: 10,
      sector_id: 1,
      unique_unit_number: 'U-101',
      numero_appartement: '101',
      rue: null,
      building_adresse: '1580 Perigord',
      pets_allowed: true,
      tenants: [{
        tenant_id: 9,
        name: 'Jean Dropdown',
        phone: '418-555-1111',
        email: null,
      }],
    });
    wrap(<NouvelAppelModal open onClose={vi.fn()} />);
    await selectBuilding();
    await waitFor(() => expect(screen.getByTestId('unit-select')).toBeTruthy());
    await userEvent.selectOptions(screen.getByTestId('unit-select'), '100');
    await waitFor(() => expect(mockFetchUnitContext).toHaveBeenCalledWith(100));
    expect(screen.getByTestId('animals-group')).toBeTruthy();
    expect((screen.getByTestId('caller-name') as HTMLInputElement).value).toBe('Jean Dropdown');
    expect((screen.getByTestId('phone-1') as HTMLInputElement).value).toBe('418 555-1111');
  });

  it('hides pets when lease does not allow them', async () => {
    wrap(<NouvelAppelModal open onClose={vi.fn()} />);
    await waitFor(() => expect(mockFetchSectors).toHaveBeenCalled());
    await pickUnitFromSearch({
      query: 'U-1',
      hit: {
        unit_id: 100,
        unique_unit_number: 'U-101',
        building_adresse: '1580 Perigord',
        numero_appartement: '101',
      },
      context: {
        unit_id: 100,
        building_id: 10,
        sector_id: 1,
        unique_unit_number: 'U-101',
        numero_appartement: '101',
        rue: null,
        building_adresse: '1580 Perigord',
        pets_allowed: false,
        tenants: [{ tenant_id: 1, name: 'Jean', phone: '418-555-0101', email: null }],
      },
    });
    expect(screen.queryByTestId('animals-group')).toBeNull();
  });

  it('creates with taxonomy axes and secondary contact', async () => {
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
    expect(body.element).toBe("Infiltration d'eau");
    expect(body.symptome).toBe('Fuite');
    expect(body.composante).toBe('Robinet');
    expect(body.emplacement).toBe('Cuisine');
    expect(body.intake_urgent).toBeUndefined();
    expect(body.animals).toBeUndefined();
    expect(body.access).toBe('yes');
  });

  it('marks photos as recommended and sends them with Créer', async () => {
    mockCreateManualRequest.mockResolvedValue({ request_id: 42, building_id: 10, unit_id: 100, match_status: 'exact' });
    wrap(<NouvelAppelModal open onClose={vi.fn()} />);
    expect(screen.getByTestId('photo-field').textContent).toMatch(/Recommandé/);
    await fillRequired();
    await waitFor(() => expect(screen.getByTestId('unit-select')).toBeTruthy());
    await userEvent.selectOptions(screen.getByTestId('unit-select'), '100');

    fireEvent.change(screen.getByTestId('photo-input'), { target: { files: [photo('evier.jpg'), photo('armoire.jpg')] } });
    expect(screen.getAllByRole('img', { name: /Photo \d/ })).toHaveLength(2);
    await userEvent.click(screen.getByRole('button', { name: 'Retirer la photo 1' }));
    expect(screen.getAllByRole('img', { name: /Photo \d/ })).toHaveLength(1);

    await userEvent.click(screen.getByTestId('submit-btn'));
    await waitFor(() => expect(mockCreateManualRequest).toHaveBeenCalledOnce());
    expect(mockCreateManualRequest.mock.calls[0][0].photos).toEqual([
      { mime: 'image/jpeg', data_base64: 'b64-armoire.jpg' },
    ]);
  });

  it('caps photos at 5 and hides the add tile when full', () => {
    wrap(<NouvelAppelModal open onClose={vi.fn()} />);
    const files = ['a', 'b', 'c', 'd', 'e', 'f', 'g'].map((n) => photo(`${n}.jpg`));
    fireEvent.change(screen.getByTestId('photo-input'), { target: { files } });
    expect(screen.getAllByRole('img', { name: /Photo \d/ })).toHaveLength(5);
    expect(screen.queryByTestId('add-photo')).toBeNull();
  });

  it('sends no photos field when none were added', async () => {
    mockCreateManualRequest.mockResolvedValue({ request_id: 43, building_id: 10, unit_id: 100, match_status: 'exact' });
    wrap(<NouvelAppelModal open onClose={vi.fn()} />);
    await fillRequired();
    await waitFor(() => expect(screen.getByTestId('unit-select')).toBeTruthy());
    await userEvent.selectOptions(screen.getByTestId('unit-select'), '100');
    await userEvent.click(screen.getByTestId('submit-btn'));
    await waitFor(() => expect(mockCreateManualRequest).toHaveBeenCalledOnce());
    expect(mockCreateManualRequest.mock.calls[0][0].photos).toBeUndefined();
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

describe('NouvelAppelModal — technician note', () => {
  it('shows « Information importante pour le technicien » right under the problem, without a warning icon', () => {
    wrap(<NouvelAppelModal open onClose={vi.fn()} />);
    const note = screen.getByLabelText('Information importante pour le technicien');
    expect(note.tagName).toBe('TEXTAREA');
    const problem = screen.getByTestId('problem');
    // Same section, straight after the description field.
    expect(problem.closest('div')?.nextElementSibling?.contains(note)).toBe(true);
    expect(screen.queryByText('⚠')).toBeNull();
    expect(screen.queryByText(/ATTENTION/)).toBeNull();
  });
});
