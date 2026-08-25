# How to add a reliability SLA

A reliability SLA is a named, bounded promise: this step finishes, fails,
is cancelled, or is declared stalled — it never spins. The toolkit lives
in `dream/reliability/`. You **call** it from the owning module; you do
not edit this how-to's neighbouring packages unless you own them.

## 1. Name the owner and the step

```python
from dream.reliability import CancelToken, Deadline, Watchdog

token = CancelToken(name="research.section")
deadline = Deadline.after(30.0, owner="research", step="section-2")
```

`owner` and `step` show up on `DeadlineExceeded` and in the watchdog
cause string. Use the package name and a short step id.

## 2. Cap every public wait

Never forward a client-supplied delay straight into `sleep` or `wait`.

```python
from dream.reliability import clamp_delay, clamp_timeout

delay = clamp_delay(params.get("step_delay"))          # hard max 2 s
timeout = clamp_timeout(params.get("timeout"), default=30.0)  # hard max 120 s
```

If the existing function already clamps (P4 `continue_plan` does), leave
it; do not add a second, looser clamp.

## 3. Adapt the stop flag you already have

Do not invent a parallel flag.

```python
from dream.reliability import adapt_agentmodes, adapt_research_stop

token = adapt_agentmodes(plan_token)          # P4 CancellationToken
token = adapt_research_stop(ctx.cancelled)    # P1 threading.Event
```

Then check it at every step boundary:

```python
token.throw_if_cancelled()
deadline.throw_if_exceeded()
```

Link a child process so `/stop` is a real kill:

```python
token.link_subprocess(proc)
```

## 4. Put a watchdog around work that can hang

```python
with Watchdog(deadline, token) as watchdog:
    result = watchdog.run(blocking_fn)

# or
result = await watchdog.run_async(coro)
```

On expiry the token is cancelled, `watchdog.cause` names the owner/step,
and the caller sees `DeadlineExceeded`. Do not swallow that into a retry
loop without a restart budget.

## 5. Give the turn a budget

```python
from dream.reliability import Budget, BudgetKind, ExhaustionAction

budget = Budget(time_s=60, tokens=4_096, output_bytes=200_000, owner="agent", step="turn")
budget.consume(BudgetKind.TOKENS, n)
text = budget.truncate_text(reply)
skip = budget.skip_if_exhausted(BudgetKind.TIME, rationale="section over time")
```

Money goes through the existing ledger:

```python
from dream.reliability import attach_ledger, consume_ledger_turn

attach_ledger(budget, ledger)
consume_ledger_turn(ledger)   # QuotaExceeded → BudgetExceeded (EN+FA)
```

Exhaustion text is bilingual. Do not invent a new English-only message.

## 6. Bound every list and every stream

```python
from dream.reliability import BoundedBuffer, OverflowPolicy, guarded_aiter

events = BoundedBuffer(maxlen=256, policy=OverflowPolicy.COALESCE)
events.put(payload, key=payload["type"])

async for chunk in guarded_aiter(producer, stall_timeout=5.0, token=token, name="reply"):
    send(chunk)
```

On the bridge, prefer the additive helper so existing callers stay put:

```python
from dream.bridge.streams import stream_with_stall_guard

chunks = stream_with_stall_guard(stream.chunks, stall_timeout=5.0)
```

Never wrap each poll in `asyncio.wait_for(anext(gen), …)` — that cancels
the generator.

## 7. SQLite: timeout first, then WAL

```python
from dream.reliability import connect_sqlite, run_transaction, claim_delivery, ensure_delivery_schema

conn = connect_sqlite(path)          # busy_timeout BEFORE journal_mode=WAL
run_transaction(conn, write_fn)
ensure_delivery_schema(conn)
claimed = claim_delivery(conn, reminder_id=rid, destination="telegram", fired_at=due)
```

Do not open a second connection that sets `journal_mode=WAL` before
`busy_timeout`. That is how `database is locked` leaks into the UI.

## 8. Supervise anything you spawn

```python
from dream.reliability import ResourceSupervisor

with ResourceSupervisor(idle_timeout=30.0) as sup:
    sup.spawn_thread("subagent-3", run)
    sup.spawn_process("helper", [sys.executable, "-m", "dream.helper"])
    sup.touch("subagent-3")
    sup.reap_stale()
```

Restarts follow the sidecar policy (3 tries, 2/5/10 s). After the
budget is spent, mark the worker failed and tell the user.

## 9. Step the degradation ladder, do not hide the failure

```python
from dream.reliability import Degradation

ladder = Degradation()
ladder.step_down("provider timeout")     # full → reduced
ladder.step_down("still failing")        # → offline/echo
ladder.fail("unknown state")             # → honest error
reply = ladder.bilingual()
```

Log the reason. The FA sentence is already in the ladder; do not drop it.

## 10. Prove it

Add a test under `tests/test_reliability*.py` or next to the owning
module that uses a **real** thread or process. A mock Event is not
enough for a cancel SLA. Keep the test inside a small deadline so CI
cannot hang. Do not put `assert` inside `if`.
