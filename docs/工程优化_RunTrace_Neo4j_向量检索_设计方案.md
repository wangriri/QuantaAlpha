# QuantaAlpha 工程优化设计方案：Run Trace、全局因子库、Neo4j 谱系图与向量经验召回

版本：v0.1  
日期：2026-08-19  
定位：方案评审稿，先统一结构和数据契约，后续再进入实现。

---

## 1. 背景与目标

当前 QuantaAlpha 已经能完成一轮因子挖掘，但从工程化、复盘和持续积累角度看，存在几个关键问题：

1. **每次 run 的过程没有结构化沉淀**  
   当前日志和结果文件可以看，但很难系统回答：
   - 这个因子是从哪个用户研究主题来的？
   - Planning Agent 拆出了哪些方向？
   - 这个因子来自 original、mutation 还是 crossover？
   - 公式生成失败过几次？
   - 回测失败是因为因子值为空、数据缺失，还是指标不达标？

2. **因子库不是全局持续累积的知识库**  
   每次 run 容易生成新的因子库，历史因子的成功/失败经验、相关性、启用状态、谱系关系没有形成全局可查询资产。

3. **评价机制需要替换和增强**  
   后续计划去掉 Qlib 回测方式，改用内部回测工具，并引入更符合当前业务判断的单因子评价流程。

4. **后续希望支持“重建”和“经验召回”**  
   未来希望：
   - 根据一次 run 的结构化文件重建流程图。
   - 输入一个新的研究主题，自动找历史相关方向、假设、因子、反馈、失败经验作为 LLM 上下文。
   - 通过因子谱系知道 mutation / crossover 是从哪些 parent 来的。

因此，本方案设计一套统一的工程底座：

```text
结构化运行记录 Run Trace
  + 事件流 events.jsonl
  + 单次 run 图索引 run_graph.json
  + 全局因子库 Global Factor Library
  + 内部回测统一结果格式
  + Neo4j 因子谱系图
  + 向量检索历史经验召回
```

核心原则：

```text
文件系统保存完整原始材料；
整体目录结构仍按 run / round / task / step / factor / attempt 分层；
每一步的输出单独保存，不把不同步骤混在同一个大 JSON 里；
每个步骤文件内部必须同时保留 raw 原始输出和 parsed 结构化结果；
events.jsonl 保存不可篡改的运行账本；
run_graph.json 支持单次 run 的 UI 重建；
全局因子库管理因子版本、状态、指标和相关性；
Neo4j 保存跨 run、跨因子的关系网络；
向量索引用于语义相关经验召回。
```

---

## 2. 当前代码真实执行结构确认

当前 evolution 模式下，真实结构应理解为：

```text
一次 run
  └─ 多个 round
      └─ 每个 round 有多个 task
          └─ 每个 task 跑一次 AlphaAgentLoop
              └─ 通常生成 1 个 hypothesis
                  └─ 这个 hypothesis 生成多个 factor / formula
                      └─ formula 生成阶段内部可能多次 retry
```

注意：

1. **task 和 direction 不能完全等同**
   - original round 中，task 通常对应 Planning Agent 拆出的 direction。
   - mutation round 中，task 通常对应一个 parent trajectory 的变异。
   - crossover round 中，task 通常对应多个 parent trajectories 的融合。

2. **当前 evolution 模式下，一个 task 通常生成一个 hypothesis**
   - 因为每个 task 默认跑 `steps_per_loop = 5`。
   - 这 5 步分别是：hypothesis、experiment/factors、factor compute、backtest、feedback。

3. **一个 hypothesis 可以生成多个 factor**
   - Prompt 中要求每次生成 2-3 个 factors。
   - 实际数量取决于 LLM 返回 JSON 中顶层 factor 条目数量。

4. **formula retry 当前不是显式节点**
   - 目前代码内部会因 JSON parse 失败、表达式不可解析、复杂度/重复度不合格而重试。
   - 但这些 attempt 没有被显式保存。
   - 本方案建议把每次 attempt 结构化保存。

5. **因子值计算和回测粒度不同**
   - 因子值计算：每个 factor 可以单独执行，生成自己的 result / factor values。
   - 回测评价：后续内部回测方案建议按“单因子评价”为主，同时一轮内多个因子需要 batch-level 选择和去重。

---

## 3. 总体架构

### 3.1 模块划分

```text
quantaalpha/
  tracing/
    recorder.py            # 运行时写节点文件、events.jsonl
    schema.py              # Pydantic schema：Run、Round、Task、Node、Edge、Artifact
    serializers.py         # 把 hypothesis / factor / feedback / metrics 转成 JSON
    graph_builder.py       # 从 events.jsonl 生成 run_graph.json

  evaluation/
    adapter_base.py         # BacktestAdapter 抽象接口
    internal_adapter.py     # 内部回测工具适配器
    metrics.py              # IC、ICIR、十组、多空收益差、超额夏普
    selection.py            # 一轮内因子分组、相关性去重、保留逻辑

  factor_store/
    global_library.py       # 全局因子库写入、查询、状态管理
    status.py               # Factor Lifecycle 状态机
    similarity.py           # 因子相关性、表达式相似、语义相似

  graph_store/
    neo4j_sync.py           # 从结构化文件同步到 Neo4j
    cypher_templates.py     # 常用 Cypher 查询模板
    vector_retriever.py     # Neo4j vector search / 混合检索
```

### 3.2 数据流

```text
运行开始
  ↓
RunRecorder 创建 run 目录
  ↓
Planning / Task / Agent / Evaluation 按步骤分别写 JSON 和 events.jsonl
  ↓
GraphBuilder 从 events.jsonl 生成 run_graph.json
  ↓
GlobalFactorLibrary 接收通过评价的因子和失败经验
  ↓
Neo4jSync 同步轻量节点、边、状态、指标、文件路径
  ↓
VectorRetriever 支持新主题召回历史经验
```

### 3.3 存储职责边界

| 存储 | 负责什么 | 不负责什么 |
|---|---|---|
| 文件系统 | 每一步的原始 prompt、LLM 输出、程序输出、节点 JSON、H5、Parquet、日志 | 复杂跨 run 查询 |
| events.jsonl | append-only 运行事件账本 | 大段业务内容 |
| run_graph.json | 单次 run 的节点、边、分组索引和摘要 | 跨 run 全局查询 |
| DuckDB / SQLite | 因子指标、相关性矩阵、跨 run 统计 | 谱系路径查询 |
| Neo4j | 因子谱系、parent-child、mutation/crossover、相似关系、语义召回索引 | 大文件、完整 prompt、完整回测明细 |
| 向量索引 | 语义相似方向/假设/反馈召回 | 数值因子相关性计算 |

---

## 4. 目录结构设计

### 4.1 单次 run 目录

示例：`max_rounds = 3`，包含 original、mutation、crossover。

