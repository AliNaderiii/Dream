import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';
import { Tabs } from '@/components/ui/tabs';

describe('Rooya interactive primitives', () => {
  it('keeps button content in flow while loading', () => {
    render(<Button loading>Save changes</Button>);
    const button = screen.getByRole('button', { name: 'Save changes' });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute('aria-busy', 'true');
    expect(screen.getByTestId('button-spinner')).toBeInTheDocument();
    expect(screen.getByText('Save changes')).toHaveClass('invisible');
  });

  it('associates input errors without relying on border color', () => {
    render(<Input label="Name" error="Name is required" />);
    const input = screen.getByRole('textbox', { name: 'Name' });
    expect(input).toHaveAttribute('aria-invalid', 'true');
    expect(input).toHaveAccessibleDescription('Name is required');
  });

  it('operates tabs with arrows', async () => {
    const user = userEvent.setup();
    render(
      <Tabs
        label="Views"
        items={[
          { id: 'list', label: 'List', content: 'List content' },
          { id: 'timeline', label: 'Timeline', content: 'Timeline content' },
        ]}
      />,
    );
    const first = screen.getByRole('tab', { name: 'List' });
    first.focus();
    await user.keyboard('{ArrowRight}');
    expect(screen.getByRole('tab', { name: 'Timeline' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tabpanel')).toHaveTextContent('Timeline content');
  });

  it('mirrors tab arrow order in RTL', async () => {
    document.documentElement.dir = 'rtl';
    const user = userEvent.setup();
    render(
      <Tabs
        label="Views"
        defaultValue="timeline"
        items={[
          { id: 'list', label: 'List', content: 'List content' },
          { id: 'timeline', label: 'Timeline', content: 'Timeline content' },
        ]}
      />,
    );
    const timeline = screen.getByRole('tab', { name: 'Timeline' });
    timeline.focus();
    await user.keyboard('{ArrowRight}');
    expect(screen.getByRole('tab', { name: 'List' })).toHaveAttribute('aria-selected', 'true');
    document.documentElement.dir = 'ltr';
  });

  it('announces and changes switch state', async () => {
    const user = userEvent.setup();
    const change = vi.fn();
    render(<Switch checked={false} onCheckedChange={change} label="Require approval" />);
    await user.click(screen.getByRole('switch', { name: 'Require approval' }));
    expect(change).toHaveBeenCalledWith(true);
  });
});
