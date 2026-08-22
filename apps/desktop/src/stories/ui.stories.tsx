import { Bell, Inbox, Search } from 'lucide-react';
import { useState } from 'react';

import { CommandPalette } from '@/components/shared/command-palette';
import { EmptyState } from '@/components/shared/empty-state';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Input, Textarea } from '@/components/ui/input';
import { Skeleton, SkeletonCard } from '@/components/ui/skeleton';
import { Switch } from '@/components/ui/switch';
import { Tabs } from '@/components/ui/tabs';
import { ToastViewport } from '@/components/ui/toast';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { useAppStore } from '@/stores/use-app-store';
import { ThemeMatrix } from '@/stories/theme-matrix';

export const Buttons = () => (
  <ThemeMatrix>
    <div className="flex flex-wrap items-center gap-2">
      <Button variant="primary">Continue</Button>
      <Button variant="secondary">Review</Button>
      <Button variant="ghost">Later</Button>
      <Button variant="destructive">Delete</Button>
      <Button variant="danger-outline">Deny</Button>
      <Button loading>Saving safely</Button>
      <Button size="icon" aria-label="Notifications">
        <Bell />
      </Button>
    </div>
  </ThemeMatrix>
);

export const Badges = () => (
  <ThemeMatrix>
    <div className="flex flex-wrap gap-2">
      {(['neutral', 'accent', 'success', 'warning', 'danger', 'info'] as const).map((tone) => (
        <Badge key={tone} variant={tone}>
          {tone}
        </Badge>
      ))}
    </div>
  </ThemeMatrix>
);

export const Inputs = () => (
  <ThemeMatrix>
    <div className="grid gap-3">
      <Input
        label="Search"
        placeholder="Memory or session"
        leading={<Search />}
        hint="Local only"
      />
      <Input label="Provider key" value="••••••••" readOnly error="The key could not be verified" />
      <Textarea label="Prompt" defaultValue="خلاصهٔ پژوهش را آماده کن" hint="Persian and English" />
    </div>
  </ThemeMatrix>
);

export const Cards = () => (
  <ThemeMatrix>
    <Card>
      <CardHeader>
        <CardTitle>Research workspace</CardTitle>
        <CardDescription>Stored on this machine</CardDescription>
      </CardHeader>
      <CardContent>Three sources are ready for analysis.</CardContent>
      <CardFooter>
        <Button size="sm" variant="primary">
          Open
        </Button>
      </CardFooter>
    </Card>
  </ThemeMatrix>
);

export const Skeletons = () => (
  <ThemeMatrix>
    <div className="grid gap-3">
      <SkeletonCard />
      <Skeleton className="h-8 w-full" />
    </div>
  </ThemeMatrix>
);

export const Dialogs = () => (
  <ThemeMatrix>
    <Dialog>
      <DialogTrigger asChild>
        <Button>Open dialog</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Allow file write?</DialogTitle>
          <DialogDescription>
            The exact path and change remain visible before approval.
          </DialogDescription>
        </DialogHeader>
        <DialogBody>~/research/notes.md</DialogBody>
        <DialogFooter>
          <Button variant="danger-outline">Deny</Button>
          <Button variant="primary">Allow once</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </ThemeMatrix>
);

export const Dropdowns = () => (
  <ThemeMatrix>
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button>Choose model</Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent>
        <DropdownMenuLabel>Local models</DropdownMenuLabel>
        <DropdownMenuCheckboxItem checked>Echo</DropdownMenuCheckboxItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem>Configure providers</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  </ThemeMatrix>
);

export const Tooltips = () => (
  <ThemeMatrix>
    <Tooltip defaultOpen>
      <TooltipTrigger asChild>
        <Button size="icon" aria-label="Notifications">
          <Bell />
        </Button>
      </TooltipTrigger>
      <TooltipContent>Background activity</TooltipContent>
    </Tooltip>
  </ThemeMatrix>
);

export const TabSets = () => (
  <ThemeMatrix>
    <Tabs
      label="Memory views"
      items={[
        { id: 'list', label: 'List', content: 'Semantic and episodic memories' },
        { id: 'timeline', label: 'Timeline', content: 'Today · This week · Older' },
      ]}
    />
  </ThemeMatrix>
);

function SwitchFixture() {
  const [checked, setChecked] = useState(true);
  return (
    <ThemeMatrix>
      <Switch
        checked={checked}
        onCheckedChange={setChecked}
        label="Require approval"
        description="Ask before the skill writes files"
      />
    </ThemeMatrix>
  );
}
export const Switches = () => <SwitchFixture />;

export const Toasts = () => (
  <ThemeMatrix>
    <ToastViewport
      label="Notifications"
      dismissLabel="Dismiss"
      onDismiss={() => undefined}
      className="!static !w-full"
      notices={[
        {
          id: 'saved',
          title: 'Memory saved',
          description: 'Available offline',
          tone: 'success',
        },
      ]}
    />
  </ThemeMatrix>
);

export const EmptyStates = () => (
  <ThemeMatrix>
    <div className="h-56">
      <EmptyState
        icon={Inbox}
        title="Nothing here yet"
        description="Your next local session will appear here."
        action={{ label: 'Start', onClick: () => undefined }}
      />
    </div>
  </ThemeMatrix>
);

export const CommandPalettes = () => {
  const setOpen = useAppStore((state) => state.setCommandPaletteOpen);
  return (
    <ThemeMatrix>
      <Button onClick={() => setOpen(true)}>Open command palette</Button>
      <CommandPalette
        commands={[
          { keys: ['mod', '1'], description: 'Go to dashboard', run: () => undefined },
          { keys: ['mod', ','], description: 'Open settings', run: () => undefined },
        ]}
      />
    </ThemeMatrix>
  );
};
