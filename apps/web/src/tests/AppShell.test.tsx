import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import AppShell from '../components/AppShell';
import type { MeResponse } from '../api/schema.d.ts';

function me(role: string): MeResponse {
  return { employee_id: 1, nom_employe: 'Test User', roles: [role] };
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
      render(
        <AppShell lang="fr" onToggleLang={vi.fn()} me={me(role)} onSignOut={vi.fn()}>
          <div />
        </AppShell>
      );
      expect(screen.getByText(label)).toBeTruthy();
    });
  }
});
