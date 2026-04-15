# Local Notification Dedup Design

**Date:** 2026-04-15

## Goal

为 TrendRadar 增加 Docker-only 的本地推送去重能力，降低 72 小时内重复新闻推送，同时尽量减少对 upstream 项目的侵入，优先通过新增文件实现。

## Constraints

- 仅支持 Docker 部署，不考虑 GitHub Actions。
- 不依赖外部 LLM 或在线向量服务。
- 模型文件不在镜像构建或运行时下载，由宿主机预下载后挂载进容器。
- 尽量不修改现有 `storage/`、`notification/dispatcher.py`、主库 schema。
- 推送记录必须保留 `platform_id` 和 `title`，供后续功能复用。

## Scope

本次设计只覆盖“通知推送前的去重”和“推送成功后的去重记录落库”。

不改变：

- 原始抓取与存储结果
- HTML 报告的原始生成逻辑
- 现有热榜/RSS 主数据库 schema
- AI 分析、翻译、调度器的既有语义

## Dedup Modes

### Complex Regions

适用区域：

- `hotlist`
- `new_items`
- `rss`
- `rss_new_items`

目标：

- 识别跨平台、跨来源但语义上重复的新闻
- 避免“同一事实不同标题”反复推送

判定方案：

- `URL` 精确命中
- 标题标准化后精确命中
- 本地 `Bi-Encoder` 召回候选
- 本地 `Cross-Encoder` 对标题对精排判重
- 数值、金额、百分比、否定、时间等事实冲突作为安全护栏，避免误杀

### Standalone Region

适用区域：

- `standalone`

目标：

- 仅避免同一数据源内的完全重复内容
- 保持独立展示区“按源完整展示”的语义

判定方案：

- 同源 + `normalized_url` 完全一致 => 去重
- URL 为空时，同源 + `normalized_title` 完全一致 => 去重
- 不做语义相似度匹配

## Shared Record Model

所有区域共用一张 sidecar SQLite 表，避免复杂区和独立展示区互相不可见，导致一条消息在同一次推送中展示两次。

建议表名：

- `sent_notification_records`

建议字段：

- `id`
- `source_type` - `hotlist | rss`
- `platform_id` - 热榜平台 ID 或 RSS feed ID
- `platform_name`
- `region_type` - `hotlist | new_items | rss | rss_new_items | standalone`
- `match_policy` - `semantic | exact`
- `title`
- `normalized_title`
- `url`
- `normalized_url`
- `fact_signature_json`
- `embedding_blob`
- `sent_at`
- `expires_at`
- `created_at`

说明：

- `embedding_blob` 对 `standalone` 可为空。
- `fact_signature_json` 对 `standalone` 可为空。
- `platform_id` 与 `title` 必须原样保存。

建议索引：

- `(expires_at)`
- `(source_type, platform_id, region_type)`
- `(normalized_url)`
- `(normalized_title)`
- `(sent_at)`

## Same-Push Dedup

仅依赖历史表不够，因为记录只会在推送成功后写入，无法阻止同一轮消息里复杂区和独立展示区各展示一次。

因此每次发送前还需要一个内存索引：

- `accepted_this_push`

处理顺序：

1. 生成所有候选新闻
2. 先和 `accepted_this_push` 比较
3. 再和 `sent_notification_records` 最近 72 小时记录比较
4. 通过者加入 `accepted_this_push`
5. 推送成功后，再批量写入 SQLite

区域优先级：

- 复杂区优先于 `standalone`

即：

- 若一条新闻已经在复杂区被接受，`standalone` 中再次出现时直接过滤
- 不让 `display.region_order` 影响去重优先级，避免行为不稳定

## Local Model Architecture

采用两阶段本地模型方案：

1. `Bi-Encoder` 召回
2. `Cross-Encoder` 精排判重

推荐模型：

- Embedding: `intfloat/multilingual-e5-small`
- Reranker: `BAAI/bge-reranker-base`

理由：

- 支持中英文混合场景，适配热榜 + RSS
- 本地可运行，效果明显优于纯规则或 `n-gram`
- 不依赖外部 LLM

## Title Dedup Logic