```text
runs/
  run_20260819_153000/
    00_run_summary.json                  # 本次 run 总摘要
    01_user_input.json                   # 用户输入和前端参数
    02_config_snapshot.yaml              # 本次实际使用配置快照
    03_run_graph.json                    # 单次 run 流程图索引
    04_events.jsonl                      # append-only 原始事件流
    05_environment.json                  # 代码版本、数据版本、LLM 配置，不含密钥

    00_planning/
      00_prompt.json                     # Planning Agent 的完整 prompt 和变量
      01_output.json                     # Planning Agent 原始输出 raw_response + 解析后的 directions

    round_00_original/
      00_round_summary.json              # 第 0 轮摘要

      task_000_original_direction_000/
        00_task.json                     # task 元信息
        01_direction.json                # 具体方向文本，含来源
        02_alpha_loop.json               # 本 task 的 AlphaAgentLoop 运行摘要和步骤索引
        03_hypothesis.json               # Hypothesis Agent 的 raw_response + parsed hypothesis
        04_experiment.json               # Factor Generation Agent 的 raw_response + parsed factors

        05_factors/
          factor_000/
            00_factor.json               # 因子定义：name、expression、features、operators，含 LLM 原文引用
            01_formula_attempts/
              attempt_000.json           # 第一次公式尝试：raw expression、parse、validation
              attempt_001.json           # 如果失败/修正，保存第二次尝试，不覆盖第一次
            02_factor_values_ref.json    # 因子值文件引用
            03_factor_evaluation.json    # 单因子评价汇总，含回测原始输出引用
          factor_001/
            同上

        06_batch_evaluation.json         # 本 task 内多个因子的整体评估和筛选
        07_feedback.json                 # Feedback Agent 的 raw_response + parsed feedback
        08_saved_factors.json            # 入库结果：candidate / active / rejected 等

    round_01_mutation/
      00_round_summary.json

      task_000_mutation/
        00_task.json
        01_parent_refs.json              # mutation 来自哪个 parent trajectory / factor / task
        02_mutation_prompt.json          # Mutation Agent prompt
        03_mutation_output.json          # Mutation Agent raw_response + parsed strategy_suffix / 新方向
        04_alpha_loop.json
        05_hypothesis.json
        06_experiment.json
        07_factors/
          factor_000/
            00_factor.json
            01_formula_attempts/
            02_factor_values_ref.json
            03_factor_evaluation.json
        08_batch_evaluation.json
        09_feedback.json
        10_saved_factors.json

    round_02_crossover/
      00_round_summary.json

      task_000_crossover/
        00_task.json
        01_parent_refs.json              # crossover 来自多个 parent
        02_crossover_prompt.json
        03_crossover_output.json         # Crossover Agent raw_response + parsed strategy_suffix / 新方向
        04_alpha_loop.json
        05_hypothesis.json
        06_experiment.json
        07_factors/
        08_batch_evaluation.json
        09_feedback.json
        10_saved_factors.json
```

这版目录的核心思想是：

```text
按流程步骤分开保存，不混文件。
```

其中：

1. 每个 Agent / 程序步骤都有自己的 JSON 文件。
2. 每个 JSON 文件内部都保留 `raw` 原始输出和 `parsed` 结构化结果。
3. 公式 retry 不覆盖旧文件，而是在 `01_formula_attempts/` 下按 attempt 保存。
4. 因子值、回测明细等大文件不强制转 JSON，只在 ref 文件中保存路径和生成口径。
5. `run_graph.json` 用这些步骤文件的路径串起整个流程。

### 4.2 命名规则

建议同时使用数字、语义和 ID：

```text
数字：保证文件排序
语义：人能看懂
ID：程序能唯一识别
```

示例：

```text
03_hypothesis.json
07_factors/factor_000/03_factor_evaluation.json
task_000_original_direction_000
round_02_crossover
```

不要只用：

```text
01.json
feedback.json
factor.json
```

原因：

1. 只用数字，人看不懂。
2. 只用英文，文件排序混乱。
3. 不含 ID，跨 run 或跨 task 容易冲突。

---

## 5. 统一 ID 设计

所有模块必须共享同一套稳定 ID。

### 5.1 主 ID

```text
run_id
  run_20260819_153000

round_id
  run_20260819_153000.round_00

task_id
  run_20260819_153000.round_00.task_000

hypothesis_id
  run_20260819_153000.round_00.task_000.hyp_000

factor_id
  run_20260819_153000.round_00.task_000.factor_000

factor_version_id
  gf_000001.v001

attempt_id
  run_20260819_153000.round_00.task_000.factor_000.attempt_000

evaluation_id
  run_20260819_153000.round_00.task_000.factor_000.eval_000
```

### 5.2 全局因子 ID

运行中的 factor 是局部产物，进入全局因子库后应生成全局 ID：

```text
source_factor_id = run_20260819_153000.round_00.task_000.factor_000
global_factor_id = gf_000001
factor_version_id = gf_000001.v001
```

原因：

1. 同一个公式可能来自不同 run。
2. 同一个因子可能后续修正公式、修正描述、换数据区间。
3. 全局启用/停用状态应挂在 global factor 或 version 上，而不是只挂在一次 run 的局部 factor 上。

---

## 6. 步骤 JSON 统一格式

整体仍然是“每一步一个文件”。  
为了保证每一步既能被程序读取，又能被人复盘，每个步骤 JSON 建议使用统一公共头，并在业务内容里同时保存原始输出和结构化结果。

### 6.1 步骤文件公共头

```json
{
  "schema_version": "1.0",
  "run_id": "run_20260819_153000",
  "node_id": "run_20260819_153000.round_00.task_000.hyp_000",
  "type": "hypothesis",
  "phase": "original",
  "round_idx": 0,
  "task_id": "run_20260819_153000.round_00.task_000",
  "status": "success",
  "input_refs": [],
  "input_refs": [],
  "output_refs": [],
  "started_at": "2026-08-19T15:30:00+08:00",
  "ended_at": "2026-08-19T15:31:00+08:00",
  "error": null,
  "payload": {}
}
```

字段说明：

| 字段 | 说明 |
|---|---|
| `schema_version` | JSON schema 版本，后续字段变更必须升级 |
| `run_id` | 所属 run |
| `node_id` | 全局唯一节点 ID |
| `type` | 节点类型，如 planning、task、hypothesis、factor、evaluation |
| `phase` | original / mutation / crossover |
| `round_idx` | 第几轮 |
| `task_id` | 所属 task |
| `status` | running / success / failed / skipped / cancelled |
| `input_refs` | 上游文件引用 |
| `output_refs` | 下游文件引用 |
| `error` | 失败信息，成功时为 null |
| `payload` | 当前步骤自己的业务内容，必须保留 raw 和 parsed |

### 6.2 每一步的 payload 标准结构

每个步骤文件的 `payload` 推荐统一包含：

```json
{
  "payload": {
    "input": {},
    "raw": {
      "request_messages": [],
      "system_prompt": "...",
      "user_prompt": "...",
      "response_text": "...",
      "response_metadata": {}
    },
    "parsed": {
      "ok": true,
      "data": {}
    },
    "parser": {
      "parser_name": "json_repair_then_pydantic",
      "attempt_count": 1,
      "warnings": []
    },
    "artifacts": []
  }
}
```

不同步骤可以扩展不同字段，但不要丢掉 `raw`。

例如：

```json
{
  "raw": {
    "request_messages": [],
    "response_text": "...",
    "response_metadata": {}
  },
  "parsed": {
    "ok": true,
    "data": {}
  },
  "parser": {
    "parser_name": "json_repair_then_pydantic",
    "attempt_count": 1,
    "warnings": []
  }
}
```

规则：

1. `raw.response_text` 必须原样保存，不因为解析成功就丢弃。
2. `parsed.data` 是程序用的结构化结果。
3. 如果解析失败，也要保存失败前的原文、错误和修复尝试。
4. 对外展示和 Neo4j 同步优先使用 `parsed.data`，复盘和 debug 看 `raw`。
5. 不同步骤之间不要混写：hypothesis 的 raw 不放进 experiment，evaluation 的原始结果不放进 factor 定义。

---

## 7. 关键文件详细数据设计

本节采用推荐落地方案：

```text
流程步骤文件保持拆分；每个步骤文件内部保存 raw + parsed。
```

也就是说：

```text
不要把 hypothesis、experiment、factor、evaluation 混到一个 task 级总文件里；
也不要只保存清洗后的 parsed 结果。
```

真正推荐的关键文件清单如下。

### 7.0 推荐关键步骤文件清单

