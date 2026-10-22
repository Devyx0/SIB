import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import { useState } from 'react';
import Select from '../components/Select';
import RangeCalendar from '../components/RangeCalendar';

function Harness({ onChange }: { onChange: (v: string) => void }) {
  const [v, setV] = useState('');
  return (
    <>
      <label htmlFor="fruit">Fruit</label>
      <Select id="fruit" value={v} data-testid="fruit" onChange={(e) => { setV(e.target.value); onChange(e.target.value); }}>
        <option value="">Tous</option>
        <option value="a">Abricot</option>
        <option value="b" disabled>Banane (épuisée)</option>
        <option value="c">Cerise</option>
      </Select>
    </>
  );
}

describe('Select search and initials', () => {
  function People({ onChange }: { onChange: (v: string) => void }) {
    const [v, setV] = useState('');
    return (
      <Select aria-label="Employé" value={v} searchable avatars searchPlaceholder="Rechercher un employé…"
              noResultsText="Aucun employé trouvé"
              onChange={(e) => { setV(e.target.value); onChange(e.target.value); }}>
        <option value="">— Non assigné —</option>
        <option value="1">Alain Lepire (Technicien)</option>
        <option value="2">André Côté (Technicien)</option>
        <option value="3">Zach Rousseau (Technicien)</option>
      </Select>
    );
  }

  it('filters the list as you type (accents ignored) and picks with Enter', async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<People onChange={onChange} />);
    await user.click(screen.getByRole('combobox', { name: 'Employé' }));
    const search = screen.getByTestId('select-search');
    expect(document.activeElement).toBe(search);
    await user.type(search, 'andre');
    expect(screen.getAllByRole('option').map((o) => o.textContent)).toEqual(['ACAndré Côté (Technicien)']);
    await user.keyboard('{Enter}');
    expect(onChange).toHaveBeenCalledWith('2');
  });

  it('says so when nothing matches, and shows initials beside people', async () => {
    const user = userEvent.setup();
    render(<People onChange={vi.fn()} />);
    await user.click(screen.getByRole('combobox', { name: 'Employé' }));
    expect(screen.getByRole('option', { name: /Zach Rousseau/ }).querySelector('[data-testid="avatar"]')?.textContent).toBe('ZR');
    await user.type(screen.getByTestId('select-search'), 'xyz');
    expect(screen.getByText('Aucun employé trouvé')).toBeTruthy();
  });
});

describe('Select (themed dropdown)', () => {
  it('is a labelled combobox showing the current option', () => {
    render(<Harness onChange={vi.fn()} />);
    const box = screen.getByRole('combobox', { name: 'Fruit' });
    expect(box.getAttribute('aria-expanded')).toBe('false');
    expect(box.textContent).toContain('Tous');
  });

  it('opens a listbox and picking an option fires a normal change event', async () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    await userEvent.click(screen.getByRole('combobox', { name: 'Fruit' }));
    expect(screen.getByRole('listbox')).toBeTruthy();
    await userEvent.click(screen.getByRole('option', { name: 'Cerise' }));
    expect(onChange).toHaveBeenCalledWith('c');
    expect(screen.queryByRole('listbox')).toBeNull();
    expect((screen.getByTestId('fruit') as HTMLSelectElement).value).toBe('c');
  });

  it('ignores disabled options', async () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    await userEvent.click(screen.getByRole('combobox', { name: 'Fruit' }));
    await userEvent.click(screen.getByRole('option', { name: 'Banane (épuisée)' }));
    expect(onChange).not.toHaveBeenCalled();
  });

  it('works from the keyboard and skips disabled options', async () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    const box = screen.getByRole('combobox', { name: 'Fruit' });
    box.focus();
    await userEvent.keyboard('{ArrowDown}'); // open on « Tous »
    await userEvent.keyboard('{ArrowDown}{ArrowDown}'); // Abricot → (skip Banane) → Cerise
    await userEvent.keyboard('{Enter}');
    expect(onChange).toHaveBeenCalledWith('c');
  });

  it('Escape closes the list without reaching outer handlers', async () => {
    const outer = vi.fn();
    render(<div onKeyDown={outer}><Harness onChange={vi.fn()} /></div>);
    const box = screen.getByRole('combobox', { name: 'Fruit' });
    await userEvent.click(box);
    fireEvent.keyDown(box, { key: 'Escape' });
    expect(screen.queryByRole('listbox')).toBeNull();
    expect(outer).not.toHaveBeenCalled();
  });

  it('existing tests can still drive the hidden native select', async () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    await userEvent.selectOptions(screen.getByTestId('fruit'), 'a');
    expect(onChange).toHaveBeenCalledWith('a');
    expect(screen.getByRole('combobox', { name: 'Fruit' }).textContent).toContain('Abricot');
  });
});

describe('RangeCalendar', () => {
  it('two clicks pick a range, in either order', async () => {
    const onChange = vi.fn();
    const { container } = render(<RangeCalendar lang="fr" start="2026-10-01" end="2026-10-20" onChange={onChange} />);
    await userEvent.click(container.querySelector('[data-day="2026-10-15"]')!);
    expect(onChange).not.toHaveBeenCalled();
    await userEvent.click(container.querySelector('[data-day="2026-10-05"]')!);
    expect(onChange).toHaveBeenCalledWith('2026-10-05', '2026-10-15');
  });

  it('disables days beyond the 31-day limit while picking the end', async () => {
    const { container } = render(<RangeCalendar lang="fr" start="2026-10-01" end="2026-10-20" maxDays={7} onChange={vi.fn()} />);
    await userEvent.click(container.querySelector('[data-day="2026-10-10"]')!);
    expect((container.querySelector('[data-day="2026-10-16"]') as HTMLButtonElement).disabled).toBe(false);
    expect((container.querySelector('[data-day="2026-10-17"]') as HTMLButtonElement).disabled).toBe(true);
  });

  it('moves between months', async () => {
    render(<RangeCalendar lang="fr" start="2026-10-01" end="2026-10-20" onChange={vi.fn()} />);
    expect(screen.getByText(/octobre 2026/i)).toBeTruthy();
    await userEvent.click(screen.getByRole('button', { name: 'Mois précédent' }));
    expect(screen.getByText(/septembre 2026/i)).toBeTruthy();
  });
});