### Step 1: Exact Short-Circuit

按顺序做最快捷的精确命中：

- `normalized_url` 完全相同 => 重复
- `normalized_title` 完全相同 => 重复

### Step 2: Feature Extraction

提取轻量事实签名：

- 普通数字
- 百分比
- 金额
- 时间表达
- 否定词

说明：

- 这部分不负责“主判定”，只负责避免模型误杀。

### Step 3: Bi-Encoder Recall

对新标题生成 embedding，从近 72 小时记录中按余弦相似度召回 `top-k` 候选。

建议参数：

- `top_k = 20`

### Step 4: Cross-Encoder Re-Rank

对召回候选逐对打分，得到更稳定的“是否是同一条新闻”分数。

建议参数：

- `rerank_threshold = 0.82`

### Step 5: Fact Conflict Veto

即使重排分数高，也要检查事实冲突：

- 百分比冲突
- 金额冲突
- 关键数字冲突
- 否定语义冲突
- 时间冲突（可配置）

若存在冲突，则不去重。

## Docker-Only Deployment

模型目录由宿主机预下载并挂载。

建议容器内路径：

- `/models/dedup-embed`
- `/models/dedup-rerank`

建议环境变量：

- `DEDUP_ENABLED=true`
- `DEDUP_WINDOW_HOURS=72`
- `DEDUP_TOP_K=20`
- `DEDUP_RERANK_THRESHOLD=0.82`
- `DEDUP_STRICT_TIME_CONFLICT=true`
- `DEDUP_EMBED_MODEL_PATH=/models/dedup-embed`
- `DEDUP_RERANK_MODEL_PATH=/models/dedup-rerank`

运行行为：

- 若 dedup 启用但模型目录缺失，默认打印警告并降级为“不启用 dedup”
- 可后续扩展严格启动模式，但不作为首版必需项

## File Layout

新增目录：

- `trendradar/dedup/`

建议新增文件：

- `trendradar/dedup/__init__.py`
- `trendradar/dedup/config.py`
- `trendradar/dedup/models.py`
- `trendradar/dedup/store.py`
- `trendradar/dedup/normalizer.py`
- `trendradar/dedup/fact_extractor.py`
- `trendradar/dedup/embedder.py`
- `trendradar/dedup/reranker.py`
- `trendradar/dedup/matcher.py`
- `trendradar/dedup/filters.py`
- `trendradar/dedup/service.py`
- `trendradar/dedup/schema.sql`

## Minimal Integration Points

尽量只在这些既有文件做少量接线：

- `trendradar/__main__.py`
- `trendradar/core/loader.py`
- `docker/docker-compose.yml`
- `docker/Dockerfile`
- `README.md`

明确不改：

- `trendradar/storage/schema.sql`
- `trendradar/storage/rss_schema.sql`
- `trendradar/storage/sqlite_mixin.py`
- `trendradar/notification/dispatcher.py`

## High-Level Runtime Flow

1. 主流程生成 `stats / new_titles / rss_items / rss_new_items / standalone_data`
2. `DedupService.filter_before_send(...)` 统一转成候选项
3. 复杂区走 `semantic` 判重
4. `standalone` 走 `exact` 判重
5. 过滤结果回写原结构
6. 原有 `dispatch_all(...)` 继续发送
7. 若至少一个渠道发送成功，`DedupService.record_after_send(...)` 批量写库

## Verification Targets

首版至少验证：

- 同 URL 重复 => 拦截
- 同标题完全重复 => 拦截
- 同义改写 => 复杂区拦截
- 数值变化 => 复杂区保留
- 否定变化 => 复杂区保留
- `standalone` 同源 exact => 拦截
- 同一轮中复杂区与 `standalone` 重复 => 只保留复杂区
- 72 小时外记录 => 不影响当前推送

## Tradeoffs

优点：

- 本地运行，稳定性高
- 对 upstream 侵入小
- 不污染原始抓取和存储语义
- 复杂区和独立展示区边界清晰

代价：

- 需要额外模型依赖和本地模型目录
- 会增加一定 CPU / 内存占用
- 首版仍需基于真实新闻数据调阈值