| 文件 | 粒度 | 主要保存什么 | raw 保存要求 |
|---|---|---|---|
| `00_run_summary.json` | 一次 run | run 总摘要、状态、指标汇总、目录索引 | 保存原始异常摘要和运行日志引用 |
| `01_user_input.json` | 一次 run | 用户输入、前端参数 | 保存前端提交的原始 payload |
| `02_config_snapshot.yaml` | 一次 run | 本次实际使用配置 | 保存脱敏后的完整配置快照 |
| `03_run_graph.json` | 一次 run | 节点、边、文件路径、摘要 | 不保存大段 raw，只做索引 |
| `04_events.jsonl` | 一次 run | append-only 事件流 | 记录事件和路径，不放大段业务内容 |
| `05_environment.json` | 一次 run | 代码版本、数据版本、LLM 配置 | 脱敏保存，不保存 key/password |
| `00_planning/00_prompt.json` | planning | Planning Agent prompt | 保存完整 system/user prompt 和变量 |
| `00_planning/01_output.json` | planning | 拆出的 directions | 保存 LLM raw_response 和 parsed directions |
| `round_xx/00_round_summary.json` | round | 本轮任务列表、任务来源、成功失败数量 | 保存本轮原始异常摘要 |
| `task_xxx/00_task.json` | task | task 元信息 | 保存任务创建时的原始参数 |
| `task_xxx/01_direction.json` | task | 本 task 使用的方向 | 保存原始方向文本和来源 |
| `task_xxx/02_alpha_loop.json` | task | AlphaAgentLoop 步骤索引 | 保存每一步文件路径和执行状态 |
| `task_xxx/03_hypothesis.json` | task step | Hypothesis Agent 输出 | 保存完整 prompt、raw_response、parsed hypothesis |
| `task_xxx/04_experiment.json` | task step | Factor Generation Agent 输出 | 保存完整 prompt、raw_response、parsed factor list |
| `factor_xxx/00_factor.json` | factor | 单个因子定义 | 保存 LLM 原始定义、标准化表达式、来源 |
| `factor_xxx/01_formula_attempts/attempt_xxx.json` | formula attempt | 单次公式尝试 | 保存 raw expression、parse 结果、validation、retry feedback |
| `factor_xxx/02_factor_values_ref.json` | factor artifact | 因子值文件路径和生成口径 | 保存计算日志、数据范围、缺失值处理摘要 |
| `factor_xxx/03_factor_evaluation.json` | factor evaluation | 单因子评价结果 | 保存内部回测工具原始输出引用和 parsed 指标 |
| `task_xxx/06_batch_evaluation.json` | task evaluation | 本 task 内多个因子的整体筛选 | 保存原始筛选输入、相关性矩阵引用、parsed 决策 |
| `task_xxx/07_feedback.json` | task step | Feedback Agent 输出 | 保存完整 prompt、raw_response、parsed feedback |
| `task_xxx/08_saved_factors.json` | task output | 因子入库结果 | 保存写库请求、写库结果、状态变化事件 |

注释：

```text
文件粒度仍然跟流程图节点一致。
每个文件是一件事情。
原始输出保存在这件事情自己的文件里。
```

### 7.1 `01_user_input.json`

```json
{
  "schema_version": "1.0",
  "run_id": "run_20260819_153000",
  "research_topic": "挖掘放量下跌后的短期反转因子",
  "frontend_params": {
    "num_directions": 2,
    "max_rounds": 3,
    "mutation_enabled": true,
    "crossover_enabled": true,
    "parallel_enabled": false
  },
  "submitted_by": "user",
  "submitted_at": "2026-08-19T15:30:00+08:00"
}
```

### 7.2 `05_environment.json`

不能保存 API Key、MongoDB 密码等敏感信息。

```json
{
  "schema_version": "1.0",
  "run_id": "run_20260819_153000",
  "code": {
    "git_commit": "abc123",
    "git_branch": "main",
    "dirty": true,
    "dirty_files": ["quantaalpha/pipeline/loop.py"]
  },
  "runtime": {
    "python_version": "3.11",
    "platform": "macOS",
    "package_lock_ref": "requirements.txt"
  },
  "data": {
    "data_source_alias": "internal_mongodb_qlib_converted",
    "data_version": "daily_20260819",
    "calendar_range": ["2024-01-01", "2026-08-19"],
    "universe": "all_a_share",
    "frequency": "daily"
  },
  "llm": {
    "provider": "deepseek",
    "model": "deepseek-v3",
    "api_base_alias": "configured_openai_compatible",
    "temperature": 0.7
  }
}
```

### 7.3 `00_planning/00_prompt.json`

```json
{
  "schema_version": "1.0",
  "node_id": "run_20260819_153000.planning.prompt",
  "type": "llm_prompt",
  "actor": "PlanningAgent",
  "model": "deepseek-v3",
  "system_prompt": "...",
  "user_prompt": "...",
  "prompt_variables": {
    "initial_direction": "挖掘放量下跌后的短期反转因子",
    "n": 2
  }
}
```

### 7.4 `00_planning/01_output.json`

```json
{
  "schema_version": "1.0",
  "node_id": "run_20260819_153000.planning.output",
  "type": "planning_output",
  "status": "success",
  "raw": {
    "system_prompt_ref": "00_prompt.json#system_prompt",
    "user_prompt_ref": "00_prompt.json#user_prompt",
    "response_text": "{\"directions\": [...] }"
  },
  "parsed": {
    "ok": true,
    "directions": [
      {
        "direction_id": "run_20260819_153000.direction_000",
        "index": 0,
        "text": "探索放量下跌后的短期均值回归特征"
      },
      {
        "direction_id": "run_20260819_153000.direction_001",
        "index": 1,
        "text": "探索高换手恐慌交易后的价格修复特征"
      }
    ]
  },
  "parser": {
    "attempt_count": 1,
    "fallback_used": false,
    "warnings": []
  }
}
```

### 7.5 `00_task.json`

```json
{
  "schema_version": "1.0",
  "run_id": "run_20260819_153000",
  "task_id": "run_20260819_153000.round_01.task_000",
  "round_id": "run_20260819_153000.round_01",
  "round_idx": 1,
  "phase": "mutation",
  "task_index": 0,
  "status": "success",
  "direction_ref": "run_20260819_153000.direction_000",
  "parent_refs": [
    "run_20260819_153000.round_00.task_000"
  ],
  "strategy_suffix_ref": "03_mutation_output.json",
  "started_at": "...",
  "ended_at": "..."
}
```

### 7.6 `01_parent_refs.json`

mutation 示例：

```json
{
  "schema_version": "1.0",
  "task_id": "run_20260819_153000.round_01.task_000",
  "phase": "mutation",
  "parents": [
    {
      "parent_task_id": "run_20260819_153000.round_00.task_000",
      "parent_trajectory_id": "traj_original_r0_d0",
      "parent_factor_ids": [
        "run_20260819_153000.round_00.task_000.factor_000"
      ],
      "selection_reason": "best_rank_ic_in_previous_round",
      "primary_metric": {
        "name": "ic_mean",
        "value": 0.041
      }
    }
  ]
}
```

crossover 示例：

```json
{
  "schema_version": "1.0",
  "task_id": "run_20260819_153000.round_02.task_000",
  "phase": "crossover",
  "parents": [
    {
      "parent_task_id": "run_20260819_153000.round_00.task_000",
      "role": "parent_a"
    },
    {
      "parent_task_id": "run_20260819_153000.round_01.task_001",
      "role": "parent_b"
    }
  ],
  "crossover_size": 2,
  "combination_reason": "diverse_phase_and_high_metric"
}
```

### 7.7 `03_hypothesis.json`

```json
{
  "schema_version": "1.0",
  "node_id": "run_20260819_153000.round_00.task_000.hyp_000",
  "type": "hypothesis",
  "actor": "HypothesisAgent",
  "status": "success",
  "input_refs": [
    "01_direction.json"
  ],
  "prompt_ref": "02_alpha_loop.json#hypothesis_prompt",
  "raw": {
    "system_prompt": "...完整 system prompt...",
    "user_prompt": "...完整 user prompt...",
    "response_text": "...LLM 原始输出，不做删改..."
  },
  "parsed": {
    "ok": true,
    "data": {
      "hypothesis": "放量下跌可能反映短期恐慌性成交，随后存在价格修复。",
      "reason": "成交量异常放大时，价格短期下跌可能来自非理性抛压。",
      "concise_observation": "...",
      "concise_justification": "...",
      "concise_knowledge": "..."
    }
  },
  "parser": {
    "attempt_count": 1,
    "warnings": []
  }
}
```

