/** Deterministic echo runtime for workroom.* */

export interface WorkroomSeat {
  seat_id: string;
  room_id: string;
  name: string;
  role_id: string;
  vip: boolean;
  memory_user: string;
  yolo: false;
  chrome_profile: false;
  computer_use: false;
  can_send: false;
}

export interface WorkroomDraft {
  draft_id: string;
  room_id: string;
  body: string;
  status: 'APPROVAL_PENDING' | 'ready' | 'denied';
  sent: false;
  yolo: false;
}

export interface WorkroomRecord {
  room_id: string;
  name: string;
  space_id: string;
  mode: 'company';
  memory_user: string;
  yolo: false;
  chrome_profile: false;
  computer_use: false;
  sends: false;
}

const rooms: WorkroomRecord[] = [];
const seats: WorkroomSeat[] = [];
const drafts: WorkroomDraft[] = [];

export function echoWorkroomCreate(name: string, yolo = false) {
  if (yolo) throw new Error('YOLO cannot open a company workroom');
  const title = name.trim();
  if (!title) throw new Error('name must be a non-empty string of at most 80 characters');
  const room_id = `wrm_echo_${rooms.length + 1}`;
  const room: WorkroomRecord = {
    room_id,
    name: title,
    space_id: '',
    mode: 'company',
    memory_user: `workroom:${room_id}`,
    yolo: false,
    chrome_profile: false,
    computer_use: false,
    sends: false,
  };
  rooms.push(room);
  return room;
}

export function echoWorkroomList() {
  return {
    rooms: [...rooms],
    count: rooms.length,
    roles: ['manager', 'specialist', 'warehouse', 'reviewer'],
  };
}

export function echoWorkroomGet(roomId: string) {
  const room = rooms.find((row) => row.room_id === roomId);
  if (!room) throw new Error('no workroom');
  const roomSeats = seats.filter((row) => row.room_id === roomId);
  return { ...room, seats: roomSeats, vip_seats: roomSeats.filter((row) => row.vip).length };
}

export function echoWorkroomAddSeat(
  roomId: string,
  name: string,
  roleId = 'specialist',
  vip = false,
  yolo = false,
) {
  if (yolo) throw new Error('YOLO cannot add workroom seats');
  const room = rooms.find((row) => row.room_id === roomId);
  if (!room) throw new Error('no workroom');
  const seat_id = `seat_echo_${seats.length + 1}`;
  const seat: WorkroomSeat = {
    seat_id,
    room_id: roomId,
    name: name.trim(),
    role_id: roleId,
    vip,
    memory_user: `workroom:${roomId}:seat:${seat_id}`,
    yolo: false,
    chrome_profile: false,
    computer_use: false,
    can_send: false,
  };
  seats.push(seat);
  return seat;
}

export function echoWorkroomListSeats(roomId: string) {
  const rows = seats.filter((row) => row.room_id === roomId);
  return { seats: rows, count: rows.length, vip_seats: rows.filter((row) => row.vip).length };
}

export function echoWorkroomDraft(roomId: string, body: string, yolo = false) {
  if (yolo) throw new Error('YOLO cannot write workroom drafts');
  const draft: WorkroomDraft = {
    draft_id: `wrd_echo_${drafts.length + 1}`,
    room_id: roomId,
    body: body.trim(),
    status: 'APPROVAL_PENDING',
    sent: false,
    yolo: false,
  };
  drafts.push(draft);
  return draft;
}

export function echoWorkroomListDrafts(roomId: string) {
  const rows = drafts.filter((row) => row.room_id === roomId);
  return { drafts: rows, count: rows.length };
}

export function echoWorkroomApprove(draftId: string, approved = false) {
  if (!approved) throw new Error('missing approver — refuse');
  const row = drafts.find((item) => item.draft_id === draftId);
  if (!row) throw new Error('no workroom draft');
  row.status = 'ready';
  return row;
}

export function echoWorkroomDeny(draftId: string) {
  const index = drafts.findIndex((row) => row.draft_id === draftId);
  if (index < 0) throw new Error('no workroom draft');
  drafts.splice(index, 1);
  return {
    applied: false,
    draft_id: draftId,
    status: 'denied' as const,
    sent: false as const,
    yolo: false as const,
    computer_use: false as const,
    chrome_profile: false as const,
  };
}

export function resetEchoWorkroom(): void {
  rooms.length = 0;
  seats.length = 0;
  drafts.length = 0;
}
