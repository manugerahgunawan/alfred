import {render, screen} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import App from './App';

describe('App UI', () => {
  it('renders the home briefing by default', () => {
    render(<App />);

    expect(screen.getByText(/Good morning\./i)).toBeInTheDocument();
    expect(screen.getByText(/Here's what needs your attention\./i)).toBeInTheDocument();
  });

  it('navigates between primary tabs', async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole('button', {name: /Family/i}));
    expect(screen.getByText(/Household/i)).toBeInTheDocument();

    await user.click(screen.getByRole('button', {name: /Alerts/i}));
    expect(screen.getByText(/Alfred's proactive updates/i)).toBeInTheDocument();

    await user.click(screen.getByRole('button', {name: /Alfred/i}));
    expect(screen.getByText(/Always at your service/i)).toBeInTheDocument();
  });

  it('provides chat controls that users can interact with', async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole('button', {name: /Alfred/i}));

    const messageInput = screen.getByPlaceholderText(/Type a message/i);
    await user.type(messageInput, 'Test message');

    expect(messageInput).toHaveValue('Test message');
    expect(screen.getAllByRole('button')).not.toHaveLength(0);
  });
});
