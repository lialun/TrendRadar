# WebSocket Realtime Refactor Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a maintainable websocket runtime that starts with the main TrendRadar process, keeps Jin10 end-to-end validation, and unifies websocket dedup and Feishu delivery with existing notification history.

**Architecture:** Add a new `trendradar/websocket` package that owns websocket runtime, channel adapters, realtime pipeline, logging, and alerting. Extend `trendradar/dedup` with single-item realtime APIs and migration-safe `dedup_key` support, then add minimal main-process wiring in `trendradar/__main__.py`, `trendradar/context.py`, and config loading.

**Tech Stack:** Python 3.10+, `asyncio`, `threading`, `queue`, `sqlite3`, existing TrendRadar config loader, existing Feishu sender behavior, existing dedup matcher/embedder/reranker.

---

### Task 1: Add websocket config to main config loading

**Files:**
- Create: `trendradar/websocket/config.py`
- Modify: `trendradar/core/loader.py`
- Test: `tests/websocket/test_config.py`

**Step 1: Write the failing test**

```python
from trendradar.websocket.config import load_websocket_config


def test_load_websocket_config_reads_nested_notification_config():
    config_data = {
        "websocket": {
            "enabled": True,
            "health_log_interval_seconds": 300,
            "channels": {
                "jin10": {
                    "enabled": True,
                    "url": "wss://example.test/socket",
                }
            },
        }
    }

    config = load_websocket_config(config_data)

    assert config["WEBSOCKET"]["ENABLED"] is True
    assert config["WEBSOCKET"]["CHANNELS"]["jin10"]["URL"] == "wss://example.test/socket"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/websocket/test_config.py::test_load_websocket_config_reads_nested_notification_config -v`
Expected: FAIL with import or missing websocket config support.

**Step 3: Write minimal implementation**

```python
def load_websocket_config(config_data: Dict[str, Any]) -> Dict[str, Any]:
    websocket = config_data.get("websocket", {})
    return {
        "WEBSOCKET": {
            "ENABLED": websocket.get("enabled", False),
            "CHANNELS": {
                "jin10": {
                    "ENABLED": websocket.get("channels", {}).get("jin10", {}).get("enabled", False),
                    "URL": websocket.get("channels", {}).get("jin10", {}).get("url", ""),
                }
            },
        }
    }
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/websocket/test_config.py::test_load_websocket_config_reads_nested_notification_config -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/websocket/test_config.py trendradar/websocket/config.py trendradar/core/loader.py
git commit -m "feat: load websocket config into main config"
```

### Task 2: Extend dedup storage with realtime key support

**Files:**
- Modify: `trendradar/dedup/models.py`
- Modify: `trendradar/dedup/schema.sql`
- Modify: `trendradar/dedup/store.py`
- Test: `tests/dedup/test_store.py`

**Step 1: Write the failing test**

```python
def test_store_initialize_adds_dedup_key_column_for_existing_db(tmp_path):
    store = DedupStore(str(tmp_path))
    conn = sqlite3.connect(store.db_path)
    conn.execute(
        "CREATE TABLE sent_notification_records ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "source_type TEXT NOT NULL,"
        "platform_id TEXT NOT NULL,"
        "platform_name TEXT DEFAULT '',"
        "region_type TEXT NOT NULL,"
        "match_policy TEXT NOT NULL,"
        "title TEXT NOT NULL,"
        "normalized_title TEXT NOT NULL,"
        "url TEXT DEFAULT '',"
        "normalized_url TEXT DEFAULT '',"
        "fact_signature_json TEXT DEFAULT '{}',"
        "embedding_blob BLOB,"
        "sent_at INTEGER NOT NULL,"
        "expires_at INTEGER NOT NULL,"
        "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
    )
    conn.commit()
    conn.close()

    store.initialize()

    conn = sqlite3.connect(store.db_path)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(sent_notification_records)")}
    assert "dedup_key" in cols
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/dedup/test_store.py::test_store_initialize_adds_dedup_key_column_for_existing_db -v`
Expected: FAIL because migration logic does not exist.

**Step 3: Write minimal implementation**

```python
def _ensure_column(self, conn: sqlite3.Connection, table: str, column_sql: str, column_name: str) -> None:
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column_name not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column_sql}")
```

Also update schema and insert/select paths to read/write `dedup_key`.

**Step 4: Run test to verify it passes**

Run: `pytest tests/dedup/test_store.py::test_store_initialize_adds_dedup_key_column_for_existing_db -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/dedup/test_store.py trendradar/dedup/models.py trendradar/dedup/schema.sql trendradar/dedup/store.py
git commit -m "feat: add realtime dedup key storage support"
```

