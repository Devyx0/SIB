import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import Portfolio from '../pages/Portfolio';
import type {
  PortfolioBuildingDetail,
  PortfolioProjectDetail,
  PortfolioSectorDetail,
  PortfolioSearchResult,
  PortfolioSectorSummary,
  PortfolioUnitDetail,
  PortfolioUnitListPage,
  TenantTurnover,
  Turnover,
} from '../api/schema.d.ts';

vi.mock('../api/client', () => ({
  fetchPortfolioSectors: vi.fn(),
  fetchPortfolioSector: vi.fn(),
  fetchPortfolioProject: vi.fn(),
  fetchPortfolioBuilding: vi.fn(),
  fetchPortfolioUnit: vi.fn(),
  fetchTenantTurnover: vi.fn(),
  searchPortfolio: vi.fn(),
  fetchPortfolioUnits: vi.fn(),
  createProject: vi.fn(),
  updateProject: vi.fn(),
  createBuilding: vi.fn(),
  updateBuilding: vi.fn(),
  createUnit: vi.fn(),
  updateUnit: vi.fn(),
  setFicheEntry: vi.fn(),
  createPaintSpec: vi.fn(),
  updatePaintSpec: vi.fn(),
  deletePaintSpec: vi.fn(),
  createBuildingDocument: vi.fn(),
  deleteBuildingDocument: vi.fn(),
  ApiError: class ApiError extends Error {
    constructor(public code: string, message: string) { super(message); }
  },
}));

import {
  fetchPortfolioBuilding,
  fetchPortfolioProject,
  fetchPortfolioSector,
  fetchPortfolioSectors,
  fetchPortfolioUnit,
  fetchPortfolioUnits,
  fetchTenantTurnover,
  searchPortfolio,
  createProject,
  createUnit,
  setFicheEntry,
  createPaintSpec,
  updateBuilding,
  updateUnit,
} from '../api/client';

const sectors: PortfolioSectorSummary[] = [
  { sector_id: 1, territoire: 'Haute-Ville', color_code: '5', project_count: 2, building_count: 3,
    unit_count: 40, occupied_unit_count: 38, top_projects: ['Projet Cartier', 'Projet Murray'] },
  { sector_id: 2, territoire: 'Inconnu', color_code: null, project_count: 1, building_count: 1,
    unit_count: 10, occupied_unit_count: 10, top_projects: ['Projet Lévis'] },
  { sector_id: 3, territoire: 'Lévis-Est', color_code: '6', project_count: 5, building_count: 6,
    unit_count: 50, occupied_unit_count: 47, top_projects: ['A', 'B', 'C'] },
];

const sector: PortfolioSectorDetail = {
  sector_id: 1, territoire: 'Haute-Ville', color_code: '5', project_count: 2, building_count: 3,
  projects: [
    { project_id: 10, nom_unique_projet: 'Projet Cartier', adresse_quickbooks: '10 rue Cartier',
      accounting_project_number: '1010', building_count: 2 },
    { project_id: 11, nom_unique_projet: 'Projet Murray', adresse_quickbooks: null,
      accounting_project_number: null, building_count: 1 },
  ],
};

const project: PortfolioProjectDetail = {
  project_id: 10, nom_unique_projet: 'Projet Cartier', adresse_quickbooks: '10 rue Cartier',
  accounting_project_number: '1010', building_count: 1,
  buildings: [{
    building_id: 100, project_id: 10, sector_id: 1, adresse: '10 rue Cartier', ville: 'Québec',
    code_postal: 'G1R 2S1', web_building_name: 'Le Cartier', actif_inactif: 'Actif', unit_count: 2,
  }],
};