### 7.8 `04_experiment.json`

```json
{
  "schema_version": "1.0",
  "node_id": "run_20260819_153000.round_00.task_000.exp_000",
  "type": "experiment",
  "actor": "FactorGenerationAgent",
  "status": "success",
  "hypothesis_id": "run_20260819_153000.round_00.task_000.hyp_000",
  "factor_ids": [
    "run_20260819_153000.round_00.task_000.factor_000",
    "run_20260819_153000.round_00.task_000.factor_001"
  ],
  "raw": {
    "system_prompt": "...完整 system prompt...",
    "user_prompt": "...完整 user prompt...",
    "response_text": "...LLM 原始输出，包含它写出的完整 factor JSON 或文本..."
  },
  "parsed": {
    "ok": true,
    "factor_count": 2,
    "factor_ids": [
      "run_20260819_153000.round_00.task_000.factor_000",
      "run_20260819_153000.round_00.task_000.factor_001"
    ]
  },
  "parser": {
    "attempt_count": 1,
    "warnings": []
  }
}
```

### 7.9 `05_factors/factor_000/00_factor.json`

```json
{
  "schema_version": "1.0",
  "factor_id": "run_20260819_153000.round_00.task_000.factor_000",
  "global_factor_id": null,
  "factor_version_id": null,
  "source": {
    "run_id": "run_20260819_153000",
    "round_idx": 0,
    "phase": "original",
    "task_id": "run_20260819_153000.round_00.task_000",
    "hypothesis_id": "run_20260819_153000.round_00.task_000.hyp_000"
  },
  "definition": {
    "name": "Volume_Panic_Reversal_10D",
    "description": "捕捉放量下跌后的短期反转。",
    "formulation": "Rank(-Delta(close, 5) * Rank(volume / Mean(volume, 20)))",
    "expression": "RANK(-DELTA($close, 5) * RANK($volume / TS_MEAN($volume, 20)))",
    "features": ["$close", "$volume"],
    "operators": ["RANK", "DELTA", "TS_MEAN"]
  },
  "raw": {
    "source_file": "../../04_experiment.json",
    "raw_factor_block": "...LLM 在 experiment 中对这个因子的原始描述和公式..."
  },
  "lifecycle": {
    "status": "candidate",
    "active": false,
    "reason": "newly_generated",
    "updated_by": "system",
    "updated_at": "2026-08-19T15:40:00+08:00"
  }
}
```

### 7.10 `01_formula_attempts/attempt_000.json`

```json
{
  "schema_version": "1.0",
  "attempt_id": "run_20260819_153000.round_00.task_000.factor_000.attempt_000",
  "factor_id": "run_20260819_153000.round_00.task_000.factor_000",
  "attempt_index": 0,
  "raw": {
    "prompt": "...完整公式生成/修正 prompt...",
    "response_text": "...LLM 原始输出...",
    "raw_expression": "Rank(-Delta(close, 5) * Rank(volume / Mean(volume, 20)))"
  },
  "parsed": {
    "ok": true,
    "expression": "RANK(-DELTA($close, 5) * RANK($volume / TS_MEAN($volume, 20)))",
    "ast": "...可选保存标准化 AST..."
  },
  "validation": {
    "json_parse_passed": true,
    "expression_parse_passed": true,
    "operator_passed": true,
    "data_field_passed": true,
    "complexity_passed": true,
    "redundancy_passed": true,
    "consistency_passed": true,
    "final_decision": "accepted"
  },
  "feedback_to_next_attempt": null
}
```

如果失败：

```json
{
  "validation": {
    "json_parse_passed": true,
    "expression_parse_passed": false,
    "operator_passed": false,
    "final_decision": "retry"
  },
  "feedback_to_next_attempt": "表达式使用了未注册算子 SMA，请改用 TS_MEAN。"
}
```

### 7.11 `03_factor_evaluation.json`

对应你们新的内部回测方案。

```json
{
  "schema_version": "1.0",
  "evaluation_id": "run_20260819_153000.round_00.task_000.factor_000.eval_000",
  "factor_id": "run_20260819_153000.round_00.task_000.factor_000",
  "evaluation_engine": "internal_backtester",
  "engine_version": "v0.1",
  "status": "success",
  "raw": {
    "engine_request": {
      "factor_values_ref": "02_factor_values_ref.json",
      "years": [2024, 2025, 2026],
      "group_count": 10
    },
    "engine_stdout_ref": "artifacts/logs/factor_000_backtest_stdout.log",
    "engine_raw_report_refs": [
      "artifacts/backtest_reports/factor_000_decile_raw.parquet",
      "artifacts/backtest_reports/factor_000_yearly_raw.json"
    ]
  },
  "years": [2024, 2025, 2026],
  "data_context": {
    "universe": "all_a_share",
    "frequency": "daily",
    "year_complete": {
      "2024": true,
      "2025": true,
      "2026": false
    }
  },
  "ic": {
    "method": "cross_sectional_ic",
    "mean_ic": 0.036,
    "threshold": 0.03,
    "pass": true
  },
  "icir": {
    "value": 0.52,
    "threshold": 0.5,
    "threshold_source": "config",
    "pass": true
  },
  "signal_direction": {
    "ic_sign": "positive",
    "selected_group": "top",
    "rule": "IC >= 0 uses top group; IC < 0 uses bottom group"
  },
  "decile_long_short_by_year": {
    "group_count": 10,
    "fee": 0,
    "threshold_return_diff": 0.2,
    "yearly": {
      "2024": {
        "top_return": 0.31,
        "bottom_return": 0.06,
        "long_short_return_diff": 0.25,
        "pass": true
      },
      "2025": {
        "top_return": 0.28,
        "bottom_return": 0.07,
        "long_short_return_diff": 0.21,
        "pass": true
      },
      "2026": {
        "top_return": 0.13,
        "bottom_return": -0.06,
        "long_short_return_diff": 0.19,
        "pass": false
      }
    }
  },
  "excess_sharpe_by_year": {
    "group_count": 10,
    "fee": "non_zero",
    "baseline": "market_equal_weight_return",
    "threshold_excess_sharpe": 1.0,
    "yearly": {
      "2024": {
        "selected_group": "top",
        "excess_sharpe": 1.23,
        "pass": true
      },
      "2025": {
        "selected_group": "top",
        "excess_sharpe": 1.08,
        "pass": true
      },
      "2026": {
        "selected_group": "top",
        "excess_sharpe": 0.91,
        "pass": false
      }
    }
  },
  "final_decision": "candidate",
  "fail_reasons": [
    "2026_decile_return_diff_below_threshold",
    "2026_excess_sharpe_below_threshold"
  ],
  "artifacts": {
    "factor_values": "factor_values_000.parquet",
    "decile_report": "decile_report_000.parquet",
    "yearly_report": "yearly_report_000.json"
  }
}
```

### 7.12 `06_batch_evaluation.json`

一轮内多个因子需要统一筛选。

```json
{
  "schema_version": "1.0",
  "task_id": "run_20260819_153000.round_00.task_000",
  "factor_ids": [
    "run_20260819_153000.round_00.task_000.factor_000",
    "run_20260819_153000.round_00.task_000.factor_001"
  ],
  "semantic_groups": [
    {
      "group_id": "grp_volume_reversal",
      "semantic_label": "放量反转类",
      "factor_ids": [
        "run_20260819_153000.round_00.task_000.factor_000",
        "run_20260819_153000.round_00.task_000.factor_001"
      ],
      "dedup_rule": "within_group_high_ic_corr_keep_best_return",
      "selected_factor_id": "run_20260819_153000.round_00.task_000.factor_000",
      "rejected_factor_ids": [
        {
          "factor_id": "run_20260819_153000.round_00.task_000.factor_001",
          "reason": "high_ic_correlation_and_lower_return"
        }
      ]
    }
  ],
  "status": "completed"
}
```

