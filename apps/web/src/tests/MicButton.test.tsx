import { render } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import MicButton from '../components/MicButton';

describe('MicButton', () => {
  it('renders nothing when SpeechRecognition is unavailable', () => {
    // jsdom does not expose window.SpeechRecognition — MicButton must return null.
    const { container } = render(<MicButton onTranscript={vi.fn()} />);
    expect(container.firstChild).toBeNull();
  });
});
