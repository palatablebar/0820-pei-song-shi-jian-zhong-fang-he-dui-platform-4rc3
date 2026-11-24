# 阶段接口

`POST /api/stages/<stage>` 接收 `multipart/form-data`。字段 `sample=dirty`、`sample=clean` 或 `file=<CSV>` 三选一。阶段为 `intake`、`prepare`、`calculate`、`policy`、`balance`。预览不入库。

`POST /api/runs` 接收同样的输入，另需表单字段 `actor`（值班员标识，1 至 40 字）；执行人登记为批次责任人。`GET /api/runs` 返回最近 50 批（含当前责任人）。`GET /api/runs/<id>` 查询一批和当前复核状态。

`PATCH /api/runs/<id>` 接收 `actor`、`revision`、`status` 和 `note`。状态使用 `APPROVED` 或 `HELD`。仅当前责任人可提交，否则返回 409 `OWNER_MISMATCH`。版本冲突返回 409 `STALE_REVIEW`，客户端读取新版本后重试。

`POST /api/runs/<id>/claim` 接收 JSON `actor`。原责任人已交回或守护期届满时接办成功，否则返回 409 `OWNER_ACTIVE`。守护期默认 1800 秒，可用环境变量 `OWNER_GUARD_SECONDS` 调整。责任人接办自己的批次为空操作。

`POST /api/runs/<id>/release` 接收 JSON `actor`，仅当前责任人可交回，交回后批次回到待接办状态。

批次 JSON 含 `owner`、`owner_since`、`guard_seconds` 与 `handovers`（每次认领、接办、交回的责任人与时间）。

`GET /api/runs/<id>/evidence` 下载内含运行清单、行号隔离、业务证据、复核信息和交接记录的 JSON。
