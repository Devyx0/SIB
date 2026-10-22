import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import AppShell from '../components/AppShell';
import type { MeResponse } from '../api/schema.d.ts';

vi.mock('../api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/client')>();
  return {
    ...actual,
    fetchAlerts: vi.fn().mockResolvedValue({ items: [], unread_count: 0 }),
  };
});

function me(role: string): MeResponse {
  return { employee_id: 1, nom_employe: 'Test User', roles: [role] };
}

// The nav uses NavLink, so AppShell needs a Router in tests.
function wrap(ui: React.ReactElement, initial = '/board') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[initial]}>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

const CASES: [string, string][] = [
  ['coordinator',  'Coordonnateur'],
  ['director',     'Directeur'],
  ['technician',   'Technicien'],
  ['contractor',   'Sous-traitant'],
  ['receptionist', 'Réceptionniste'],
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
    expect(screen.getByTestId('nav-triage')).toHaveTextContent('Triage');
    expect(screen.getByTestId('nav-tasks')).toHaveTextContent('Tâches');
    expect(screen.getByTestId('nav-nouvelle-tache')).toHaveTextContent('Nouvelle tâche');
    expect(screen.getByText("Vue d'ensemble")).toBeTruthy();
    expect(screen.getByTestId('nav-tableau-bord')).toHaveTextContent('Tableau de bord');
    expect(screen.getByTestId('nav-utilisation')).toHaveTextContent('Utilisation');
  });

  it('has no Après les heures item (not built yet)', () => {
    wrap(<AppShell lang="fr" onToggleLang={vi.fn()} me={coord} onSignOut={vi.fn()}>x</AppShell>);
    expect(screen.queryByTestId('nav-apres-heures')).toBeNull();
    expect(screen.queryByText('Après les heures')).toBeNull();
  });

  it('overview items are in-app nav links', () => {
    wrap(<AppShell lang="fr" onToggleLang={vi.fn()} me={coord} onSignOut={vi.fn()}>x</AppShell>);
    expect((screen.getByTestId('nav-tableau-bord') as HTMLAnchorElement).getAttribute('href'))
      .toBe('/tableau-de-bord');
    expect((screen.getByTestId('nav-utilisation') as HTMLAnchorElement).getAttribute('href'))
      .toBe('/utilisation');
  });

  it('routes: Triage → /triage, Tasks → /tasks, Nouvelle tâche → /tasks?nouvelle-tache=1', () => {
    wrap(<AppShell lang="fr" onToggleLang={vi.fn()} me={coord} onSignOut={vi.fn()}>x</AppShell>);
    expect((screen.getByTestId('nav-triage') as HTMLAnchorElement).getAttribute('href')).toBe('/triage');
    expect((screen.getByTestId('nav-tasks') as HTMLAnchorElement).getAttribute('href')).toBe('/tasks');
    expect((screen.getByTestId('nav-nouvelle-tache') as HTMLAnchorElement).getAttribute('href'))
      .toBe('/tasks?nouvelle-tache=1');
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

  it('the open drawer has its own close button that hands focus back to the menu button', async () => {
    const { default: userEvent } = await import('@testing-library/user-event');
    wrap(<AppShell lang="fr" onToggleLang={vi.fn()} me={coord} onSignOut={vi.fn()}>x</AppShell>);
    const burger = screen.getByTestId('burger');
    await userEvent.click(burger);
    const close = screen.getByTestId('drawer-close');
    expect(document.activeElement).toBe(close);
    await userEvent.click(close);
    expect(burger.getAttribute('aria-expanded')).toBe('false');
    expect(document.activeElement).toBe(burger);
  });

  it('opening another page starts it at the top', async () => {
    const { default: userEvent } = await import('@testing-library/user-event');
    const scrollTo = vi.spyOn(window, 'scrollTo').mockImplementation(() => {});
    wrap(<AppShell lang="fr" onToggleLang={vi.fn()} me={coord} onSignOut={vi.fn()}>x</AppShell>);
    const main = document.querySelector('main')!;
    main.scrollTop = 500;
    scrollTo.mockClear();
    await userEvent.click(screen.getByTestId('nav-portfolio'));
    expect(scrollTo).toHaveBeenCalledWith(expect.objectContaining({ top: 0, behavior: 'instant' }));
    expect(main.scrollTop).toBe(0);
    scrollTo.mockRestore();
  });

  it('never shows a Milestone label', () => {
    wrap(<AppShell lang="fr" onToggleLang={vi.fn()} me={coord} onSignOut={vi.fn()}>x</AppShell>);
    expect(screen.queryByText(/milestone|jalon/i)).toBeNull();
  });

  it('receptionist only sees Nouvel appel → /intake', () => {
    wrap(
      <AppShell lang="fr" onToggleLang={vi.fn()} me={me('receptionist')} onSignOut={vi.fn()}>
        x
      </AppShell>,
      '/intake',
    );
    expect(screen.getByTestId('nav-nouvel-appel')).toHaveTextContent('Nouvel appel');
    expect((screen.getByTestId('nav-nouvel-appel') as HTMLAnchorElement).getAttribute('href'))
      .toBe('/intake');
    expect(screen.queryByTestId('nav-triage')).toBeNull();
    expect(screen.queryByTestId('nav-tasks')).toBeNull();
    expect(screen.queryByTestId('nav-tableau-bord')).toBeNull();
  });
});