---

## 8. events.jsonl 设计

### 8.1 为什么需要 events.jsonl

`run_graph.json` 是展示用的索引，但运行中如果崩溃，graph 可能没来得及完整写。  
因此必须有 append-only 事件流作为运行账本。

但注意：

```text
events.jsonl 不是保存大段原始输出的地方。
```

它只记录：

```text
什么时候发生了什么；
哪个节点成功/失败；
原始记录文件在哪里；
生成了哪些 artifact。
```

真正的 LLM 原文、公式重试原文、程序输出，放在各自步骤文件里：

```text
03_hypothesis.json 保存 Hypothesis Agent 的原文；
04_experiment.json 保存 Factor Generation Agent 的原文；
attempt_000.json 保存一次公式尝试的原文；
03_factor_evaluation.json 保存评价结果和原始回测输出引用。
```

原则：

```text
运行时优先写 events.jsonl；
步骤文件写完后追加 node_completed；
run_graph.json 可以随时由 events.jsonl 重建。
```

### 8.2 事件类型

| 事件类型 | 说明 |
|---|---|
| `run_started` | run 开始 |
| `run_completed` | run 完成 |
| `node_created` | 创建节点文件 |
| `node_started` | 某节点开始 |
| `node_completed` | 某节点成功完成 |
| `node_failed` | 某节点失败 |
| `edge_created` | 新增节点关系 |
| `artifact_created` | 生成 H5 / Parquet / JSON 报告，并记录路径 |
| `factor_status_changed` | 因子状态变化 |
| `review_added` | 人工审核意见 |
| `sync_to_neo4j_completed` | Neo4j 同步完成 |

### 8.3 示例

```json
{"event_id":"evt_000001","type":"run_started","run_id":"run_20260819_153000","time":"2026-08-19T15:30:00+08:00"}
{"event_id":"evt_000002","type":"node_created","run_id":"run_20260819_153000","node_id":"run_20260819_153000.planning.output","node_type":"planning_output","path":"00_planning/01_output.json","time":"2026-08-19T15:30:10+08:00"}
{"event_id":"evt_000003","type":"edge_created","from":"run_20260819_153000.planning.output","to":"run_20260819_153000.round_00.task_000","edge_type":"CREATES_TASK","time":"2026-08-19T15:30:11+08:00"}
{"event_id":"evt_000004","type":"node_completed","node_id":"run_20260819_153000.round_00.task_000.hyp_000","status":"success","path":"round_00_original/task_000_original_direction_000/03_hypothesis.json","time":"2026-08-19T15:31:00+08:00"}
```

### 8.4 并行写入注意

未来 `parallel_enabled=true` 时：

1. 每个 task 只写自己的 task 目录。
2. `events.jsonl` 写入必须使用文件锁。
3. 全局因子库和 Neo4j 不建议在 task 内并行直接写，建议 run 结束或阶段结束后统一 sync。

---

## 9. run_graph.json 设计

### 9.1 职责

`run_graph.json` 不保存大内容，只保存：

```text
节点 ID
节点类型
文件路径
状态
边关系
分组信息
关键摘要字段
```

前端重建流程图时：

```text
读取 run_graph.json
  ↓
根据 nodes 画节点
  ↓
根据 edges 画线
  ↓
根据 groups 折叠 round / task
  ↓
点击节点时根据 path 读取详细 JSON
```

### 9.2 示例

```json
{
  "schema_version": "1.0",
  "run_id": "run_20260819_153000",
  "status": "completed",
  "nodes": [
    {
      "id": "run_20260819_153000.planning.output",
      "type": "planning_output",
      "label": "Planning Agent 输出方向",
      "path": "00_planning/01_output.json",
      "status": "success"
    },
    {
      "id": "run_20260819_153000.round_00.task_000",
      "type": "task",
      "phase": "original",
      "round_idx": 0,
      "label": "Original Task 000",
      "path": "round_00_original/task_000_original_direction_000/00_task.json",
      "status": "success"
    },
    {
      "id": "run_20260819_153000.round_00.task_000.factor_000",
      "type": "factor",
      "phase": "original",
      "round_idx": 0,
      "label": "Volume_Panic_Reversal_10D",
      "path": "round_00_original/task_000_original_direction_000/05_factors/factor_000/00_factor.json",
      "status": "candidate",
      "summary": {
        "mean_ic": 0.036,
        "excess_sharpe_2025": 1.08
      }
    }
  ],
  "edges": [
    {
      "from": "run_20260819_153000.planning.output",
      "to": "run_20260819_153000.round_00.task_000",
      "type": "CREATES_TASK"
    },
    {
      "from": "run_20260819_153000.round_00.task_000",
      "to": "run_20260819_153000.round_00.task_000.hyp_000",
      "type": "GENERATES"
    },
    {
      "from": "run_20260819_153000.round_00.task_000.hyp_000",
      "to": "run_20260819_153000.round_00.task_000.factor_000",
      "type": "GENERATES_FACTOR"
    }
  ],
  "groups": [
    {
      "id": "run_20260819_153000.round_00",
      "type": "round",
      "label": "Round 0 / Original",
      "children": [
        "run_20260819_153000.round_00.task_000"
      ]
    }
  ]
}
```

---

## 10. 内部回测与评价方案设计

### 10.1 替换 Qlib 的原则

后续计划去掉 Qlib 回测，改用内部工具。  
因此本方案不把结构化记录绑定到 Qlib，而是定义统一的 `BacktestAdapter`。

```python
class BacktestAdapter:
    def compute_factor_values(self, factor, data_context):
        ...

    def evaluate_single_factor(self, factor_values, returns, config):
        ...

    def evaluate_factor_batch(self, factors, config):
        ...

    def export_artifacts(self, output_dir):
        ...
```

当前可以实现：

```text
InternalBacktestAdapter
```

未来如果需要对比旧结果，也可以临时实现：

```text
QlibBacktestAdapter
```

### 10.2 单因子评价流程

你们当前计划：

```text
1. 先用 IC 评估，至少 > 0.03
2. ICIR 由 AI 建议基准，但最终写入 config
3. 分年用内部回测工具跑 10 分组，手续费为 0
   计算每一年头尾组收益差，至少相差 20 个点
4. 分年用内部回测工具跑 10 分组，手续费不为 0
   IC 为正时看头组，IC 为负时看尾组
   全市场等权收益率作为基线
   超额夏普至少 1.0
5. 当前先跑 2024、2025、2026 年
6. 一轮内保留多个因子时，后续按因子意义分组，组内根据 IC 去重，保留收益最高的一个因子
```

### 10.3 配置建议

```yaml
evaluation:
  engine: internal_backtester
  years: [2024, 2025, 2026]
  group_count: 10

  ic:
    method: cross_sectional_ic
    threshold: 0.03

  icir:
    threshold: 0.5     # 可先由 AI 建议，但必须落到配置里
    threshold_source: config

  decile_long_short:
    fee: 0
    threshold_return_diff: 0.2

  excess_sharpe:
    fee_mode: non_zero
    baseline: market_equal_weight_return
    threshold: 1.0
    positive_ic_group: top
    negative_ic_group: bottom

  factor_selection:
    semantic_grouping_enabled: true
    within_group_corr_method: ic_series_corr
    within_group_corr_threshold: 0.85
    keep_rule: highest_long_short_return
```

### 10.4 评价节点输出

单因子评价结果已经在第 7.11 节给出。  
关键是必须同时保存：

```text
factor_level_metrics      # 单因子指标
batch_selection_metrics   # 一轮内多个因子的筛选指标
raw_artifacts             # 详细回测报表和因子值文件
```