const building: PortfolioBuildingDetail = {
  building_id: 100, project_id: 10, sector_id: 1, adresse: '10 rue Cartier', ville: 'Québec',
  code_postal: 'G1R 2S1', web_building_name: 'Le Cartier', actif_inactif: 'Actif',
  nb_logements: '2', nb_etages: '3', annee_construction: '1965',
  territoire: 'Haute-Ville', nom_unique_projet: 'Projet Cartier', unit_count: 2,
  units: [
    { unit_id: 1000, numero_appartement: '101', unique_unit_number: '10-101', rue: '10, rue Cartier', grandeur: '4 1/2',
      tenant_names: ['Ada Lovelace', 'Grace Hopper'], occupant_count: 2, lease_statut: 'Régulier' },
    { unit_id: 1001, numero_appartement: '102', unique_unit_number: null, rue: '10, rue Cartier', grandeur: '3 1/2',
      tenant_names: [], occupant_count: 0, lease_statut: null },
  ],
  reference: {
    chauffage: 'Central Hot Water (Gas)', chauffage_details: null, chauffe_eau: null, systeme_incendie: null,
    boite_a_cle_ext: null, boite_a_cle_int: null, internet: null, furnished: null, building_structure: null,
    property_type: null, ascenseur: false, nb_elevateurs: null, piscine: null, sauna: null, gym: null,
    dogs_allowed: true,
  },
  fiche: [
    { label: 'Code de peinture', value: 'SW 7005' },
    { label: 'Toiture', value: 'Membrane avec gravier' },
  ],
  paint_specs: [{ paint_spec_id: 9, zone: 'LOGEMENTS', surface_label: 'Murs', product_interior: 'promar200 sw7017',
                  product_exterior: null, manufacturer: 'Sherwin William' }],
  documents: [],
};

const unit: PortfolioUnitDetail = {
  unit_id: 1000, building_id: 100, project_id: 10, sector_id: 1,
  numero_appartement: '101', rue: '10, rue Cartier', grandeur: '4 1/2',
  building_adresse: '10 rue Cartier', web_building_name: 'Le Cartier',
  nom_unique_projet: 'Projet Cartier', territoire: 'Haute-Ville', unique_unit_number: '10-101',
  paint_specs: [], paint_notes: [{ label: 'Code de peinture', value: 'SW 7005' }],
  lease: { lease_id: 5, debut_bail: '2026-07-01', fin_bail: '2027-06-30', statut: 'Régulier', langue_bail: 'Français' },
  tenants: [{
    tenant_id: 7, nom_complet: 'Ada Lovelace', telephone: '418-555-0199',
    telephone_international: '+14185550199', courriel: 'ada@example.test', capacite: 'named_on_lease',
    has_turnover: true,
  }, {
    tenant_id: 8, nom_complet: 'Grace Hopper', telephone: null,
    telephone_international: null, courriel: null, capacite: 'named_on_lease',
    has_turnover: false,
  }],
};

const blankTurnover: Turnover = {
  turnover_id: 1, tenant_role: null, move_reason: null, outgoing_tenant_name: null,
  lease_end_date: null, move_out_confirmed_date: null, move_out_time: null, key_return_method: null,
  assignment_desired_date: null, outgoing_loyer: null, outgoing_fin_bail: null,
  incoming_tenant_name: null, lease_start_date: null, move_in_confirmed_date: null, move_in_time: null,
  key_pickup_method: null, intercom_status: null, cleaning_status: null, parking_remote_status: null,
  parking_stall_current: null, parking_stall_new: null, internet_transfer_current: null,
  internet_transfer_new: null, furnished_status_current: null, furnished_status_new: null,
  room_count: null, mattress_size: null, pre_departure_inspection_notes: null, general_notes: null,
  settlement: null, furniture: [],
};

const turnover: TenantTurnover = {
  unit_id: 1000,
  tenant: unit.tenants[0],
  turnovers: [{
    ...blankTurnover, turnover_id: 44, tenant_role: 'incoming',
    incoming_tenant_name: 'Ada Lovelace', outgoing_tenant_name: 'Charles Babbage',
    lease_start_date: '2026-07-01', move_in_confirmed_date: '2026-07-01',
    lease_end_date: '2026-06-30', outgoing_loyer: '958.00', intercom_status: 'done',
  }],
  other_turnovers: [{ ...blankTurnover, turnover_id: 12, incoming_tenant_name: 'Charles Babbage' }],
};

