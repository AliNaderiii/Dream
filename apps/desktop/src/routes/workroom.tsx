import { useEffect, useState } from 'react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader } from '@/components/ui/card';
import { Input, Textarea } from '@/components/ui/input';
import { useBridge } from '@/lib/bridge/hooks';
import {
  workroomAddSeat,
  workroomApprove,
  workroomCreate,
  workroomDeny,
  workroomDraft,
  workroomList,
  workroomListDrafts,
  workroomListSeats,
  type WorkroomDraft,
  type WorkroomRecord,
  type WorkroomSeat,
} from '@/lib/bridge/workroom';
import { useTranslation } from '@/lib/i18n';

const ROLES = ['manager', 'specialist', 'warehouse', 'reviewer'];

export default function WorkroomRoute() {
  const { t } = useTranslation('workroom');
  const { client } = useBridge();
  const [rooms, setRooms] = useState<WorkroomRecord[]>([]);
  const [active, setActive] = useState<WorkroomRecord | null>(null);
  const [seats, setSeats] = useState<WorkroomSeat[]>([]);
  const [drafts, setDrafts] = useState<WorkroomDraft[]>([]);
  const [name, setName] = useState('Studio Co');
  const [seatName, setSeatName] = useState('Leila');
  const [roleId, setRoleId] = useState('manager');
  const [vip, setVip] = useState(false);
  const [body, setBody] = useState('');
  const [error, setError] = useState<string | null>(null);
  const roomId = active?.room_id;

  useEffect(() => {
    let cancelled = false;
    void workroomList(client)
      .then((listed) => {
        if (cancelled) return;
        const rows = listed.rooms ?? [];
        setRooms(rows);
        setActive(rows[0] ?? null);
      })
      .catch((reason: unknown) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : String(reason));
      });
    return () => {
      cancelled = true;
    };
  }, [client]);

  useEffect(() => {
    let cancelled = false;
    if (!roomId) {
      return;
    }
    void Promise.all([workroomListSeats(client, roomId), workroomListDrafts(client, roomId)])
      .then(([seatRows, draftRows]) => {
        if (cancelled) return;
        setSeats(seatRows.seats ?? []);
        setDrafts(draftRows.drafts ?? []);
      })
      .catch((reason: unknown) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : String(reason));
      });
    return () => {
      cancelled = true;
    };
  }, [client, roomId]);

  const refreshRooms = async (room?: WorkroomRecord) => {
    const listed = await workroomList(client);
    setRooms(listed.rooms ?? []);
    if (room) setActive(room);
  };

  const onCreate = async () => {
    setError(null);
    try {
      const room = await workroomCreate(client, name);
      await refreshRooms(room);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  };

  const onAddSeat = async () => {
    if (!roomId) return;
    setError(null);
    try {
      await workroomAddSeat(client, roomId, seatName, roleId, vip);
      const listed = await workroomListSeats(client, roomId);
      setSeats(listed.seats ?? []);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  };

  const onDraft = async () => {
    if (!roomId) return;
    setError(null);
    try {
      await workroomDraft(client, roomId, body);
      const listed = await workroomListDrafts(client, roomId);
      setDrafts(listed.drafts ?? []);
      setBody('');
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  };

  const onApprove = async (draftId: string) => {
    if (!roomId) return;
    setError(null);
    try {
      await workroomApprove(client, draftId);
      const listed = await workroomListDrafts(client, roomId);
      setDrafts(listed.drafts ?? []);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  };

  const onDeny = async (draftId: string) => {
    if (!roomId) return;
    setError(null);
    try {
      await workroomDeny(client, draftId);
      const listed = await workroomListDrafts(client, roomId);
      setDrafts(listed.drafts ?? []);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  };

  return (
    <main
      className="flex h-full flex-col gap-4 overflow-y-auto p-4"
      aria-labelledby="workroom-title"
    >
      <header>
        <h1 id="workroom-title" className="text-h2 font-semibold">
          {t('title')}
        </h1>
        <p className="text-body text-fg-muted">{t('subtitle')}</p>
      </header>

      {error && (
        <p role="alert" className="rounded-lg border border-danger-fg p-3 text-body text-danger-fg">
          {error}
        </p>
      )}

      <div className="flex flex-wrap gap-2">
        <Badge variant="success">{t('yolo')}</Badge>
        <Badge variant="neutral">{t('chrome')}</Badge>
        <Badge variant="warning">{t('nosend')}</Badge>
      </div>

      <Card>
        <CardHeader>
          <h2 className="text-h3 font-semibold">{t('createTitle')}</h2>
          <CardDescription>{t('createHelp')}</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <Input label={t('name')} value={name} onChange={(event) => setName(event.target.value)} />
          <Button onClick={() => void onCreate()} disabled={!name.trim()}>
            {t('create')}
          </Button>
          <ul className="flex flex-wrap gap-2">
            {rooms.map((room) => (
              <li key={room.room_id}>
                <Button
                  variant={room.room_id === roomId ? 'primary' : 'secondary'}
                  onClick={() => setActive(room)}
                >
                  {room.name}
                </Button>
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>

      {roomId && (
        <>
          <Card>
            <CardHeader>
              <h2 className="text-h3 font-semibold">{t('seats')}</h2>
              <CardDescription>{t('seatsHelp')}</CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-3">
              <Input
                label={t('seatName')}
                value={seatName}
                onChange={(event) => setSeatName(event.target.value)}
              />
              <label className="flex flex-col gap-1 text-caption font-medium">
                {t('role')}
                <select
                  className="rounded-md border border-border-default bg-surface px-3 py-2 text-body"
                  value={roleId}
                  onChange={(event) => setRoleId(event.target.value)}
                >
                  {ROLES.map((role) => (
                    <option key={role} value={role}>
                      {role}
                    </option>
                  ))}
                </select>
              </label>
              <label className="flex items-center gap-2 text-caption">
                <input type="checkbox" checked={vip} onChange={() => setVip((value) => !value)} />
                {t('vip')}
              </label>
              <Button onClick={() => void onAddSeat()} disabled={!seatName.trim()}>
                {t('addSeat')}
              </Button>
              <ul className="flex flex-col gap-2">
                {seats.map((seat) => (
                  <li key={seat.seat_id} className="text-caption">
                    {seat.name} · {seat.role_id}
                    {seat.vip ? ` · ${t('vip')}` : ''}
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <h2 className="text-h3 font-semibold">{t('drafts')}</h2>
              <CardDescription>{t('draftsHelp')}</CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-3">
              <Textarea
                label={t('body')}
                value={body}
                onChange={(event) => setBody(event.target.value)}
              />
              <Button onClick={() => void onDraft()} disabled={!body.trim()}>
                {t('queue')}
              </Button>
              <ul className="flex flex-col gap-2">
                {drafts.map((draft) => (
                  <li
                    key={draft.draft_id}
                    className="flex flex-col gap-2 rounded-lg border border-border-default p-3"
                    dir="auto"
                  >
                    <p className="text-caption">{draft.body}</p>
                    <p className="text-caption text-fg-muted">
                      {draft.status} · {t('unsent')}
                    </p>
                    {draft.status === 'APPROVAL_PENDING' && (
                      <div className="flex gap-2">
                        <Button onClick={() => void onApprove(draft.draft_id)}>
                          {t('approve')}
                        </Button>
                        <Button variant="secondary" onClick={() => void onDeny(draft.draft_id)}>
                          {t('deny')}
                        </Button>
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
        </>
      )}
    </main>
  );
}