不要把“单因子好”和“一批因子组合效果好”混为一个指标。

---

## 11. 全局因子库设计

### 11.1 目标

全局因子库解决：

```text
每次 run 不是孤立因子库
成功经验能累积
失败经验能复用
相似因子能查重
因子能启用、停用、归档
后续新主题能召回历史经验
```

### 11.2 建议目录

```text
global_factor_library/
  00_factor_index.jsonl              # 全局因子基本信息
  01_factor_versions.jsonl           # 因子版本
  02_factor_metrics.duckdb           # 指标表
  03_factor_status_events.jsonl      # 状态变化历史
  04_factor_correlations.parquet     # 因子值相关性矩阵
  05_factor_similarity.jsonl         # 表达式/语义相似关系
  06_active_factors.json             # 当前启用因子列表
  07_rejected_factors.json           # 拒绝因子索引
```

### 11.3 因子生命周期

状态建议：

```text
candidate    新生成，待评价 / 待审核
accepted     评价通过，可进入库
active       当前启用
inactive     暂不启用，但保留
rejected     明确拒绝
deprecated   曾经有效，现在废弃
archived     历史归档，默认不参与召回
```

建议先实现简版：

```text
candidate / active / inactive / rejected / archived
```

### 11.4 因子状态事件

状态不要覆盖，要 append-only。

```json
{
  "event_id": "status_evt_000001",
  "global_factor_id": "gf_000001",
  "factor_version_id": "gf_000001.v001",
  "from_status": "candidate",
  "to_status": "active",
  "from_active": false,
  "to_active": true,
  "reason": "ic_passed_and_low_corr_with_active_factors",
  "operator": "system",
  "reviewer": null,
  "review_comment": null,
  "time": "2026-08-19T16:00:00+08:00"
}
```

### 11.5 入库规则初版

可以先用规则：

```text
if mean_ic < 0.03:
    rejected
elif yearly_long_short_return_diff 任一年 < 0.2:
    candidate 或 inactive，需要人工复核
elif yearly_excess_sharpe 任一年 < 1.0:
    candidate 或 inactive，需要人工复核
elif max_corr_with_active > 0.85:
    inactive
else:
    active
```

注意：2026 可能不是完整年度，需要记录 `year_complete=false`，规则上可以降低权重或单独标注。

---

## 12. Neo4j 数据库设计

Neo4j 用于保存轻量关系和索引，不保存大文件和完整 prompt。

### 12.1 节点标签

```cypher
// 一次完整运行
(:Run {
  id: "run_20260819_153000",        // 主键，对应 run_id
  status: "completed",              // running / completed / failed
  created_at: datetime(...),
  path: "runs/run_20260819_153000", // 文件系统路径
  research_topic: "放量下跌后的短期反转"
})

// 轮次
(:Round {
  id: "run_20260819_153000.round_00",
  run_id: "run_20260819_153000",
  round_idx: 0,
  phase: "original",                // original / mutation / crossover
  status: "completed",
  path: "round_00_original/00_round_summary.json"
})

// 任务
(:Task {
  id: "run_20260819_153000.round_00.task_000",
  run_id: "run_20260819_153000",
  round_idx: 0,
  phase: "original",
  task_index: 0,
  status: "success",
  path: "round_00_original/task_000_original_direction_000/00_task.json"
})

// 研究方向
(:Direction {
  id: "run_20260819_153000.direction_000",
  run_id: "run_20260819_153000",
  text: "探索放量下跌后的短期均值回归特征",
  embedding: [...],                 // 可选：用于向量检索
  path: "00_planning/01_output.json"
})

// 研究假设
(:Hypothesis {
  id: "run_20260819_153000.round_00.task_000.hyp_000",
  run_id: "run_20260819_153000",
  text: "放量下跌可能反映短期恐慌性成交，随后存在价格修复。",
  summary: "放量下跌后的短期反转",
  embedding: [...],
  path: "round_00_original/task_000_original_direction_000/03_hypothesis.json"
})

// 因子
(:Factor {
  id: "run_20260819_153000.round_00.task_000.factor_000", // source factor id
  global_factor_id: "gf_000001",
  factor_version_id: "gf_000001.v001",
  name: "Volume_Panic_Reversal_10D",
  expression: "RANK(...)",
  status: "candidate",              // candidate / active / inactive / rejected / archived
  active: false,
  quality_score: 0.71,
  mean_ic: 0.036,
  icir: 0.52,
  max_corr_with_active: 0.43,
  embedding: [...],                 // 因子描述/公式文本 embedding
  path: "round_00_original/task_000_original_direction_000/05_factors/factor_000/00_factor.json"
})

// 公式尝试
(:FormulaAttempt {
  id: "run_20260819_153000.round_00.task_000.factor_000.attempt_000",
  factor_id: "run_20260819_153000.round_00.task_000.factor_000",
  attempt_index: 0,
  expression: "RANK(...)",
  final_decision: "accepted",
  path: "round_00_original/task_000_original_direction_000/05_factors/factor_000/01_formula_attempts/attempt_000.json"
})

// 回测 / 评价结果
(:Evaluation {
  id: "run_20260819_153000.round_00.task_000.factor_000.eval_000",
  factor_id: "run_20260819_153000.round_00.task_000.factor_000",
  engine: "internal_backtester",
  mean_ic: 0.036,
  icir: 0.52,
  pass: false,
  final_decision: "candidate",
  path: "round_00_original/task_000_original_direction_000/05_factors/factor_000/03_factor_evaluation.json"
})

// Feedback
(:Feedback {
  id: "run_20260819_153000.round_00.task_000.feedback_000",
  run_id: "run_20260819_153000",
  summary: "该因子在 2024/2025 表现较好，但 2026 超额夏普不足。",
  embedding: [...],
  path: "round_00_original/task_000_original_direction_000/07_feedback.json"
})

// 特征
(:Feature {
  name: "$volume"                    // 主键
})

// 算子
(:Operator {
  name: "RANK"                       // 主键
})
```

### 12.2 关系类型

```cypher
// Run 包含 Round
(:Run)-[:HAS_ROUND]->(:Round)

// Round 包含 Task
(:Round)-[:HAS_TASK]->(:Task)

// Task 使用 Direction
(:Task)-[:USES_DIRECTION]->(:Direction)

// Task 生成 Hypothesis
(:Task)-[:GENERATES_HYPOTHESIS]->(:Hypothesis)

// Hypothesis 生成 Factor
(:Hypothesis)-[:GENERATES_FACTOR]->(:Factor)

// Factor 有公式尝试
(:Factor)-[:HAS_ATTEMPT]->(:FormulaAttempt)

// Factor 有单因子评价
(:Factor)-[:HAS_EVALUATION]->(:Evaluation)

// Task 有 Feedback
(:Task)-[:HAS_FEEDBACK]->(:Feedback)

// mutation 来源
(:Task)-[:MUTATED_FROM {
  reason: "best_rank_ic_in_previous_round"
}]->(:Task)

// crossover 来源，一个 crossover task 可以有多条 CROSSED_FROM 边
(:Task)-[:CROSSED_FROM {
  role: "parent_a"
}]->(:Task)

// 因子使用字段
(:Factor)-[:USES_FEATURE]->(:Feature)

// 因子使用算子
(:Factor)-[:USES_OPERATOR]->(:Operator)

// 因子数值相关性
(:Factor)-[:CORRELATED_WITH {
  pearson: 0.91,
  spearman: 0.88,
  date_range: "2024-01-01:2026-08-19",
  universe: "all_a_share",
  frequency: "daily",
  method: "factor_value_corr"
}]->(:Factor)

// 语义相似
(:Hypothesis)-[:SIMILAR_TO {
  score: 0.87,
  method: "embedding_cosine",
  model: "text-embedding-xxx"
}]->(:Hypothesis)

// 因子停用原因
(:Factor)-[:DEACTIVATED_BECAUSE {
  reason: "high_corr_with_active_factor",
  corr: 0.93,
  time: datetime(...)
}]->(:Factor)

// 因子版本关系
(:Factor)-[:SUPERSEDED_BY {
  reason: "formula_simplified"
}]->(:Factor)
```

