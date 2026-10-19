import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import AppShell from '../components/AppShell';
import type { MeResponse } from '../api/schema.d.ts';

function me(role: string): MeResponse {
  return { employee_id: 1, nom_employe: 'Test User', roles: [role] };
}

// The nav uses NavLink, so AppShell needs a Router in tests.
function wrap(ui: React.ReactElement, initial = '/board') {
  return render(<MemoryRouter initialEntries={[initial]}>{ui}</MemoryRouter>);
}

const CASES: [string, string][] = [
  ['coordinator', 'Coordonnateur'],
  ['director',    'Directeur'],
  ['technician',  'Technicien'],
  ['contractor',  'Sous-traitant'],
];

describe('AppShell sidebar role labels (lang=fr)', () => {
  for (const [role, label] of CASES) {
    it(`renders "${label}" for role "${role}"`, () => {
      wrap(
        <AppShell lang="fr" onToggleLang={vi.fn()} me={me(role)} onSignOut={vi.fn()}>
          <div />
        </AppShell>
      );
      expect(screen.getByText(label)).toBeTruthy();
    });
  }
});

describe('AppShell side menu', () => {
  const coord = me('coordinator');

  it('renders the menu items with French labels', () => {
    wrap(<AppShell lang="fr" onToggleLang={vi.fn()} me={coord} onSignOut={vi.fn()}>x</AppShell>);
    expect(screen.getByTestId('nav-board')).toHaveTextContent('Répartition');
    expect(screen.getByTestId('nav-nouvel-appel')).toHaveTextContent('Nouvel appel');
    expect(screen.getByTestId('nav-dossiers')).toHaveTextContent('Dossiers');
    expect(screen.getByTestId('nav-apres-heures')).toHaveTextContent('Après les heures');
    expect(screen.getByText("Vue d'ensemble")).toBeTruthy();
    expect(screen.getByTestId('nav-tableau-bord')).toHaveTextContent('Tableau de bord');
    expect(screen.getByTestId('nav-utilisation')).toHaveTextContent('Utilisation');
  });

  it('greys the coming-soon items with a Bientôt chip', () => {
    wrap(<AppShell lang="fr" onToggleLang={vi.fn()} me={coord} onSignOut={vi.fn()}>x</AppShell>);
    expect(screen.getAllByText('Bientôt')).toHaveLength(3); // Après les heures, Tableau de bord, Utilisation
    expect(screen.getByTestId('nav-apres-heures').closest('a')).toBeNull(); // not a link
  });

  it('overview items open the mockup in a new tab with the preview tooltip', () => {
    wrap(<AppShell lang="fr" onToggleLang={vi.fn()} me={coord} onSignOut={vi.fn()}>x</AppShell>);
    for (const id of ['nav-tableau-bord', 'nav-utilisation']) {
      const a = screen.getByTestId(id) as HTMLAnchorElement;
      expect(a.href).toContain('sib-maintenance-mockups.vercel.app');
      expect(a.target).toBe('_blank');
      expect(a.rel).toContain('noreferrer');
      expect(a.title).toBe('Aperçu — maquette, données fictives');
    }
  });

  it('routes: Répartition → /board, Dossiers → /dossiers, Nouvel appel → /board?nouvel-appel=1', () => {
    wrap(<AppShell lang="fr" onToggleLang={vi.fn()} me={coord} onSignOut={vi.fn()}>x</AppShell>);
    expect((screen.getByTestId('nav-board') as HTMLAnchorElement).getAttribute('href')).toBe('/board');
    expect((screen.getByTestId('nav-dossiers') as HTMLAnchorElement).getAttribute('href')).toBe('/dossiers');
    expect((screen.getByTestId('nav-nouvel-appel') as HTMLAnchorElement).getAttribute('href'))
      .toBe('/board?nouvel-appel=1');
  });

  it('Escape closes the mobile slide-over', async () => {
    const { default: userEvent } = await import('@testing-library/user-event');
    wrap(<AppShell lang="fr" onToggleLang={vi.fn()} me={coord} onSignOut={vi.fn()}>x</AppShell>);
    const burger = screen.getByTestId('burger');
    await userEvent.click(burger);
    expect(burger.getAttribute('aria-expanded')).toBe('true');
    await userEvent.keyboard('{Escape}');
    expect(burger.getAttribute('aria-expanded')).toBe('false');
  });

  it('never shows a Milestone label', () => {
    wrap(<AppShell lang="fr" onToggleLang={vi.fn()} me={coord} onSignOut={vi.fn()}>x</AppShell>);
    expect(screen.queryByText(/milestone|jalon/i)).toBeNull();
  });
});