### Task 3: Add single-item realtime dedup APIs

**Files:**
- Modify: `trendradar/dedup/service.py`
- Modify: `trendradar/dedup/matcher.py`
- Test: `tests/dedup/test_realtime_service.py`

**Step 1: Write the failing test**

```python
def test_check_realtime_candidate_uses_dedup_key_before_title(tmp_path):
    service = DedupService(base_dir=str(tmp_path), config={"ENABLED": True, "WINDOW_HOURS": 72})
    service.store = DedupStore(str(tmp_path))
    service.store.initialize()
    candidate = CandidateNews(
        candidate_id="websocket:1",
        source_type="websocket",
        platform_id="jin10",
        platform_name="jin10",
        region_type="websocket",
        match_policy="exact",
        title="title a",
        normalized_title="title a",
        dedup_key="jin10:1",
    )
    service.record_realtime_candidate(candidate, "2026-04-16 10:00:00")

    duplicate = service.check_realtime_candidate(candidate, "2026-04-16 10:01:00")
    assert duplicate["reason"] == "dedup_key"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/dedup/test_realtime_service.py::test_check_realtime_candidate_uses_dedup_key_before_title -v`
Expected: FAIL because realtime APIs and `dedup_key` matching do not exist.

**Step 3: Write minimal implementation**

```python
def check_realtime_candidate(self, candidate: CandidateNews, now_str: Any) -> Optional[Dict[str, Any]]:
    history_records = self._load_recent_records(now_str)
    self._attach_embeddings([candidate])
    return self._check_duplicate(candidate, [], history_records)


def record_realtime_candidate(self, candidate: CandidateNews, now_str: Any = None) -> int:
    return self._insert_candidates([candidate], now_str)
```

Update duplicate checking so `dedup_key` is evaluated first.

**Step 4: Run test to verify it passes**

Run: `pytest tests/dedup/test_realtime_service.py::test_check_realtime_candidate_uses_dedup_key_before_title -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/dedup/test_realtime_service.py trendradar/dedup/service.py trendradar/dedup/matcher.py
git commit -m "feat: add realtime dedup service APIs"
```

### Task 4: Build reusable websocket runtime core

**Files:**
- Create: `trendradar/websocket/__init__.py`
- Create: `trendradar/websocket/models.py`
- Create: `trendradar/websocket/logging.py`
- Create: `trendradar/websocket/core/reconnect.py`
- Create: `trendradar/websocket/core/client.py`
- Create: `trendradar/websocket/core/channel.py`
- Create: `trendradar/websocket/core/runner.py`
- Create: `trendradar/websocket/runtime.py`
- Test: `tests/websocket/test_runtime.py`

**Step 1: Write the failing test**

```python
def test_runtime_processes_events_from_channel_queue(tmp_path):
    runtime = WebSocketRuntime(
        config={"ENABLED": True, "CHANNELS": {}, "PROCESSING": {"QUEUE_MAX_SIZE": 10}},
        dedup_service=FakeDedupService(),
        feishu_sender=FakeFeishuSender(),
    )
    runtime._pipeline.enqueue(FakeRealtimeEvent("jin10", "jin10:1", "headline"))
    runtime._pipeline.process_next()
    assert runtime._pipeline.stats["sent_success"] == 1
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/websocket/test_runtime.py::test_runtime_processes_events_from_channel_queue -v`
Expected: FAIL because runtime package does not exist.

**Step 3: Write minimal implementation**

```python
class WebSocketRuntime:
    def __init__(self, config, dedup_service, feishu_sender, alert_sender=None):
        self.config = config
        self.dedup_service = dedup_service
        self.feishu_sender = feishu_sender
        self.alert_sender = alert_sender
```

Add queue-backed pipeline helpers and state snapshot support.

**Step 4: Run test to verify it passes**

Run: `pytest tests/websocket/test_runtime.py::test_runtime_processes_events_from_channel_queue -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/websocket/test_runtime.py trendradar/websocket
git commit -m "feat: add websocket runtime core"
```

### Task 5: Implement Jin10 binary channel adapter on top of runtime core

**Files:**
- Create: `trendradar/websocket/channels/jin10/__init__.py`
- Create: `trendradar/websocket/channels/jin10/binary_protocol.py`
- Create: `trendradar/websocket/channels/jin10/channel.py`
- Test: `tests/websocket/test_jin10_channel.py`

**Step 1: Write the failing test**

