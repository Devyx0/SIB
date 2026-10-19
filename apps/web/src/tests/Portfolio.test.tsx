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
  PortfolioSectorSummary,
  PortfolioUnitDetail,
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
}));

import {
  fetchPortfolioBuilding,
  fetchPortfolioProject,
  fetchPortfolioSector,
  fetchPortfolioSectors,
  fetchPortfolioUnit,
  fetchTenantTurnover,
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
    { unit_id: 1000, numero_appartement: '101', rue: '10, rue Cartier', grandeur: '4 1/2',
      tenant_name: 'Ada Lovelace', occupant_count: 2, lease_statut: 'Régulier' },
    { unit_id: 1001, numero_appartement: '102', rue: '10, rue Cartier', grandeur: '3 1/2',
      tenant_name: null, occupant_count: 0, lease_statut: null },
  ],
};

const unit: PortfolioUnitDetail = {
  unit_id: 1000, building_id: 100, project_id: 10, sector_id: 1,
  numero_appartement: '101', rue: '10, rue Cartier', grandeur: '4 1/2',
  building_adresse: '10 rue Cartier', web_building_name: 'Le Cartier',
  nom_unique_projet: 'Projet Cartier', territoire: 'Haute-Ville',
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

    await user.click(await screen.findByTestId('building-card'));
    expect(screen.getByTestId('location')).toHaveTextContent('/portfolio/batiments/100');

    const rows = await screen.findAllByTestId('unit-row');
    expect(rows).toHaveLength(2);
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
        tenant_name: i === 3 ? 'Émile Nelligan' : `Locataire ${i}`,
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
});
