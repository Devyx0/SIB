import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import JustificationModal from '../components/JustificationModal';

function wrap(props: Partial<Parameters<typeof JustificationModal>[0]> = {}) {
  return render(
    <JustificationModal
      open={true}
      onSave={props.onSave ?? vi.fn()}
      onCancel={props.onCancel ?? vi.fn()}
      lang="fr"
      {...props}
    />
  );
}

describe('JustificationModal', () => {
  it('renders when open=true', () => {
    wrap();
    expect(screen.getByTestId('justification-text')).toBeTruthy();
  });

  it('renders nothing when open=false', () => {
    render(<JustificationModal open={false} onSave={vi.fn()} onCancel={vi.fn()} />);
    expect(screen.queryByTestId('justification-text')).toBeNull();
  });

  it('save button disabled when text is empty', () => {
    wrap();
    const btn = screen.getByTestId('justification-save') as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
  });

  it('save button disabled when text is under 10 chars', async () => {
    wrap();
    await userEvent.type(screen.getByTestId('justification-text'), 'Too short');
    const btn = screen.getByTestId('justification-save') as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
  });

  it('save button enabled at exactly 10 chars', async () => {
    wrap();
    await userEvent.type(screen.getByTestId('justification-text'), '1234567890');
    const btn = screen.getByTestId('justification-save') as HTMLButtonElement;
    expect(btn.disabled).toBe(false);
  });

  it('calls onSave with text and typed input_method', async () => {
    const onSave = vi.fn();
    wrap({ onSave });
    await userEvent.type(screen.getByTestId('justification-text'), 'Valid justification text');
    await userEvent.click(screen.getByTestId('justification-save'));
    expect(onSave).toHaveBeenCalledWith('Valid justification text', 'typed');
  });

  it('calls onCancel when Annuler clicked', async () => {
    const onCancel = vi.fn();
    wrap({ onCancel });
    await userEvent.click(screen.getByText('Annuler'));
    expect(onCancel).toHaveBeenCalled();
  });

  it('hides mic button when SpeechRecognition is unavailable', () => {
    // jsdom does not expose window.SpeechRecognition, so the button must not render
    wrap();
    expect(screen.queryByTestId('mic-btn')).toBeNull();
  });
});
