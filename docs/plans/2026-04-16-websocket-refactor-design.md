# WebSocket Realtime Refactor Design

**Date:** 2026-04-16

**Scope:** `dedup` and `websocket` only. Existing upstream hotlist/RSS/report logic should remain behaviorally unchanged except for the minimal wiring needed to host websocket runtime inside the main process.

## Goal

Refactor the uncommitted Jin10 websocket implementation into a maintainable realtime subsystem that:

- starts with the main TrendRadar process instead of running as a separate service,
- keeps `test_jin10_binary.py` as an end-to-end validation path,
- reuses one unified dedup pipeline across websocket and existing notification sources,
- makes websocket channels easy to extend,
- recovers automatically from failures,
- produces actionable logs and high-signal Feishu alerts for sustained failures.

## Hard Constraints

- Minimize invasive changes to upstream project code.
- Prefer putting new logic in a new package instead of modifying existing modules in place.
- Preserve existing dedup rules; only extend the interface and storage model as needed for realtime flow.
- `lastList` history from Jin10 participates in the same full pipeline as realtime messages.
- Websocket failures must not break the existing scheduled crawl and notification flow.

## Problems In Current Uncommitted Code

- Websocket logic is under `trendradar/crawler/websocket`, but it is not crawler logic; it is realtime ingestion and notification infrastructure.
- `jin10_notifier.py` duplicates dedup checks, storage reads, embedding logic, and Feishu sending instead of reusing `trendradar/dedup` and the shared notification layer.
- Runtime concerns are mixed together: connection management, Jin10 protocol handling, dedup, rendering, and delivery all live in the same slice.
- Current testing and debugging entry points are fragmented into many ad hoc scripts and docs, which raises maintenance and merge cost.
- Logging is mostly `print`-based and too noisy for long-running diagnosis while still missing structured high-level health signals.

## Target Package Layout

Create a new package: `trendradar/websocket`

Planned structure:

- `trendradar/websocket/__init__.py`
- `trendradar/websocket/config.py`
- `trendradar/websocket/runtime.py`
- `trendradar/websocket/logging.py`
- `trendradar/websocket/models.py`
- `trendradar/websocket/core/client.py`
- `trendradar/websocket/core/reconnect.py`
- `trendradar/websocket/core/channel.py`
- `trendradar/websocket/core/runner.py`
- `trendradar/websocket/pipeline/dedup.py`
- `trendradar/websocket/pipeline/feishu.py`
- `trendradar/websocket/pipeline/alerts.py`
- `trendradar/websocket/channels/jin10/binary_protocol.py`
- `trendradar/websocket/channels/jin10/channel.py`
- `trendradar/websocket/testing.py`

Responsibilities:

- `core`: generic websocket runtime, connection lifecycle, backoff, health accounting, queue handoff.
- `channels/jin10`: Jin10-specific handshake, decryption, parsing, and standard event conversion.
- `pipeline`: dedup adapter, realtime message formatting, Feishu sender reuse, alert throttling.
- `runtime`: main-process integration and lifecycle control.
- `testing`: end-to-end assembly helpers reused by `test_jin10_binary.py`.

The existing `trendradar/crawler/websocket` code becomes obsolete and should not remain on the runtime path.

## Main Process Integration

The main process stays synchronous. Do not convert `trendradar/__main__.py` into an async program.

Runtime model:

- `NewsAnalyzer` creates `WebSocketRuntime` during initialization when websocket is enabled.
- `WebSocketRuntime` owns a background thread with a dedicated `asyncio` event loop.
- One runtime hosts all websocket channel tasks.
- Channels publish normalized realtime events into a single in-process queue.
- One pipeline consumer serially executes `dedup -> send -> record` to avoid duplicate pushes caused by concurrent writers.
- `NewsAnalyzer.run()` shutdown always stops the runtime in `finally`, regardless of crawl success.

Failure isolation:

- Channel crash does not abort the main analyzer.
- The runtime attempts auto-recovery in the background.
- Existing crawl, RSS, report generation, and batch push flow continue unaffected.

## Unified Dedup Design

Dedup logic remains centralized in `trendradar/dedup`.

### API Extensions

Extend `DedupService` with single-item realtime methods:

- `check_realtime_candidate(candidate: CandidateNews, now_str: Any) -> Optional[Dict[str, Any]]`
- `record_realtime_candidate(candidate: CandidateNews, now_str: Any = None) -> int`

These methods reuse the same exact and semantic rules as batch notifications. The batch methods stay unchanged for current hotlist/RSS flow.

### Storage Extension

Extend `sent_notification_records` with optional `dedup_key`.

Purpose:

- allow hard dedup for sources that expose stable message ids,
- prevent websocket replay duplicates after reconnect,
- keep old sources working unchanged when `dedup_key` is empty.