### 12.3 约束与索引

```cypher
// 主键约束：保证 id 唯一
CREATE CONSTRAINT run_id IF NOT EXISTS
FOR (n:Run) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT round_id IF NOT EXISTS
FOR (n:Round) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT task_id IF NOT EXISTS
FOR (n:Task) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT factor_id IF NOT EXISTS
FOR (n:Factor) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT feature_name IF NOT EXISTS
FOR (n:Feature) REQUIRE n.name IS UNIQUE;

CREATE CONSTRAINT operator_name IF NOT EXISTS
FOR (n:Operator) REQUIRE n.name IS UNIQUE;

// 常用过滤索引
CREATE INDEX factor_global_id IF NOT EXISTS
FOR (n:Factor) ON (n.global_factor_id);

CREATE INDEX factor_status IF NOT EXISTS
FOR (n:Factor) ON (n.status);

CREATE INDEX factor_active IF NOT EXISTS
FOR (n:Factor) ON (n.active);

CREATE INDEX factor_mean_ic IF NOT EXISTS
FOR (n:Factor) ON (n.mean_ic);

CREATE INDEX task_phase_round IF NOT EXISTS
FOR (n:Task) ON (n.phase, n.round_idx);
```

### 12.4 向量索引

如果使用 Neo4j 自带 vector index，可以给 Direction、Hypothesis、Feedback、Factor 建向量索引。

```cypher
// 注释：
// direction_embedding_index 用于根据新研究主题召回相似历史方向。
CREATE VECTOR INDEX direction_embedding_index IF NOT EXISTS
FOR (n:Direction) ON (n.embedding)
OPTIONS {
  indexConfig: {
    `vector.dimensions`: 1536,
    `vector.similarity_function`: "cosine"
  }
};

// hypothesis_embedding_index 用于召回相似历史研究假设。
CREATE VECTOR INDEX hypothesis_embedding_index IF NOT EXISTS
FOR (n:Hypothesis) ON (n.embedding)
OPTIONS {
  indexConfig: {
    `vector.dimensions`: 1536,
    `vector.similarity_function`: "cosine"
  }
};

// feedback_embedding_index 用于召回相似失败经验和复盘建议。
CREATE VECTOR INDEX feedback_embedding_index IF NOT EXISTS
FOR (n:Feedback) ON (n.embedding)
OPTIONS {
  indexConfig: {
    `vector.dimensions`: 1536,
    `vector.similarity_function`: "cosine"
  }
};

// factor_embedding_index 用于召回语义相似因子描述或公式。
CREATE VECTOR INDEX factor_embedding_index IF NOT EXISTS
FOR (n:Factor) ON (n.embedding)
OPTIONS {
  indexConfig: {
    `vector.dimensions`: 1536,
    `vector.similarity_function`: "cosine"
  }
};
```

维度 `1536` 只是示例，实际应和 embedding 模型一致。

---

## 13. 向量查找与历史经验召回方案

### 13.1 目标

用户输入新研究主题：

```text
挖掘放量下跌后的短期反转因子
```

系统自动召回：

```text
相似历史方向
相似历史假设
表现好的相关因子
失败过的类似公式
高相关需要避免重复的因子
mutation / crossover 可借鉴 parent
```

然后组装成 LLM 上下文。

### 13.2 三类相似性

1. **语义相似**
   - Direction text
   - Hypothesis text
   - Feedback summary
   - Factor description / expression text

2. **结构相似**
   - 使用相同特征：volume、close、return
   - 使用相同算子：RANK、DELTA、TS_MEAN
   - 公式 AST 相似

3. **数值相似**
   - 因子值 Pearson / Spearman 相关性
   - IC 序列相关性
   - 分组收益表现相似

建议：

```text
语义相似：embedding + Neo4j vector index
结构相似：Neo4j Feature / Operator 关系
数值相似：Python / DuckDB / pandas 先计算，再写入 Neo4j 的 CORRELATED_WITH 边
```

### 13.3 检索流程

```text
输入新研究主题
  ↓
生成 query embedding
  ↓
Neo4j vector search 找相似 Direction / Hypothesis / Feedback / Factor
  ↓
沿图扩展：
    找这些节点对应的 Factor
    找 Factor 的 Evaluation
    找 parent / children
    找相关性高的已有 active factors
    找 rejected / failed attempts
  ↓
筛选：
    优先 active + 高质量
    辅助 inactive + 高相关，提醒避免重复
    纳入 rejected / failed 作为负面经验
  ↓
组装 LLM context
```

### 13.4 Cypher 示例：相似 hypothesis 召回

```cypher
// 输入 queryEmbedding 后，召回相似历史假设
CALL db.index.vector.queryNodes(
  "hypothesis_embedding_index",
  20,
  $queryEmbedding
) YIELD node, score
WHERE score > 0.75
MATCH (node)-[:GENERATES_FACTOR]->(f:Factor)
OPTIONAL MATCH (f)-[:HAS_EVALUATION]->(e:Evaluation)
RETURN
  node.id AS hypothesis_id,
  node.summary AS hypothesis_summary,
  score AS semantic_score,
  f.id AS factor_id,
  f.name AS factor_name,
  f.expression AS expression,
  e.mean_ic AS mean_ic,
  e.icir AS icir,
  e.final_decision AS decision
ORDER BY semantic_score DESC, mean_ic DESC
LIMIT 10;
```

### 13.5 Cypher 示例：找高相关 active 因子，避免重复

```cypher
// 新因子入库前，查它和 active 因子的相关性
MATCH (new:Factor {id: $newFactorId})-[r:CORRELATED_WITH]-(old:Factor)
WHERE old.active = true
  AND abs(r.pearson) >= 0.85
RETURN
  old.id AS active_factor_id,
  old.name AS active_factor_name,
  old.expression AS active_expression,
  r.pearson AS pearson,
  r.spearman AS spearman,
  r.date_range AS date_range
ORDER BY abs(r.pearson) DESC;
```

### 13.6 LLM context 组装格式

```json
{
  "positive_context": [
    {
      "type": "historical_factor",
      "factor_name": "Volume_Panic_Reversal_10D",
      "hypothesis": "放量下跌后存在短期修复",
      "expression": "RANK(...)",
      "mean_ic": 0.041,
      "excess_sharpe": 1.2,
      "why_relevant": "语义相似，且 active"
    }
  ],
  "avoid_context": [
    {
      "type": "high_correlation_factor",
      "factor_name": "Old_Volume_Reversal",
      "corr": 0.92,
      "message": "新公式应避免只是该因子的形式变体"
    }
  ],
  "warning_context": [
    {
      "type": "failed_attempt",
      "reason": "公式过度复杂，2026 年超额夏普低于 1.0",
      "feedback": "应减少嵌套算子，优先使用简单 rank / delta 结构"
    }
  ]
}
```

---

## 14. 相关性计算与存储设计

### 14.1 相关性不是 Neo4j 直接计算

建议：

```text
Python / DuckDB / pandas 负责计算；
Neo4j 负责存储和查询计算结果。
```

### 14.2 相关性边必须记录口径

```json
{
  "factor_a": "gf_000001.v001",
  "factor_b": "gf_000002.v001",
  "pearson": 0.91,
  "spearman": 0.88,
  "ic_series_corr": 0.76,
  "date_range": ["2024-01-01", "2026-08-19"],
  "universe": "all_a_share",
  "frequency": "daily",
  "fillna_method": "drop_pairwise",
  "neutralization": "none",
  "computed_at": "2026-08-19T16:00:00+08:00"
}
```

原因：

```text
corr=0.9 本身没有意义；
必须知道在哪个时间段、哪个股票池、什么缺失值处理方法下算出来。
```

