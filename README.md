
原项目<a href="https://github.com/sansan0/TrendRadar" title="TrendRadar">
TrendRader</a>

## 相比原版的变更
1. 增加推送消息去重
2. 只支持Docker部署

## 本地推送去重模型

这个分支只支持 Docker 部署的本地推送去重，不依赖外部 LLM。

### 模型

请先在宿主机下载这两个模型，再通过 volume 挂载到容器：

- embedding: `intfloat/multilingual-e5-small`
- reranker: `BAAI/bge-reranker-base`

建议目录结构：

```text
models/
  dedup-embed/      # intfloat/multilingual-e5-small
  dedup-rerank/     # BAAI/bge-reranker-base
```

可从 Hugging Face 下载：

- https://huggingface.co/intfloat/multilingual-e5-small
- https://huggingface.co/BAAI/bge-reranker-base

默认开启 72 小时去重：

```text
DEDUP_ENABLED=true
DEDUP_WINDOW_HOURS=72
DEDUP_TOP_K=20
DEDUP_RERANK_THRESHOLD=0.98
DEDUP_STRICT_TIME_CONFLICT=true
DEDUP_DEBUG=false
```

### 去重策略

- 热榜主区 / 新增区 / RSS 区：本地语义去重
- 独立展示区：同源标题或 URL 完全一致才去重
- 如果同一条内容已经在复杂区展示，独立展示区不会再展示一次