For Jin10:

- `dedup_key = "jin10:<message_id>"`

Dedup order:

1. `dedup_key`
2. existing exact duplicate logic
3. existing semantic duplicate logic

This satisfies:

- the same Jin10 message id only pushes once,
- websocket-pushed content is still deduplicated against later hotlist/RSS notifications,
- future websocket channels can share the same persistence layer without new rules.

### Schema Migration

`DedupStore.initialize()` must become migration-safe instead of assuming a fresh database.

Required changes:

- create table if missing,
- add `dedup_key` column if the database was created by old code,
- create indexes if missing.

## Realtime Event Model

Introduce a small normalized model for pipeline processing.

Example fields:

- `channel`
- `event_type`
- `source_message_id`
- `dedup_key`
- `title`
- `content`
- `published_at`
- `detail_url`
- `raw_payload`
- `meta`

Every websocket channel maps protocol messages into this model. The pipeline does not know channel-specific parsing details.

## Delivery Design

### Message Push

Websocket realtime news keeps a compact Feishu rendering optimized for single-message updates.

Unification rule:

- reuse shared Feishu transport behavior where practical,
- keep websocket-specific compact rendering isolated in websocket pipeline,
- do not force realtime events through the large report renderer.

The realtime push path should:

1. format one compact message,
2. send via a reusable Feishu sender abstraction,
3. record dedup only after successful delivery.

### Alerting

Add websocket-specific alerting for sustained failures, not every exception.

Alert examples:

- consecutive reconnect failures hit threshold,
- channel disconnected longer than threshold,
- repeated protocol parse/decrypt failures beyond threshold,
- pipeline backlog above threshold,
- runtime worker restarted after failure,
- channel recovered after a sustained outage.

Alert requirements:

- alert cooldown to avoid spam,
- recovery notification after outage,
- alert path separated from realtime-news rendering logic,
- configuration support for using the normal Feishu webhook first, while allowing a future dedicated alert webhook.

## Logging Design

New websocket code uses a dedicated logger instead of raw `print`.

Logging goals:

- readable console summary,
- persistent file log for diagnosis,
- enough context to correlate reconnect, parse, dedup, and delivery failures.

Recommended file:

- `output/logs/websocket.log`

Important log events:

- runtime start and stop,
- channel connect success/failure,
- reconnect wait and counters,
- Jin10 key exchange and login status,
- message receive summary,
- dedup hit with reason (`dedup_key`, `exact`, `semantic`),
- push success/failure,
- queue backlog warnings,
- periodic health snapshots,
- alert sent / recovery sent.

Health snapshot fields:

- channel state,
- last message time,
- total messages,
- dedup filtered count,
- send success/failure count,
- consecutive failures,
- reconnect count,
- queue size.

## Testing Strategy

Keep `test_jin10_binary.py`, but convert it from an ad hoc script into an end-to-end validation entrypoint that uses the production runtime assembly.

`test_jin10_binary.py` must still validate:

- Jin10 websocket connect,
- key exchange and login,
- `lastList` handling,
- realtime event handling,
- dedup,
- Feishu send,
- runtime stats output.

Remove or retire the other websocket-only test and debug entry points that do not match the final architecture, including:

- `tests/test_websocket.py`
- `websocket_service.py`
- `debug_websocket.py`
- `debug_websocket_advanced.py`
- `debug_websocket_decrypt.py`
- analysis/debug-only websocket helper scripts that are no longer needed after protocol support is stabilized

Replace them with focused automated tests for:

- Jin10 protocol parsing and normalization,
- realtime dedup adapter behavior,
- runtime assembly and queue processing,
- alert throttling logic.

## Minimal Upstream Touch Points

Keep upstream modifications minimal and explicit:

- `trendradar/core/loader.py`
  Load websocket config into the main config object.
- `trendradar/context.py`
  Add lazy websocket runtime creation or config accessor as needed.
- `trendradar/__main__.py`
  Start and stop runtime from `NewsAnalyzer`.
- `trendradar/dedup/*`
  Add single-item realtime API and migration-safe `dedup_key` storage support.

Everything else should live under the new `trendradar/websocket` package.

## Additional Refactors Worth Doing In The Same Scope

- Split websocket news sending and websocket alert sending into separate pipeline helpers.
- Add runtime status snapshot APIs so health reporting and future diagnostics reuse the same state model.
- Keep channel implementations thin by pushing all reusable logic into `core` and `pipeline`.
- Avoid duplicating config parsing by merging websocket config into the existing main configuration loading path.

## Non-Goals

- Do not redesign the batch hotlist/RSS notification flow.
- Do not change the semantic dedup rules themselves.
- Do not move unrelated crawler/report/AI code.
- Do not build a general event bus for every future source beyond websocket in this refactor.