```python
def test_jin10_channel_turns_flash_message_into_realtime_event():
    channel = Jin10Channel(config={"URL": "wss://example.test/socket"})
    event = channel._build_realtime_event(
        msg_id=1000,
        payload={
            "id": 123,
            "time": "2026-04-16 10:00:00",
            "data": {"title": "A", "content": "B"},
        },
    )
    assert event.dedup_key == "jin10:123"
    assert event.title == "A"
    assert event.content == "B"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/websocket/test_jin10_channel.py::test_jin10_channel_turns_flash_message_into_realtime_event -v`
Expected: FAIL because Jin10 channel adapter does not exist.

**Step 3: Write minimal implementation**

```python
def _build_realtime_event(self, msg_id: int, payload: Dict[str, Any]) -> RealtimeEvent:
    data = payload.get("data", {})
    message_id = str(payload.get("id", ""))
    return RealtimeEvent(
        channel="jin10",
        event_type=str(msg_id),
        source_message_id=message_id,
        dedup_key=f"jin10:{message_id}" if message_id else "",
        title=data.get("title", "").strip(),
        content=data.get("content", "").strip(),
        published_at=payload.get("time", ""),
        raw_payload=payload,
    )
```

Port the proven binary parsing pieces from the uncommitted implementation into the new package.

**Step 4: Run test to verify it passes**

Run: `pytest tests/websocket/test_jin10_channel.py::test_jin10_channel_turns_flash_message_into_realtime_event -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/websocket/test_jin10_channel.py trendradar/websocket/channels/jin10
git commit -m "feat: add jin10 websocket channel adapter"
```

### Task 6: Add realtime pipeline delivery and alerts

**Files:**
- Create: `trendradar/websocket/pipeline/dedup.py`
- Create: `trendradar/websocket/pipeline/feishu.py`
- Create: `trendradar/websocket/pipeline/alerts.py`
- Test: `tests/websocket/test_alerts.py`
- Test: `tests/websocket/test_pipeline.py`

**Step 1: Write the failing test**

```python
def test_alerts_are_rate_limited_by_key_and_cooldown():
    sender = FakeAlertSender()
    alerts = AlertManager(sender=sender, cooldown_seconds=1800)
    alerts.notify_failure("jin10:disconnect", "failed")
    alerts.notify_failure("jin10:disconnect", "failed again")
    assert sender.sent_count == 1
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/websocket/test_alerts.py::test_alerts_are_rate_limited_by_key_and_cooldown -v`
Expected: FAIL because alert throttling does not exist.

**Step 3: Write minimal implementation**

```python
class AlertManager:
    def __init__(self, sender, cooldown_seconds: int):
        self.sender = sender
        self.cooldown_seconds = cooldown_seconds
        self._last_sent = {}

    def notify_failure(self, key: str, message: str) -> bool:
        ...
```

Add compact websocket Feishu rendering and send-after-dedup success ordering.

**Step 4: Run test to verify it passes**

Run: `pytest tests/websocket/test_alerts.py::test_alerts_are_rate_limited_by_key_and_cooldown -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/websocket/test_alerts.py tests/websocket/test_pipeline.py trendradar/websocket/pipeline
git commit -m "feat: add websocket delivery pipeline and alerts"
```

### Task 7: Wire runtime into main process lifecycle

**Files:**
- Modify: `trendradar/context.py`
- Modify: `trendradar/__main__.py`
- Test: `tests/websocket/test_main_integration.py`

**Step 1: Write the failing test**

```python
def test_news_analyzer_starts_and_stops_websocket_runtime(mocker):
    runtime = mocker.Mock()
    mocker.patch("trendradar.__main__.build_websocket_runtime", return_value=runtime)
    analyzer = NewsAnalyzer(config=build_test_config(websocket_enabled=True))
    analyzer.run()
    runtime.start.assert_called_once()
    runtime.stop.assert_called_once()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/websocket/test_main_integration.py::test_news_analyzer_starts_and_stops_websocket_runtime -v`
Expected: FAIL because runtime is not wired into `NewsAnalyzer`.

**Step 3: Write minimal implementation**

```python
class NewsAnalyzer:
    def __init__(self, config=None):
        ...
        self.websocket_runtime = build_websocket_runtime(self.ctx, self.dedup_service)
        if self.websocket_runtime:
            self.websocket_runtime.start()

    def run(self) -> None:
        try:
            ...
        finally:
            if self.websocket_runtime:
                self.websocket_runtime.stop()
            self.ctx.cleanup()
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/websocket/test_main_integration.py::test_news_analyzer_starts_and_stops_websocket_runtime -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/websocket/test_main_integration.py trendradar/context.py trendradar/__main__.py
git commit -m "feat: run websocket runtime inside main process"
```

