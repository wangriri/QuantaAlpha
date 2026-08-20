# 中文量化 Prompt 轻量优化成果说明

## 背景

本次优化目标是把中文量化研究提示词思想接入 QuantaAlpha 的主流程，但不引入当前代码尚未真实提供的上下文。

因此第一版只做“轻量优化”：

- 不新增 `DATA_CONTEXT`、`FACTOR_LIBRARY`、`ENVIRONMENT_CONTEXT` 等上下文占位符。
- 不改数据读取、MongoDB、Qlib、回测逻辑。
- 不改 mutation / crossover 的演化提示词。
- 只优化当前 original 主链路中已经实际使用的 prompt：研究方向生成、假设生成、假设转因子公式。

## 修改范围

### 1. 研究方向生成 Prompt

文件：

```text
quantaalpha/pipeline/prompts/planning_prompts.yaml
```

主要修改：

- 将研究方向生成规则改为中文描述。
- 明确 planning 阶段只负责生成研究方向，不生成公式、代码和回测方案。
- 增加约束：方向必须具体、可检验、彼此差异明显。
- 增加约束：不要只通过修改窗口、阈值、参数来制造多个方向。
- 增加约束：不要假设当前没有提供的数据、外部 API 或额外数据源。
- 增加约束：不得把未经验证的方向写成确定有效结论。
- 输出格式从“Markdown 代码块包裹 JSON”改为“纯 JSON”。
- JSON key 仍保持 `"directions"`，避免破坏解析逻辑。

### 2. 方向转假设 Prompt

文件：

```text
quantaalpha/factors/prompts/prompts.yaml
```

修改位置：

```text
potential_direction_transformation
hypothesis_output_format
factor_hypothesis_specification
hypothesis_gen
```

主要修改：

- 将“用户给出的方向如何转成假设”改成中文研究语义。
- 强调假设必须可检验，不能停留在“研究情绪”“研究资金行为”等抽象表达。
- 强调假设只能表达待验证关系，不能预设因子有效。
- 强调时间因果关系：未来收益只能作为检验目标，不能作为因子构造信息。
- 保留 JSON key：
  - `"hypothesis"`
  - `"concise_knowledge"`
  - `"concise_observation"`
  - `"concise_justification"`
  - `"concise_specification"`
- JSON value 允许中文，方便研究人员阅读。

### 3. 假设转因子公式 Prompt

文件：

```text
quantaalpha/factors/prompts/prompts.yaml
```

修改位置：

```text
hypothesis2experiment
factor_experiment_output_format
```

主要修改：

- 将公式生成规则改成中文说明，但保留英文变量名、函数名和 JSON key。
- 明确每次生成 2-3 个独立因子。
- 明确因子之间应有不同构造思路，不能只改窗口或阈值。
- 强化简单性约束：
  - 表达式硬上限 250 字符。
  - 目标长度 50-150 字符。
  - 避免深层嵌套、复杂条件分支、过多乘法链。
- 明确只能使用当前 prompt 已经列出的日频字段：
  - `$open`
  - `$close`
  - `$high`
  - `$low`
  - `$volume`
  - `$return`
- 明确表达式必须使用英文变量和函数，例如 `RANK()`、`TS_MEAN()`、`TS_CORR()`。
- 修复原 prompt 中不合法 JSON 示例问题：
  - 补齐缺失逗号。
  - 移除末尾多余逗号。
  - 移除 JSON 示例里的注释。
  - 示例描述改为中文，但 key 和 expression 保持英文。

## 语言策略

本次采用混合语言策略：

```text
中文：研究方向、假设、市场逻辑、约束说明、变量解释
英文：JSON key、字段名、函数名、表达式语法
```

原因：

- 用户通常用中文提问，研究表达用中文更自然。
- 系统解析依赖英文 JSON key，不能中文化。
- 因子表达式解析器依赖英文变量和函数，不能中文化。

示例：

```json
{
  "hypothesis": "研究异常放量后是否存在短期反转关系。",
  "concise_knowledge": "如果成交量相对历史水平异常放大，则可以检验其是否反映短期过度交易或信息冲击。"
}
```

而不是：

```json
{
  "假设": "研究异常放量后是否存在短期反转关系。"
}
```

## 未做内容

本次没有加入以下内容：

- 没有加入 `DATA_CONTEXT`。
- 没有加入 `FACTOR_LIBRARY`。
- 没有加入 `ENVIRONMENT_CONTEXT`。
- 没有接入 active / disabled 因子状态。
- 没有接入 Neo4j 或向量检索。
- 没有改 mutation / crossover prompt。
- 没有改 MongoDB、Qlib 数据、回测和因子库保存逻辑。

这些内容应等后续代码真实提供上下文后再加入 prompt。

## 测试覆盖

新增测试文件：

```text
tests/test_prompt_templates.py
```

测试内容：

- planning prompt 可以渲染。
- planning prompt 不包含未接入的上下文占位符。
- planning 输出格式不再要求 Markdown code block。
- planning 解析器可以解析纯 JSON。
- hypothesis prompt 可以用当前真实变量渲染。
- factor prompt 可以用当前真实变量渲染。
- JSON key 保持英文：
  - `"directions"`
  - `"hypothesis"`
  - `"description"`
  - `"variables"`
  - `"formulation"`
  - `"expression"`
- 表达式语法仍保留 `$close`、`TS_MEAN` 等英文机器接口。

## 后续建议

下一阶段可以在当前版本稳定后继续做：

1. 增加 `prompt_version` 记录到 trace 文件。
2. 把当前轻量 prompt 抽象成可配置的 `zh_quant_v1_light` prompt pack。
3. 接入真实 `data_context` 后，再把可用数据、频率、时间范围写进 prompt。
4. 接入全局因子库后，再加入已有因子去重、active / disabled、相似因子经验检索。
5. 单独优化 mutation / crossover，让它们继承“不要只改参数、保持低相关、避免重复”的规则。

## 本次成果一句话

本次完成了 QuantaAlpha original 主链路的中文量化研究 prompt 轻量优化：让 LLM 更像中文量化研究员一样提出方向、生成假设和写因子公式，同时保留英文 JSON key 和表达式语法，避免破坏现有系统解析与执行。