### 14.3 入库前相关性检查

```text
新因子生成
  ↓
计算与 active 因子库的相关性
  ↓
如果 max_corr_with_active > 0.85
    标记 inactive 或 candidate_for_review
    写 DEACTIVATED_BECAUSE / HIGHLY_CORRELATED_WITH 关系
否则进入 active 候选
```

---

## 15. 人工审核与状态变更

必须支持人工决策，因为因子启用/停用不一定完全由规则决定。

### 15.1 review 文件

```json
{
  "review_id": "review_000001",
  "global_factor_id": "gf_000001",
  "factor_version_id": "gf_000001.v001",
  "reviewer": "teacher_or_researcher",
  "review_status": "approved",
  "review_comment": "逻辑清晰，相关性不高，先进入 active 观察。",
  "reviewed_at": "2026-08-19T16:20:00+08:00"
}
```

### 15.2 Neo4j 审核关系

```cypher
// 人工审核节点，可用于审计
(:Review {
  id: "review_000001",
  reviewer: "teacher_or_researcher",
  decision: "approved",
  comment: "逻辑清晰，相关性不高，先进入 active 观察。",
  reviewed_at: datetime(...)
})

(:Review)-[:REVIEWS]->(:Factor)
```

---

## 16. Schema 版本与兼容性

每个 JSON 必须包含：

```json
{
  "schema_version": "1.0"
}
```

后续如果字段变化：

```text
1.0 -> 1.1：新增字段，兼容旧读取
1.x -> 2.0：结构变化，需要 migration
```

建议新增：

```text
quantaalpha/tracing/schema_registry.py
```

功能：

```text
validate_json(path)
migrate_json(path, from_version, to_version)
```

---

## 17. 安全与敏感信息

禁止保存：

```text
API Key
MongoDB URI 中的密码
私有账号密码
完整认证 token
带密码的数据库连接串
```

可以保存：

```text
api_provider
model_name
api_base_alias
data_source_alias
mongo_database_name
collection_name
```

如果必须保存连接信息，应脱敏：

```text
mongodb+srv://user:***@host/database
```

---

## 18. 重建功能定义

“重建”要分四种，不要混用：

| 类型 | 含义 | 第一版是否做 |
|---|---|---|
| UI 重建 | 根据 run_graph.json 展示流程图 | 是 |
| 结果重建 | 读取 JSON / Parquet / H5 展示结果 | 是 |
| 计算重建 | 重新计算因子值和回测 | 后续 |
| LLM 重建 | 重新调用 Agent 生成内容 | 后续 |

第一版建议只做：

```text
UI 重建 + 结果重建
```

---

## 19. 落地计划

### 阶段 1：Run Trace MVP

目标：

```text
每次 run 有结构化目录、分步骤高保真 JSON、events.jsonl、run_graph.json。
```

任务：

1. 新增 `quantaalpha/tracing/`。
2. 实现 `RunRecorder`。
3. 保存：
   - `00_run_summary.json`
   - `01_user_input.json`
   - `02_config_snapshot.yaml`
   - `05_environment.json`
   - `00_planning/00_prompt.json`
   - `00_planning/01_output.json`
   - `round_xx/00_round_summary.json`
   - `task_xxx/00_task.json`
   - `task_xxx/03_hypothesis.json`
   - `task_xxx/04_experiment.json`
   - `factor_xxx/00_factor.json`
   - `factor_xxx/01_formula_attempts/attempt_xxx.json`
   - `factor_xxx/03_factor_evaluation.json`
   - `task_xxx/07_feedback.json`
4. 实现 events append。
5. 实现 run_graph 构建。

### 阶段 2：内部回测适配

目标：

```text
替换 Qlib 评价输出，不影响上层流程。
```

任务：

1. 定义 `BacktestAdapter`。
2. 实现 `InternalBacktestAdapter`。
3. 支持 IC / ICIR。
4. 支持分年 10 分组收益差。
5. 支持分年超额夏普。
6. 输出 `factor_xxx/03_factor_evaluation.json` 和 `task_xxx/06_batch_evaluation.json`。

### 阶段 3：Formula Attempts 和失败经验

目标：

```text
把公式重试、解析失败、校验失败显式保存。
```

任务：

1. 修改 factor generation 的 retry loop。
2. 每次 LLM 返回都保存 attempt。
3. 保存 validation 明细。
4. 保存失败原因。
5. 将失败节点写入 run_graph。

### 阶段 4：Global Factor Library

目标：

```text
所有 run 的因子进入全局库，并支持状态管理。
```

任务：

1. 生成 `global_factor_id`。
2. 写 factor index。
3. 写 metrics DuckDB。
4. 写 status events。
5. 计算 active 因子相关性。
6. 实现 active / inactive / rejected。

### 阶段 5：Neo4j 同步

目标：

```text
把 run trace 和全局因子库同步为谱系图。
```

任务：

1. 创建 Neo4j constraints 和 indexes。
2. 实现 `neo4j_sync.py`。
3. 同步 Run / Round / Task / Direction / Hypothesis / Factor / Evaluation / Feedback。
4. 同步 parent、mutation、crossover、feature、operator、correlation 边。

### 阶段 6：向量经验召回

目标：

```text
输入新研究主题，自动召回历史相关经验。
```

任务：

1. 确定 embedding 模型。
2. 为 Direction / Hypothesis / Feedback / Factor 生成 embedding。
3. 建 Neo4j vector index。
4. 实现 hybrid retrieval。
5. 组装 LLM context。

---

## 20. 关键风险与提前规避

| 风险 | 规避方式 |
|---|---|
| 文件和 Neo4j 串不起来 | 第一版就统一 ID |
| graph 中途崩溃不完整 | events.jsonl append-only，可重建索引 |
| 分步骤文件只保存 parsed 导致真实性下降 | 每个步骤 JSON 都保存 `raw` 原文和 `parsed` 结果 |
| 结构化解析丢失 LLM 原话 | 每次 LLM 调用同时保存 `raw.response_text` 和 `parsed.data` |
| 因子名重复 | 使用 global_factor_id / factor_version_id |
| 数据变化导致指标不可比 | 保存 data_version、date_range、universe |
| 回测方式替换导致旧结构废弃 | 用 BacktestAdapter 和统一 evaluation schema |
| 并行写入冲突 | task 目录独立写，events 加锁，全局同步后置 |
| 相关性无口径 | 相关性边必须保存 date_range、universe、method |
| 启用状态被覆盖 | 状态变化使用 status_events append-only |
| Neo4j 太早引入增加复杂度 | 第一阶段先文件化，后同步 Neo4j |
| 敏感信息泄露 | environment 脱敏，不保存 key/password |

---

## 21. 最终推荐结论

最终方案可以概括为：

```text
1. 用 Run Trace 把每次挖掘变成可回放、可审计的结构化轨迹。
2. 保持 run / round / task / step / factor / attempt 的分步骤文件结构。
3. 每个步骤 JSON 内部同时保存 raw 原始输出和 parsed 结构化结果。
4. 用 events.jsonl 做运行账本，run_graph.json 做单次流程重建索引。
5. 用内部 BacktestAdapter 替换 Qlib，并统一输出 factor_evaluation.json 和 batch_evaluation.json。
6. 用 Global Factor Library 管理因子版本、状态、启用/停用、指标和相关性。
7. 用 Neo4j 保存因子谱系、mutation/crossover 来源、相似因子网络。
8. 用向量索引实现新研究主题到历史经验的自动召回。
```

最重要的工程决策：

```text
不要让文件系统、Neo4j、前端各自发明 ID。
一切都以 run_id / task_id / factor_id / global_factor_id / factor_version_id 串联。
```

这样后续才能稳定支持：

```text
流程重建
失败复盘
因子查重
全局因子库维护
因子启用/停用管理
相似经验召回
mutation/crossover 谱系追踪
新回测框架替换
```