const searchResult: PortfolioSearchResult = {
  q: 'peinture cartier',
  units: [{ unit_id: 1000, building_id: 100, numero_appartement: '101', unique_unit_number: '10-101',
            rue: '10, rue Cartier', grandeur: '4 1/2', building_adresse: '10 rue Cartier',
            tenant_names: ['Ada Lovelace', 'Grace Hopper'], occupant_count: 2 }],
  buildings: [],
  projects: [],
  tenants: [],
  facts: [{ building_id: 100, building_adresse: '10 rue Cartier', web_building_name: 'Le Cartier',
            label: 'Code de peinture', value: 'SW 7005 Pure White', source: 'fiche' }],
};

const unitPage: PortfolioUnitListPage = {
  items: [{ unit_id: 1001, building_id: 100, project_id: 10, sector_id: 1, numero_appartement: '102',
            unique_unit_number: null, rue: '10, rue Cartier', grandeur: '3 1/2',
            building_adresse: '10 rue Cartier', nom_unique_projet: 'Projet Cartier', territoire: 'Haute-Ville',
            lease_statut: null, fin_bail: null, tenant_names: [], occupant_count: 0 }],
  total: 1, vacant_total: 1, grandeur_options: ['3 1/2', '4 1/2'], page: 1, page_size: 50,
};

function LocationProbe() {
  const loc = useLocation();
  return <span data-testid="location">{loc.pathname + loc.search}</span>;
}