### Task 8: Preserve `test_jin10_binary.py` as the end-to-end validation entrypoint

**Files:**
- Modify: `test_jin10_binary.py`
- Create: `trendradar/websocket/testing.py`
- Test: `tests/websocket/test_testing_entrypoint.py`

**Step 1: Write the failing test**

```python
def test_build_jin10_test_runtime_returns_runtime_and_stats_printer():
    runtime, printer = build_jin10_test_runtime(config={"WEBSOCKET": {"ENABLED": True}})
    assert runtime is not None
    assert callable(printer)
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/websocket/test_testing_entrypoint.py::test_build_jin10_test_runtime_returns_runtime_and_stats_printer -v`
Expected: FAIL because testing assembly helpers do not exist.

**Step 3: Write minimal implementation**

```python
def build_jin10_test_runtime(config: Dict[str, Any]) -> Tuple[WebSocketRuntime, Callable[[], None]]:
    runtime = WebSocketRuntime(...)
    return runtime, runtime.print_stats
```

Refactor `test_jin10_binary.py` so it uses the production runtime assembly instead of a private notifier.

**Step 4: Run test to verify it passes**

Run: `pytest tests/websocket/test_testing_entrypoint.py::test_build_jin10_test_runtime_returns_runtime_and_stats_printer -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/websocket/test_testing_entrypoint.py test_jin10_binary.py trendradar/websocket/testing.py
git commit -m "refactor: keep jin10 binary test on production websocket runtime"
```

### Task 9: Remove obsolete websocket code and debug entrypoints

**Files:**
- Delete: `tests/test_websocket.py`
- Delete: `websocket_service.py`
- Delete: `debug_websocket.py`
- Delete: `debug_websocket_advanced.py`
- Delete: `debug_websocket_decrypt.py`
- Delete: `trendradar/crawler/websocket/__init__.py`
- Delete: `trendradar/crawler/websocket/client.py`
- Delete: `trendradar/crawler/websocket/jin10_binary_client.py`
- Delete: `trendradar/crawler/websocket/jin10_client.py`
- Delete: `trendradar/crawler/websocket/jin10_notifier.py`
- Delete: `trendradar/crawler/websocket/manager.py`
- Delete: `trendradar/crawler/websocket/reconnect.py`
- Modify: `docs/WEBSOCKET_GUIDE.md`

**Step 1: Write the failing test**

```python
def test_no_legacy_websocket_import_path_remains():
    with pytest.raises(ModuleNotFoundError):
        __import__("trendradar.crawler.websocket.manager")
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/websocket/test_cleanup.py::test_no_legacy_websocket_import_path_remains -v`
Expected: FAIL because legacy modules still exist.

**Step 3: Write minimal implementation**

Delete the obsolete runtime path and update docs to point to the new websocket package.

**Step 4: Run test to verify it passes**

Run: `pytest tests/websocket/test_cleanup.py::test_no_legacy_websocket_import_path_remains -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/websocket/test_cleanup.py docs/WEBSOCKET_GUIDE.md
git add -u
git commit -m "refactor: remove legacy websocket implementation"
```

### Task 10: Verify the retained Jin10 flow and targeted regression coverage

**Files:**
- Test: `tests/dedup/test_realtime_service.py`
- Test: `tests/websocket/test_config.py`
- Test: `tests/websocket/test_runtime.py`
- Test: `tests/websocket/test_jin10_channel.py`
- Test: `tests/websocket/test_alerts.py`
- Test: `tests/websocket/test_pipeline.py`
- Test: `tests/websocket/test_main_integration.py`
- Test: `tests/websocket/test_testing_entrypoint.py`

**Step 1: Run focused automated tests**

Run: `pytest tests/dedup/test_realtime_service.py tests/websocket -v`
Expected: PASS

**Step 2: Run syntax validation**

Run: `python -m compileall trendradar test_jin10_binary.py tests/websocket`
Expected: PASS

**Step 3: Run manual Jin10 validation entrypoint**

Run: `python test_jin10_binary.py`
Expected: Connects to Jin10, handles `lastList`, deduplicates repeated items, pushes via Feishu when configured, and prints runtime stats.

**Step 4: Review runtime logs**

Check: `output/logs/websocket.log`
Expected: startup, health snapshot, reconnect, dedup, and send logs are present and readable.

**Step 5: Commit**

```bash
git add tests/dedup/test_realtime_service.py tests/websocket test_jin10_binary.py trendradar output/logs/websocket.log
git commit -m "test: verify websocket realtime refactor"
```
