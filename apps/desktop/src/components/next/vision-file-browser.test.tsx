import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';

import { VisionFileBrowser } from '@/components/next/vision-file-browser';
import { getBridgeClient, resetBridgeClient } from '@/lib/bridge/client';
import { resetEchoWorkspace } from '@/lib/bridge/echo-workspace';
import { joinWorkspacePath } from '@/lib/workspace/join-path';

describe('joinWorkspacePath', () => {
  it('joins unix roots with forward slashes', () => {
    expect(joinWorkspacePath('/workspace/demo', 'scan-report.png')).toBe(
      '/workspace/demo/scan-report.png',
    );
    expect(joinWorkspacePath('/workspace/demo/', 'notes/todo.md')).toBe(
      '/workspace/demo/notes/todo.md',
    );
  });

  it('joins windows roots with backslashes and normalizes separators', () => {
    expect(joinWorkspacePath('C:\\Users\\alina\\Documents', 'scans/report.png')).toBe(
      'C:\\Users\\alina\\Documents\\scans\\report.png',
    );
    expect(joinWorkspacePath('C:\\Users\\alina\\Documents\\', 'report.png')).toBe(
      'C:\\Users\\alina\\Documents\\report.png',
    );
  });

  it('returns the root itself for an empty relative path', () => {
    expect(joinWorkspacePath('/workspace/demo', '')).toBe('/workspace/demo');
    expect(joinWorkspacePath('C:\\Docs', '  ')).toBe('C:\\Docs');
  });

  it('never produces a double separator', () => {
    expect(joinWorkspacePath('/workspace/demo/', '/a.png')).toBe('/workspace/demo/a.png');
    expect(joinWorkspacePath('C:\\Docs\\', '\\a.png')).toBe('C:\\Docs\\a.png');
  });
});

describe('VisionFileBrowser (echo transport)', () => {
  beforeEach(() => {
    resetBridgeClient();
    resetEchoWorkspace();
  });

  it('lists seeded workspace files and selects an OCR-ready image with its absolute path', async () => {
    const client = getBridgeClient();
    expect(client.transportKind).toBe('echo');
    const selected: string[] = [];
    render(
      <VisionFileBrowser
        client={client}
        selectedPath=""
        onSelect={(path) => selected.push(path)}
      />,
    );

    // The seeded demo root appears as a chip and its files are listed.
    expect(await screen.findByTitle('/workspace/demo')).toBeTruthy();
    expect(await screen.findByText('scan-report.png')).toBeTruthy();
    expect(screen.getByText('invoice-1405.png')).toBeTruthy();
    expect(screen.getByText('sales.csv')).toBeTruthy();
    // Honest transport badge for the browser preview.
    expect(screen.getByText(/BROWSER PREVIEW/)).toBeTruthy();

    await userEvent.click(screen.getByText('scan-report.png'));
    expect(selected[selected.length - 1]).toBe('/workspace/demo/scan-report.png');
  });

  it('navigates into a directory and back to the root via the root chip', async () => {
    const client = getBridgeClient();
    render(<VisionFileBrowser client={client} selectedPath="" onSelect={() => {}} />);

    await screen.findByText('scan-report.png');
    await userEvent.click(screen.getByText('notes'));
    expect(await screen.findByText('todo.md')).toBeTruthy();
    expect(screen.queryByText('scan-report.png')).toBeNull();

    // The root chip resets the listing to the root directory.
    await userEvent.click(screen.getByTitle('/workspace/demo'));
    expect(await screen.findByText('scan-report.png')).toBeTruthy();
  });

  it('registers a folder inline and switches the listing to it', async () => {
    const client = getBridgeClient();
    const user = userEvent.setup();
    render(<VisionFileBrowser client={client} selectedPath="" onSelect={() => {}} />);

    await screen.findByText('scan-report.png');
    await user.type(screen.getByPlaceholderText(/مسیر پوشه/), 'C:\\Users\\alina\\Documents');
    await user.click(screen.getByText('ثبت پوشه (import_folder)'));

    // The new root chip appears, active, and its listing is served.
    const chip = await screen.findByTitle('C:\\Users\\alina\\Documents');
    expect(chip.className).toContain('fuchsia');
    expect(chip.textContent).toContain('Imported folder');
    expect(await screen.findByText('scan-report.png')).toBeTruthy();
  });
});
