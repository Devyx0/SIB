import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import { useState } from 'react';
import StepsList from '../components/StepsList';

function Harness({ initial = '', onChange = vi.fn(), disabled = false }: { initial?: string; onChange?: (v: string) => void; disabled?: boolean }) {
  const [v, setV] = useState(initial);
  return (
    <StepsList
      lang="fr"
      label="Prochaines étapes"
      value={v}
      onChange={(next) => { setV(next); onChange(next); }}
      disabled={disabled}
      inputTestId="add"
    />
  );
}

const items = () => screen.queryAllByTestId('step-item').map((li) => (li.querySelector('textarea') as HTMLTextAreaElement).value);

describe('StepsList', () => {
  it('Enter adds a step and clears the field; the value is one step per line', async () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    await userEvent.type(screen.getByTestId('add'), 'Commander la pièce{Enter}');
    await userEvent.type(screen.getByTestId('add'), 'Rappeler le locataire{Enter}');
    expect(items()).toEqual(['Commander la pièce', 'Rappeler le locataire']);
    expect((screen.getByTestId('add') as HTMLInputElement).value).toBe('');
    expect(onChange).toHaveBeenLastCalledWith('Commander la pièce\nRappeler le locataire');
  });

  it('ignores empty entries', async () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    await userEvent.type(screen.getByTestId('add'), '   {Enter}');
    expect(onChange).not.toHaveBeenCalled();
  });

  it('pasting several lines adds several steps', () => {
    render(<Harness />);
    fireEvent.paste(screen.getByTestId('add'), { clipboardData: { getData: () => 'Un\nDeux\n\nTrois' } });
    expect(items()).toEqual(['Un', 'Deux', 'Trois']);
  });

  it('existing multi-line notes show as separate steps', () => {
    render(<Harness initial={'Vérifier le siphon\nCommander la pièce'} />);
    expect(items()).toEqual(['Vérifier le siphon', 'Commander la pièce']);
  });

  it('↑ / ↓ buttons reorder, and ✕ removes', async () => {
    render(<Harness initial={'A\nB\nC'} />);
    await userEvent.click(screen.getByRole('button', { name: 'Descendre l’étape 1' }));
    expect(items()).toEqual(['B', 'A', 'C']);
    await userEvent.click(screen.getByRole('button', { name: 'Monter l’étape 3' }));
    expect(items()).toEqual(['B', 'C', 'A']);
    await userEvent.click(screen.getByRole('button', { name: 'Retirer l’étape 2' }));
    expect(items()).toEqual(['B', 'A']);
  });

  it('Alt+↑ / Alt+↓ move a step from the keyboard', () => {
    render(<Harness initial={'A\nB\nC'} />);
    fireEvent.keyDown(screen.getByRole('textbox', { name: 'Étape 3' }), { key: 'ArrowUp', altKey: true });
    expect(items()).toEqual(['A', 'C', 'B']);
  });

  it('drag and drop moves a step', () => {
    render(<Harness initial={'A\nB\nC'} />);
    const rows = screen.getAllByTestId('step-item');
    const dataTransfer = { setData: vi.fn(), effectAllowed: '' };
    fireEvent.dragStart(rows[2], { dataTransfer });
    fireEvent.dragOver(rows[0], { dataTransfer });
    fireEvent.drop(rows[0], { dataTransfer });
    expect(items()).toEqual(['C', 'A', 'B']);
  });

  it('editing a step in place updates it; clearing it removes it', () => {
    render(<Harness initial={'A\nB'} />);
    const first = screen.getByRole('textbox', { name: 'Étape 1' });
    fireEvent.change(first, { target: { value: 'A modifiée' } });
    fireEvent.blur(first);
    expect(items()).toEqual(['A modifiée', 'B']);
    const second = screen.getByRole('textbox', { name: 'Étape 2' });
    fireEvent.change(second, { target: { value: '' } });
    fireEvent.blur(second);
    expect(items()).toEqual(['A modifiée']);
  });

  it('read-only: no add field, no move or remove buttons', () => {
    render(<Harness initial={'A\nB'} disabled />);
    expect(screen.queryByTestId('add')).toBeNull();
    expect(screen.queryByRole('button')).toBeNull();
    expect(items()).toEqual(['A', 'B']);
  });
});