function wrap(path: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/portfolio/*" element={<Portfolio lang="fr" />} />
        </Routes>
        <LocationProbe />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('Portfolio', () => {
  beforeEach(() => {
    vi.mocked(fetchPortfolioSectors).mockReset().mockResolvedValue(sectors);
    vi.mocked(fetchPortfolioSector).mockReset().mockResolvedValue(sector);
    vi.mocked(fetchPortfolioProject).mockReset().mockResolvedValue(project);
    vi.mocked(fetchPortfolioBuilding).mockReset().mockResolvedValue(building);
    vi.mocked(fetchPortfolioUnit).mockReset().mockResolvedValue(unit);
    vi.mocked(fetchTenantTurnover).mockReset().mockResolvedValue(turnover);
    vi.mocked(searchPortfolio).mockReset().mockResolvedValue(searchResult);
    vi.mocked(fetchPortfolioUnits).mockReset().mockResolvedValue(unitPage);
  });

  it('drills from sectors down to a tenant turnover', async () => {
    const user = userEvent.setup();
    wrap('/portfolio');

    const sectorCards = await screen.findAllByTestId('sector-card');
    expect(sectorCards).toHaveLength(3);
    await user.click(screen.getByText('Haute-Ville'));
    expect(screen.getByTestId('location')).toHaveTextContent('/portfolio/secteurs/1');

    await user.click(await screen.findByText('Projet Cartier'));
    expect(screen.getByTestId('location')).toHaveTextContent('/portfolio/secteurs/1/projets/10');
    expect(fetchPortfolioProject).toHaveBeenCalledWith(10, 1);

    await user.click(await screen.findByRole('link', { name: '10 rue Cartier' }));
    expect(screen.getByTestId('location')).toHaveTextContent('/portfolio/batiments/100');

    const rows = await screen.findAllByTestId('unit-row');
    expect(rows).toHaveLength(2);
    expect(within(rows[0]).getByText('Ada Lovelace, Grace Hopper')).toBeTruthy();
    expect(within(rows[1]).getByText('Aucun locataire')).toBeTruthy();
    await user.click(rows[0]);
    expect(screen.getByTestId('location')).toHaveTextContent('/portfolio/unites/1000');

    await user.click(await screen.findByRole('button', { name: 'Ada Lovelace' }));
    expect(screen.getByTestId('location')).toHaveTextContent('/portfolio/unites/1000?locataire=7');
    const dialog = await screen.findByTestId('turnover-dialog');
    expect(fetchTenantTurnover).toHaveBeenCalledWith(1000, 7);
    const [card] = await within(dialog).findAllByTestId('turnover-card');
    expect(within(card).getByText('Arrivée')).toBeTruthy();
    expect(within(card).getByText('Charles Babbage')).toBeTruthy();
    expect(within(card).getByText('Fait')).toBeTruthy(); // intercom label
    expect(within(dialog).getByText(/Autres roulements de ce logement \(1\)/)).toBeTruthy();

    await user.click(within(dialog).getByTestId('turnover-close'));
    expect(screen.queryByTestId('turnover-dialog')).toBeNull();
    expect(screen.getByTestId('location')).toHaveTextContent('/portfolio/unites/1000');
  });

  it('summarises the portfolio and each sector, unknown sector last', async () => {
    wrap('/portfolio');
    const totals = await screen.findByTestId('portfolio-totals');
    expect(within(totals).getByText('100')).toBeTruthy(); // units
    expect(within(totals).getByText('95 %')).toBeTruthy(); // 95 of 100 occupied
    expect(within(totals).getByText('5 vacants')).toBeTruthy();
    const cards = screen.getAllByTestId('sector-card');
    expect(cards.map((c) => c.querySelector('h2')?.textContent)).toEqual(['Haute-Ville', 'Lévis-Est', 'Inconnu']);
    expect(within(cards[0]).queryByText(/%/)).toBeNull(); // occupancy only in the totals
    expect(within(cards[1]).getByText('+2')).toBeTruthy(); // 5 projects, 3 shown
  });

  it('breadcrumb links back up the hierarchy from a unit', async () => {
    wrap('/portfolio/unites/1000');
    const crumbs = await screen.findByTestId('breadcrumbs');
    await within(crumbs).findByText('10 rue Cartier');
    const links = within(crumbs).getAllByRole('link').map((a) => a.getAttribute('href'));
    expect(links).toEqual([
      '/portfolio',
      '/portfolio/secteurs/1',
      '/portfolio/secteurs/1/projets/10',
      '/portfolio/batiments/100',
    ]);
    expect(within(crumbs).getByText('Logement 101')).toHaveAttribute('aria-current', 'page');
  });

  it('marks only the tenants who have a turnover', async () => {
    wrap('/portfolio/unites/1000');
    const rows = await screen.findAllByTestId('tenant-row');
    expect(within(rows[0]).getByTestId('turnover-flag')).toHaveTextContent('Roulement');
    expect(within(rows[1]).queryByTestId('turnover-flag')).toBeNull();
  });

  it('opens the turnover panel from the URL and closes it with Escape', async () => {
    const user = userEvent.setup();
    wrap('/portfolio/unites/1000?locataire=7');
    expect(await screen.findByTestId('turnover-dialog')).toBeTruthy();
    await user.keyboard('{Escape}');
    expect(screen.queryByTestId('turnover-dialog')).toBeNull();
  });

  it('says so when the tenant has no turnover and opens the unit history', async () => {
    vi.mocked(fetchTenantTurnover).mockResolvedValue({ ...turnover, turnovers: [] });
    wrap('/portfolio/unites/1000?locataire=7');
    expect(await screen.findByTestId('turnover-empty')).toBeTruthy();
    const details = screen.getByText(/Autres roulements/).closest('details');
    expect(details).toHaveAttribute('open');
  });

  it('filters units with the search box', async () => {
    const many = {
      ...building,
      units: Array.from({ length: 10 }, (_, i) => ({
        ...building.units[0], unit_id: 2000 + i, numero_appartement: String(200 + i),
        tenant_names: [i === 3 ? 'Émile Nelligan' : `Locataire ${i}`],
      })),
    };
    vi.mocked(fetchPortfolioBuilding).mockResolvedValue(many);
    const user = userEvent.setup();
    wrap('/portfolio/batiments/100');
    expect(await screen.findAllByTestId('unit-row')).toHaveLength(10);
    await user.type(screen.getByTestId('portfolio-search'), 'emile');
    expect(screen.getAllByTestId('unit-row')).toHaveLength(1);
  });

  it('shows a not-found message for a sector outside scope', async () => {
    vi.mocked(fetchPortfolioSector).mockRejectedValue(Object.assign(new Error('x'), { code: 'NOT_FOUND' }));
    wrap('/portfolio/secteurs/9');
    expect(await screen.findByText('Introuvable ou hors de votre secteur.')).toBeTruthy();
  });

  it('searches the whole portfolio and opens a building fact', async () => {
    const user = userEvent.setup();
    wrap('/portfolio');
    await user.type(screen.getByTestId('portfolio-global-search'), 'peinture cartier');
    const results = await screen.findByTestId('portfolio-search-results');
    await within(results).findByText('Code de peinture : SW 7005 Pure White');
    expect(searchPortfolio).toHaveBeenLastCalledWith('peinture cartier');
    expect(within(results).getByText('Ada Lovelace, Grace Hopper')).toBeTruthy();
    // The first hit is active; Enter opens it.
    await user.keyboard('{Enter}');
    expect(screen.getByTestId('location')).toHaveTextContent('/portfolio/batiments/100');
  });

  it('shows the global search on the sectors page only', async () => {
    wrap('/portfolio');
    expect(screen.getByTestId('portfolio-global-search')).toBeTruthy();
    expect(screen.getByTestId('all-units-link')).toBeTruthy();
  });

  it('has no global search on an inner page', async () => {
    wrap('/portfolio/batiments/100');
    expect(await screen.findAllByTestId('unit-row')).not.toHaveLength(0);
    expect(screen.queryByTestId('portfolio-global-search')).toBeNull();
  });

  it('moves through search results with the arrow keys', async () => {
    const user = userEvent.setup();
    wrap('/portfolio');
    await user.type(screen.getByTestId('portfolio-global-search'), 'cartier');
    await screen.findByText('Code de peinture : SW 7005 Pure White');
    await user.keyboard('{ArrowDown}{Enter}');
    expect(screen.getByTestId('location')).toHaveTextContent('/portfolio/unites/1000');
  });

  it('links the vacant total to the filtered unit list', async () => {
    const user = userEvent.setup();
    wrap('/portfolio');
    await user.click(await screen.findByTestId('vacant-link'));
    expect(screen.getByTestId('location')).toHaveTextContent('/portfolio/logements?occupation=vacant');
    expect(await screen.findAllByTestId('units-row')).toHaveLength(1);
    expect(fetchPortfolioUnits).toHaveBeenLastCalledWith(expect.objectContaining({ occupancy: 'vacant', page: 1 }));
    expect(screen.getByTestId('occ-vacant')).toHaveAttribute('aria-pressed', 'true');
  });

  it('keeps unit list filters in the URL and resets them', async () => {
    const user = userEvent.setup();
    wrap('/portfolio/logements?secteur=1&occupation=vacant&page=2');
    await screen.findAllByTestId('units-row');
    expect(fetchPortfolioUnits).toHaveBeenLastCalledWith(
      expect.objectContaining({ sector_id: 1, occupancy: 'vacant', page: 2 }));
    // Changing a filter goes back to page 1.
    await user.click(screen.getByTestId('occ-occupe'));
    expect(screen.getByTestId('location')).toHaveTextContent('/portfolio/logements?secteur=1&occupation=occupe');
    await user.click(screen.getByTestId('units-reset'));
    expect(screen.getByTestId('location').textContent).toBe('/portfolio/logements');
  });

  it('filters a building to its vacant units', async () => {
    const user = userEvent.setup();
    wrap('/portfolio/batiments/100');
    expect(await screen.findAllByTestId('unit-row')).toHaveLength(2);
    await user.click(screen.getByTestId('building-occ-vacant'));
    const rows = screen.getAllByTestId('unit-row');
    expect(rows).toHaveLength(1);
    expect(within(rows[0]).getByText('Aucun locataire')).toBeTruthy();
  });

  it('shows the building info and saves an edited fiche line', async () => {
    vi.mocked(setFicheEntry).mockReset().mockResolvedValue(undefined);
    const user = userEvent.setup();
    wrap('/portfolio/batiments/100');
    const fiche = await screen.findByTestId('building-fiche');
    expect(within(fiche).getByText('Membrane avec gravier')).toBeTruthy();
    expect(within(screen.getByTestId('building-paint')).getByText('promar200 sw7017')).toBeTruthy();
    expect(within(screen.getByTestId('building-characteristics')).getByText('Oui')).toBeTruthy(); // dogs

    const row = within(fiche).getAllByTestId('fiche-row')[0];
    await user.click(within(row).getByTestId('edit-fiche'));
    const box = within(fiche).getByRole('textbox');
    await user.clear(box);
    await user.type(box, 'SW 7006');
    await user.click(within(fiche).getByRole('button', { name: 'Enregistrer' }));
    expect(setFicheEntry).toHaveBeenCalledWith(100, {
      label: 'Code de peinture', value: 'SW 7006', current_value: 'SW 7005',
    });
  });

  it('shows a stale-data message when the fiche changed meanwhile', async () => {
    vi.mocked(setFicheEntry).mockReset().mockRejectedValue(Object.assign(new Error('x'), { code: 'STALE_DATA' }));
    const user = userEvent.setup();
    wrap('/portfolio/batiments/100');
    const fiche = await screen.findByTestId('building-fiche');
    await user.click(within(within(fiche).getAllByTestId('fiche-row')[1]).getByTestId('edit-fiche'));
    await user.type(within(fiche).getByRole('textbox'), '!');
    await user.click(within(fiche).getByRole('button', { name: 'Enregistrer' }));
    expect(await within(fiche).findByRole('alert')).toHaveTextContent(/rechargez la page/);
  });

  it('adds a paint spec and sends only changed characteristics', async () => {
    vi.mocked(createPaintSpec).mockReset().mockResolvedValue({} as never);
    vi.mocked(updateBuilding).mockReset().mockResolvedValue(undefined);
    const user = userEvent.setup();
    wrap('/portfolio/batiments/100');
    const paint = await screen.findByTestId('building-paint');
    await user.click(within(paint).getByTestId('add-paint'));
    const form = within(paint).getByTestId('paint-form');
    await user.type(within(form).getByLabelText('Zone'), 'CORRIDORS');
    await user.type(within(form).getByLabelText('Produit intérieur'), 'SW 7004');
    await user.click(within(form).getByRole('button', { name: 'Enregistrer' }));
    expect(createPaintSpec).toHaveBeenCalledWith(100, expect.objectContaining({
      zone: 'CORRIDORS', product_interior: 'SW 7004',
    }));

    const chars = screen.getByTestId('building-characteristics');
    await user.click(within(chars).getByTestId('edit-characteristics'));
    await user.type(within(chars).getByLabelText('Chauffe-eau'), 'Gaz');
    await user.click(within(chars).getByRole('button', { name: 'Enregistrer' }));
    expect(updateBuilding).toHaveBeenCalledWith(100, {
      changes: { chauffe_eau: 'Gaz' }, current: { chauffe_eau: null },
    });
  });

  it('creates a project with its first building and opens it', async () => {
    vi.mocked(createProject).mockReset().mockResolvedValue({
      project_id: 77, building_id: 700, sector_id: 1, unit_id: null, paint_spec_id: null, document_id: null,
    });
    const user = userEvent.setup();
    wrap('/portfolio/secteurs/1');
    await user.click(await screen.findByTestId('add-project'));
    const dialog = screen.getByTestId('project-dialog');
    await user.type(within(dialog).getByLabelText('Nom du projet *'), 'Projet Neuf');
    await user.type(within(dialog).getByLabelText(/^Adresse \*/), '5 rue Neuve');
    await user.click(within(dialog).getByTestId('form-submit'));
    expect(createProject).toHaveBeenCalledWith(expect.objectContaining({
      nom_unique_projet: 'Projet Neuf',
      first_building: expect.objectContaining({ sector_id: 1, adresse: '5 rue Neuve' }),
    }));
    expect(await screen.findByTestId('location')).toHaveTextContent('/portfolio/secteurs/1/projets/77');
    expect(screen.queryByTestId('project-dialog')).toBeNull();
  });

  it('has view and edit icons on cards and unit rows', async () => {
    vi.mocked(updateUnit).mockReset().mockResolvedValue(undefined);
    const user = userEvent.setup();
    wrap('/portfolio/secteurs/1');
    const cards = await screen.findAllByTestId('project-card');
    expect(within(cards[0]).getByRole('link', { name: 'Voir Projet Cartier' }))
      .toHaveAttribute('href', '/portfolio/secteurs/1/projets/10');
    await user.click(within(cards[0]).getByTestId('project-card-edit'));
    expect(within(screen.getByTestId('project-dialog')).getByLabelText('Nom du projet *')).toHaveValue('Projet Cartier');
    // Editing doesn't navigate away.
    expect(screen.getByTestId('location')).toHaveTextContent('/portfolio/secteurs/1');
  });

  it('edits a unit from its row without opening it', async () => {
    vi.mocked(updateUnit).mockReset().mockResolvedValue(undefined);
    const user = userEvent.setup();
    wrap('/portfolio/batiments/100');
    const rows = await screen.findAllByTestId('unit-row');
    await user.click(within(rows[0]).getByTestId('unit-row-edit'));
    expect(screen.getByTestId('location')).toHaveTextContent('/portfolio/batiments/100');
    const dialog = screen.getByTestId('unit-dialog');
    const size = within(dialog).getByLabelText(/^Grandeur/);
    await user.clear(size);
    await user.type(size, '5 1/2');
    await user.click(within(dialog).getByTestId('form-submit'));
    expect(updateUnit).toHaveBeenCalledWith(1000, { changes: { grandeur: '5 1/2' }, current: { grandeur: '4 1/2' } });
  });

  it('adds a unit to a building', async () => {
    vi.mocked(createUnit).mockReset().mockResolvedValue({
      unit_id: 1500, building_id: 100, project_id: null, sector_id: null, paint_spec_id: null, document_id: null,
    });
    const user = userEvent.setup();
    wrap('/portfolio/batiments/100');
    await user.click(await screen.findByTestId('add-unit'));
    const dialog = screen.getByTestId('unit-dialog');
    expect(within(dialog).getByLabelText('Adresse du logement')).toHaveValue('10, rue Cartier');
    await user.type(within(dialog).getByLabelText('No de logement *'), '103');
    await user.click(within(dialog).getByTestId('form-submit'));
    expect(createUnit).toHaveBeenCalledWith(expect.objectContaining({ building_id: 100, numero_appartement: '103' }));
    expect(await screen.findByTestId('location')).toHaveTextContent('/portfolio/unites/1500');
  });

  it("shows the building's paint on the unit page", async () => {
    wrap('/portfolio/unites/1000');
    const paint = await screen.findByTestId('unit-paint');
    expect(within(paint).getByText('SW 7005')).toBeTruthy();
    expect(within(paint).getByRole('link')).toHaveAttribute('href', '/portfolio/batiments/100#fiche-technique');
  });
});
