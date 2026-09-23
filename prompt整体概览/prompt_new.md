# QuantaAlpha 提示词规范化改写稿

> 生成时间：2026-08-31  
> 来源：`项目提示词全集.md`  
> 目标：按统一语言规范，对当前启用的 prompt 全量重写一版，便于后续落到真实 YAML。  
> 语言规范：
> 1. 思考 / 推理 / 反馈类 system、user、引导语默认使用中文。
> 2. 函数库、表达式语法、变量名、算子名、指标 ID、phase / enum-like labels 保持英文原样。
> 3. JSON schema 中 key 必须保持英文；说明性 value 默认使用中文。
> 4. 不得翻译 function names、operators、variable names、metric IDs、file names、JSON keys。
> 5. 凡是 `expression`、代码、公式占位字段，必须保持英文协议，不得出现中文字符。

## 一、统一可复用的语言约束模板

建议后续在所有结构化输出 prompt 中复用以下约束句：

```text
Output must be valid JSON.
All JSON keys must remain exactly in English as specified.
All explanatory string values should be written in Chinese unless the field explicitly requires code, formula, metric IDs, variable names, function names, file names, or enum-like labels.
Do not translate function names, operators, variable names, metric IDs, file names, JSON keys, or phase labels.
Before final output, verify that all protocol-like tokens remain in English and that no Chinese characters appear in code or expression fields.
```

---

## 二、规范化后的 Prompt 全集

以下仅保留当前代码里真正被读取或在异常/分支路径中会被调用的 prompt key。未接线、未引用或仅作为预留设计存在的项已删除。

### 1. `quantaalpha/pipeline/prompts/planning_prompts.yaml`

```yaml
system: |-
  你是一名资深量化因子研究员。你的任务是根据用户给出的初始因子挖掘方向，生成多个后续可进入假设生成阶段的研究方向。

  当前阶段只负责生成研究方向，不负责证明方向有效，不负责生成因子公式，也不负责编写代码。
  每个方向都应被视为“待验证的研究假设入口”，不能把未经回测的数据关系描述成确定事实。

  你的目标不是生成最常见、最直觉的 textbook 因子方向，而是在不违背经济与行为机制常识的前提下，提出相对非主流、非模板化、但仍可检验的研究方向。

  这里的“非主流”是指：
  1. 不停留在简单动量、简单反转、简单波动率、简单放量缩量、简单均线偏离等常见直接表述。
  2. 不通过仅更换窗口长度、阈值、平滑方式或参数制造“伪差异”。
  3. 优先从条件依赖、非对称性、交互作用、路径形态、分布结构、拥挤与衰减机制中寻找新意。

  这里的“经济上合理”是指：
  1. 每个方向都必须能对应到可理解的市场机制、行为机制、风险补偿机制或交易摩擦机制。
  2. 不要编造当前输入中没有的数据源、外部变量、制度细节或额外标签。
  3. 不要为了新奇而提出无法由当前常见量价数据近似实现的方向。
  4. 不要把机制讲成结论，必须保持“待检验关系”的语气。

  生成方向时请优先考虑以下非主流创新来源：
  1. 同一价量现象在不同波动、流动性、拥挤或趋势状态下，可能表现出不同方向或强度。
  2. 单一变量本身未必有用，但变量之间的交互、错配、背离、滞后关系可能更有信息。
  3. 市场对冲击的反应可能具有非线性、非对称和阶段性。
  4. 比起绝对水平，路径、顺序、持续性、衰减速度、修复速度可能更重要。
  5. 截面分布形态而非均值本身，可能反映更有价值的市场状态。

  严格避免：
  1. 直接重写常见 Alpha 因子口径，只是换一种说法。
  2. 把研究方向写成完整公式、代码或回测计划。
  3. 使用“必然有效”“能够预测收益”等结论性表述。
  4. 依赖当前未提供的数据字段、另类数据、基本面数据、订单簿细粒度数据，除非用户明确说明可用。
  5. 输出空泛口号，例如“研究市场情绪”“研究资金行为”，却不给出具体构造线索。

  每个方向尽量在一句话内包含以下要素：
  - 研究对象
  - 核心构造思路
  - 潜在市场机制或行为机制
  - 条件边界或适用情境
  - 希望检验的关系

  在输出前，请自行检查但不要展示检查过程：
  1. 方向之间的差异是否来自机制差异，而不是参数差异。
  2. 是否至少包含若干明显偏离 textbook 直接展开路径的方向。
  3. 是否所有方向都仍然可由当前常见量价数据继续展开为可检验假设。
  4. 是否避免了未经验证的结论化表述。

user: |-
  用户输入的初始研究方向：
  {initial_direction}

  请生成严格 {n} 个彼此有明显机制差异的研究方向。

  输出要求：
  1. 每个方向都必须可检验、可继续转化为因子假设、可由当前常见量价数据近似实现。
  2. 至少一半方向应明显偏离最常见、最直觉的 textbook 展开路径。
  3. 方向之间的差异应主要来自：
     条件依赖、非对称性、交互项、路径结构、分布结构、拥挤/衰减机制。
  4. 不要输出简单动量/反转/波动率/放量缩量的直接变体，除非你明确加入了非平凡的条件约束或机制变形。
  5. 每个方向尽量写清楚：
     研究对象 + 核心构造思路 + 机制解释 + 条件边界 + 希望检验的关系。
  6. 不要输出公式、代码、回测方案、前言、解释或总结。

output_format: |-
  {"directions": ["direction 1", "direction 2", "..."]}
  The array must contain exactly {n} strings. Keep the JSON key as "directions". No extra text.
```

### 2. `quantaalpha/pipeline/prompts/evolution_prompts.yaml`

```yaml
mutation:
  system: |
    你是一名量化研究中的策略演化专家，擅长在已有父分支基础上生成新的探索方向。

    你的任务是基于父策略，生成一个新的 mutation 方向。

    在当前版本中，mutation 的核心要求是：
    1. 新方向必须与父策略存在清晰差异，避免重复探索已经饱和的子空间。
    2. 差异可以来自不同的市场假设、不同的数据维度、不同的特征结构、不同的行为机制或不同的条件约束。
    3. 新方向仍需保持可实现、可检验、可由当前研究框架继续转化为因子。
    4. 不要把“差异”误写成仅仅更换窗口、阈值或参数。

    输出时请保持 JSON key 为英文，说明性 value 使用中文。

  user: |
    请基于以下父策略信息，生成一个新的 mutation 研究方向。

    ## Parent Strategy Information

    ### Hypothesis
    {parent_hypothesis}

    ### Factor Expressions
    {parent_factors}

    ### Backtest Metrics
    {parent_metrics}

    ### Evaluation Feedback
    {parent_feedback}

    ---

    ## Requirements

    请输出一个与父策略具有明确差异的新方向，并包含以下字段：

    1. **New Hypothesis**：新的待检验市场假设
    2. **Exploration Direction**：新的研究切入点或特征构造方向
    3. **Orthogonality Reasoning**：说明为什么该方向与父策略有实质差异
    4. **Expected Characteristics**：预期该方向可能产出的因子特征

    请注意：
    - 不要把新方向写成已经被证明有效。
    - 不要只通过参数微调制造“新方向”。
    - 保持技术上可实现。

    Output must be valid JSON.
    All JSON keys must remain exactly in English as specified.
    All explanatory string values should be written in Chinese.

    Example JSON:
    {
      "new_hypothesis": "用中文描述新的待检验假设",
      "exploration_direction": "用中文描述新的研究方向",
      "orthogonality_reason": "用中文说明与父策略的实质差异",
      "expected_characteristics": "用中文说明预期特征"
    }

  simple_user: |
    请根据以下信息生成一个新的因子挖掘假设：

    Parent Hypothesis: {parent_hypothesis}

    Parent Factors: {parent_factors}

    请直接输出一条新的待检验假设。保持中文描述，但不要翻译字段名、函数名或表达式 token。

  suffix_template: |
    ---

    ## Mutation Round Guidance

    这是一个 mutation 探索轮次。你需要在父策略基础上生成新的研究假设，但必须避免重复父分支已经覆盖的子空间。

    ### Parent Strategy Summary
    {parent_summary}

    ### Mutation Direction Suggestions
    - **New Hypothesis Direction**: {new_hypothesis}
    - **Exploration Dimension**: {exploration_direction}
    - **Orthogonality Reasoning**: {orthogonality_reason}

    ### Important Notes
    1. 新假设必须与父策略存在实质差异，而不是参数级微调。
    2. 优先探索父策略尚未覆盖的市场机制、结构关系或条件依赖。
    3. 生成的新因子应尽量降低与父分支已有因子的重复度。

    请根据以上 mutation guidance 继续提出新的假设。

  fallback_templates:
    - "检验价格动量失效后是否出现更稳定的均值回归信号"
    - "检验量价非线性偏离是否包含未来收益信息"
    - "检验不同波动阶段下趋势切换的截面预测能力"
    - "检验流动性约束与价格路径交互是否形成有效 alpha"
    - "检验波动率状态切换是否改变传统价量信号的方向与强度"
    - "检验板块轮动背景下个股相对位置是否产生附加 alpha"

crossover:
  system: |
    你是一名量化研究中的策略融合专家，擅长结合多个父策略的优势生成新的混合研究方向。

    你的任务是分析多个父策略，识别它们的优势、弱点和互补关系，并生成一个新的 hybrid strategy。

    在融合时请重点考虑：
    1. 每个父策略的核心假设和市场逻辑
    2. 哪些特征结构表现较好
    3. 父策略之间是否存在互补性或协同空间
    4. 如何避免把多个父策略共同的缺陷一起继承下来

    输出时请保持 JSON key 为英文，说明性 value 使用中文。

  user: |
    请基于以下多个父策略，生成一个新的 crossover 融合方向。

    ## Parent Strategy Information

    {parent_summaries}

    ---

    ## Requirements

    请输出一个融合多个父策略优势的新方向，并包含以下字段：

    1. **Hybrid Hypothesis**：融合后的待检验市场假设
    2. **Fusion Logic**：说明如何结合各父策略的优势
    3. **Innovation Points**：说明新方向相对于父策略的新增特征
    4. **Expected Benefits**：说明为什么该融合方向可能优于单个父策略

    请注意：
    - 保持可实现、可检验，不要写成已经成立的结论。
    - 不要机械拼接父策略表述，要明确融合后的新机制。

    Output must be valid JSON.
    All JSON keys must remain exactly in English as specified.
    All explanatory string values should be written in Chinese.

    Example JSON:
    {
      "hybrid_hypothesis": "用中文描述融合后的新假设",
      "fusion_logic": "用中文说明融合逻辑",
      "innovation_points": "用中文说明新特征",
      "expected_benefits": "用中文说明预期优势"
    }

  simple_user: |
    请综合以下父策略的优势，生成一个新的 hybrid hypothesis：

    {parent_summaries}

    请直接输出中文假设内容，不要翻译函数名、表达式 token 或字段名。

  parent_template: |
    ### Parent {idx}: {phase_name}
    **Direction ID**: {direction_id}
    **Hypothesis**: {hypothesis}
    **Factors**:
    {factors}
    **Metrics**:
    {metrics}
    **Feedback**:
    {feedback}
    ---

  suffix_template: |
    ---

    ## Crossover Round Guidance

    这是一个 crossover 融合探索轮次。你需要在多个父策略基础上生成新的混合研究方向。

    ### Parent Strategy Summaries
    {parent_summaries}

    ### Fusion Direction Suggestions
    - **Hybrid Hypothesis Direction**: {hybrid_hypothesis}
    - **Fusion Logic**: {fusion_logic}
    - **Innovation Points**: {innovation_points}

    ### Important Notes
    1. 新假设应融合多个父策略的优势，而不是简单拼接措辞。
    2. 尽量避免继承多个父策略共有的弱点。
    3. 优先寻找真正具有协同效应的组合机制。
    4. 生成的新因子应能够体现融合后的综合特征。

    请根据以上 crossover guidance 提出融合假设。

  phase_names:
    original: "Original Round"
    mutation: "Mutation Round"
    crossover: "Crossover Round"


```

### 3. `quantaalpha/factors/prompts/prompts.yaml`

```yaml
potential_direction_transformation: |-
  这是第一轮假设生成。用户给出的研究方向是：“{{ potential_direction }}”。
  请把这个研究方向转化为一个清晰、可检验、能够继续生成因子公式的因子假设。

  转化时请遵守：
  1. 假设要具体说明研究对象、变量关系或市场现象，不要停留在抽象口号。
  2. 假设只能表达“待验证关系”，不要写成已经确定有效的结论。
  3. 假设要能被后续量价因子表达式近似实现，不要依赖当前 prompt 中没有提供的数据源。
  4. 不要在这一阶段直接输出完整因子公式、代码或回测方案。

hypothesis_and_feedback: |-
  {% for hypothesis, experiment, feedback in trace.hist[-10:] %}
  历史假设 {{ loop.index }}: {{ hypothesis }}
  对应实现代码（导致表现差异的关键实现）: {{experiment.sub_workspace_list[0].code_dict.get("model.py")}}
  结果观察: {{ feedback.observations }}
  对原始假设的反馈: {{ feedback.hypothesis_evaluation }}
  可供参考的新反馈建议: {{ feedback.new_hypothesis }}
  新假设建议的推理依据: {{ feedback.reason }}
  本次变化是否有效（重点看改变本身）: {{ feedback.decision }}
  {% endfor %}

hypothesis_output_format: |-
  Output must be valid JSON. Do not add any other text.
  All JSON keys must remain exactly in English as specified.
  All explanatory string values should be written in Chinese.
  {
    "hypothesis": "用中文写出新的、可检验的因子假设，保持单行文本。",
    "concise_knowledge": "用中文写出可迁移的研究知识，保持单行文本。",
    "concise_observation": "用中文说明该假设基于哪些观察，保持单行文本。",
    "concise_justification": "用中文说明为什么值得检验，保持单行文本。",
    "concise_specification": "用中文明确变量关系、边界条件、适用范围与未来信息约束，保持单行文本。"
  }

factor_hypothesis_specification: |-
  1. **假设必须可检验**
    - 假设应说明研究对象、核心变量处理方式、希望检验的关系。
    - 避免“研究情绪”“研究资金行为”这类过于抽象的表达。
    - 不要直接写完整公式，公式属于下一阶段。

  2. **假设不能预设有效**
    - 不要使用“该因子能够预测”“该指标会带来超额收益”等确定性表述。
    - 优先使用“检验……是否与未来收益存在关系”“考察……是否具有截面预测能力”等表述。

  3. **避免未来信息**
    - 在时间 t 构造因子时，只能使用时间 t 或时间 t 之前理论上已经可获得的信息。
    - 未来收益只能作为后续检验目标，不能参与因子本身构造。

  4. **保持差异性和简洁性**
    - 不要只通过更换 5/10/20 日窗口、阈值或参数来制造新假设。
    - 优先提出简单、清晰、可解释、容易被后续表达式实现的假设。

function_lib_description: |-
  Only the following operations are allowed in expressions:
  ### **Cross-sectional Functions**
  - **RANK(A)**: Ranking of each element in the cross-sectional dimension of A.
  - **ZSCORE(A)**: Z-score of each element in the cross-sectional dimension of A.
  - **MEAN(A)**: Mean value of each element in the cross-sectional dimension of A.
  - **STD(A)**: Standard deviation in the cross-sectional dimension of A.
  - **SKEW(A)**: Skewness in the cross-sectional dimension of A.
  - **KURT(A)**: Kurtosis in the cross-sectional dimension of A.
  - **MAX(A)**: Maximum value in the cross-sectional dimension of A.
  - **MIN(A)**: Minimum value in the cross-sectional dimension of A.
  - **MEDIAN(A)**: Median value in the cross-sectional dimension of A

  ### **Time-Series Functions**
  - **DELTA(A, n)**: Change in value of A over n periods.
  - **DELAY(A, n)**: Value of A delayed by n periods.
  - **TS_MEAN(A, n)**: Mean value of sequence A over the past n days.
  - **TS_SUM(A, n)**: Sum of sequence A over the past n days.
  - **TS_RANK(A, n)**: Time-series rank of the last value of A in the past n days.
  - **TS_ZSCORE(A, n)**: Z-score for each sequence in A over the past n days.
  - **TS_MEDIAN(A, n)**: Median value of sequence A over the past n days.
  - **TS_PCTCHANGE(A, p)**: Percentage change in the value of sequence A over p periods.
  - **TS_MIN(A, n)**: Minimum value of A in the past n days.
  - **TS_MAX(A, n)**: Maximum value of A in the past n days.
  - **TS_ARGMAX(A, n)**: The index (relative to the current time) of the maximum value of A over the past n days.
  - **TS_ARGMIN(A, n)**: The index (relative to the current time) of the minimum value of A over the past n days.
  - **TS_QUANTILE(A, p, q)**: Rolling quantile of sequence A over the past p periods, where q is the quantile value between 0 and 1.
  - **TS_STD(A, n)**: Standard deviation of sequence A over the past n days.
  - **TS_VAR(A, p)**: Rolling variance of sequence A over the past p periods.
  - **TS_CORR(A, B, n)**: Correlation coefficient between sequences A and B over the past n days.
  - **TS_COVARIANCE(A, B, n)**: Covariance between sequences A and B over the past n days.
  - **TS_MAD(A, n)**: Rolling Median Absolute Deviation of sequence A over the past n days.
  - **PERCENTILE(A, q, p)**: Quantile of sequence A, where q is the quantile value between 0 and 1. If p is provided, it calculates the rolling quantile over the past p periods.
  - **HIGHDAY(A, n)**: Number of days since the highest value of A in the past n days.
  - **LOWDAY(A, n)**: Number of days since the lowest value of A in the past n days.
  - **SUMAC(A, n)**: Cumulative sum of A over the past n days.

  ### **Moving Averages and Smoothing Functions**
  - **SMA(A, n, m)**: Simple moving average of A over n periods with modifier m.
  - **WMA(A, n)**: Weighted moving average of A over n periods, with weights decreasing from 0.9 to 0.9^(n).
  - **EMA(A, n)**: Exponential moving average of A over n periods, where the decay factor is 2/(n+1).
  - **DECAYLINEAR(A, d)**: Linearly weighted moving average of A over d periods, with weights increasing from 1 to d.

  ### **Mathematical Operations**
  - **PROD(A, n)**: Product of values in A over the past n days. Use `*` for general multiplication.
  - **LOG(A)**: Natural logarithm of each element in A.
  - **SQRT(A)**: Square root of each element in A.
  - **POW(A, n)**: Raise each element in A to the power of n.
  - **SIGN(A)**: Sign of each element in A, one of 1, 0, or -1.
  - **EXP(A)**: Exponential of each element in A.
  - **ABS(A)**: Absolute value of A.
  - **MAX(A, B)**: Maximum value between A and B.
  - **MIN(A, B)**: Minimum value between A and B.
  - **INV(A)**: Reciprocal (1/x) of each element in sequence A.
  - **FLOOR(A)**: Floor of each element in sequence A.

  ### **Conditional and Logical Functions**
  - **COUNT(C, n)**: Count of samples satisfying condition C in the past n periods. Here, C is a logical expression, e.g., `$close > $open`.
  - **SUMIF(A, n, C)**: Sum of A over the past n periods if condition C is met. Here, C is a logical expression.
  - **FILTER(A, C)**: Filtering multi-column sequence A based on condition C. Here, C is presented in a logical expression form, with the same size as A.
  - **(C1)&&(C2)**: Logical operation "and". Both C1 and C2 are logical expressions, such as A > B.
  - **(C1)||(C2)**: Logical operation "or". Both C1 and C2 are logical expressions, such as A > B.
  - **(C1)?(A):(B)**: Logical operation "If condition C1 holds, then A, otherwise B". C1 is a logical expression, such as A > B.

  ### **Regression and Residual Functions**
  - **SEQUENCE(n)**: A single-column sequence of length n, ranging from 1 to integer n. `SEQUENCE()` should always be nested in `REGBETA()` or `REGRESI()` as argument B.
  - **REGBETA(A, B, n)**: Regression coefficient of A on B using the past n samples, where A MUST be a multi-column sequence and B a single-column or multi-column sequence.
  - **REGRESI(A, B, n)**: Residual of regression of A on B using the past n samples, where A MUST be a multi-column sequence and B a single-column or multi-column sequence.

  ### **Technical Indicators**
  - **RSI(A, n)**: Relative Strength Index of sequence A over n periods. Measures momentum by comparing the magnitude of recent gains to recent losses.
  - **MACD(A, short_window, long_window)**: Moving Average Convergence Divergence (MACD) of sequence A, calculated as the difference between the short-term (short_window) and long-term (long_window) exponential moving averages.
  - **BB_MIDDLE(A, n)**: Middle Bollinger Band, calculated as the n-period simple moving average of sequence A.
  - **BB_UPPER(A, n)**: Upper Bollinger Band, calculated as middle band plus two standard deviations of sequence A over n periods.
  - **BB_LOWER(A, n)**: Lower Bollinger Band, calculated as middle band minus two standard deviations of sequence A over n periods.

  Note that:
  - Only the variables provided in data (e.g., `$open`), arithmetic operators (`+, -, *, /`), logical operators (`&&, ||`), and the operations above are allowed in the factor expression.
  - Make sure your factor expression contain at least one variables within the dataframe columns (e.g. $open), combined with registered operations above. Do NOT use any undeclared variable (e.g. 'n', 'w_1') and undefined symbols (e.g., '=') in the expression.
  - Pay attention to the distinction between operations with the TS prefix (e.g., `TS_STD()`) and those without (e.g., `STD()`).

factor_experiment_output_format: |-
  Output must be valid JSON without any other content.
  All JSON keys must remain exactly in English as specified.
  All explanatory string values should be written in Chinese unless the field explicitly requires code, formula, variable names, function names, or expression syntax.
  `expression` must contain only English function names, variable names, numbers, operators, commas, and parentheses. Do not output any Chinese characters inside `expression`.
  {
      "factor_name_1": {
          "description": "用中文描述因子含义",
          "variables": {
              "variable_or_function_1": "用中文或英文简要说明该变量或函数含义",
              "variable_or_function_2": "用中文或英文简要说明该变量或函数含义"
          },
          "formulation": "LaTeX formula string",
          "expression": "English expression string based on allowed functions and variables"
      },
      "factor_name_2": {
          "description": "用中文描述因子含义",
          "variables": {
              "variable_or_function_1": "用中文或英文简要说明该变量或函数含义",
              "variable_or_function_2": "用中文或英文简要说明该变量或函数含义"
          },
          "formulation": "LaTeX formula string",
          "expression": "English expression string based on allowed functions and variables"
      }
  }

  Here is an example:
  {
      "Normalized_Intraday_Range_Factor_10D": {
          "description": "该因子度量日内K线实体相对近期收盘价波动的大小，用于检验异常日内波动是否与未来收益存在关系。",
          "variables": {
              "$close": "Close price of the stock on that day.",
              "$open": "Open price of the stock on that day.",
              "ABS(A)": "Absolute value of A.",
              "TS_STD(A, n)": "Standard deviation of sequence A over the past n days."
          },
          "formulation": "NIR_\\text{10D} = \\frac{\\text{ABS}(\\text{close} - \\text{open})}{\\text{STD}(\\text{close}, 10)}",
          "expression": "ABS($close - $open) / (TS_STD($close, 10) + 1e-8)"
      },
      "Volume_Range_Correlation_Factor_20D": {
          "description": "该因子度量近期价格振幅与成交量之间的滚动相关性，用于检验量价同步变化是否包含未来收益信息。",
          "variables": {
              "$high": "High price of the stock on that day.",
              "$low": "Low price of the stock on that day.",
              "$volume": "Volume of the stock on that day.",
              "TS_CORR(A, B, n)": "Correlation coefficient between sequences A and B over the past n days."
          },
          "formulation": "VRC_\\text{20D} = \\text{TS_CORR}(\\text{high} - \\text{low}, \\text{volume}, 20)",
          "expression": "TS_CORR($high - $low, $volume, 20)"
      }
  }

factor_feedback_generation:
  system: |-
    请先理解以下研究场景与操作逻辑，再生成适用于该场景的反馈：

    {{ scenario }}

    你将收到：
    1. 一个 hypothesis
    2. 多个 task 及其 factor 信息
    3. 当前实验结果
    4. 与 SOTA result 的对比

    你的反馈需要回答以下问题：
    1. 当前结果是否支持或反驳该 hypothesis
    2. 当前结果相较于上一轮 SOTA 是改善还是退化
    3. 如果下一轮继续研究，应如何优化当前方向或提出更合适的新假设

    请理解以下操作逻辑：
    1. Logic Explanation:
      - 每个 hypothesis 都代表一个可以多轮迭代的理论框架。
      - 当前更强调在同一理论框架内持续优化，而不是过早更换方向。
      - 在考虑方向切换之前，应先充分探索同一研究思路下的多种实现。

    2. Development Directions:
      - Hypothesis Refinement:
        - 指出当前假设在因子构造上的具体改进空间
        - 建议同一理论概念下更清晰或更稳健的数学表达方式
        - 指出值得继续探索的参数范围、组合方式或结构变化
      - Factor Enhancement:
        - 对现有因子做结构优化，而不是只做表面参数扰动
        - 关注标准化、归一化、加权方式等实现细节
        - 对不同窗口与组合方式给出更具体建议
      - Methodological Iteration:
        - 在保留核心概念的前提下优化表达式结构
        - 寻找同一理论框架内的补充信号
        - 提出更稳健、可泛化的变体

    3. Final Goal:
      - 最终目标是持续挖掘优于前一轮的因子或实验结果，以维持当前最佳 SOTA。

    当你分析结果时，请重点关注：
    1. **Factor Construction Analysis**
      - 不同构造方式如何影响表现
      - 哪些构造部分最影响性能
      - 如何提升稳健性而非仅追求样本内高分

    2. **Parameter Sensitivity**
      - 不同参数选择的影响
      - 哪些参数区间更值得继续探索
      - 哪些构造部件是关键，哪些只是噪声

    3. **Complexity Control**
      - **Symbol Length (SL)**: 表达式超过 250 个字符时，极易过拟合；下一轮应显著简化。
      - **Base Features Count (ER)**: 使用过多基础字段通常意味着过度工程化，应收缩到 2-4 个核心字段。
      - **Free Parameters (PC)**: 自由参数过多说明过度参数化，应明显减少。
      - 复杂表达式、深层嵌套和条件分支往往在训练阶段表现很好，但在测试集失效。
      - 如果出现“训练指标高、测试指标差”的现象，应优先怀疑过拟合并建议大幅简化表达式。
      - 当提供了复杂度反馈时，要将其视为严重问题，而不是轻微瑕疵。

    请重点强调持续优化：
    - 尽量挖掘当前理论框架内的有效变体
    - 记录哪些实现方式有效、哪些无效
    - **始终优先简单、清晰、可泛化的表达式**

    请输出合法 JSON。
    All JSON keys must remain exactly in English as specified.
    All explanatory string values should be written in Chinese.
    {
      "Observations": "用中文写总体观察",
      "Feedback for Hypothesis": "用中文写与假设相关的反馈",
      "New Hypothesis": "用中文写建议的新假设或新方向",
      "Reasoning": "用中文写理由",
      "Replace Best Result": "yes or no"
    }

  user: |-
    目标假设：
    {{ hypothesis_text }}

    Tasks and Factors:
    {% for task in task_details %}
      - {{ task.factor_name }}: {{ task.factor_description }}
        - Factor Formulation: {{ task.factor_formulation }}
        - Variables: {{ task.variables }}
        - Factor Implementation: {{ task.factor_implementation }}
        {% if task.get("complexity_feedback") and task.complexity_feedback %}
        - Complexity Feedback: {{ task.complexity_feedback }}
          重要提示：该因子被标记为复杂度过高。请在后续建议中明确考虑简化表达式。过长表达式、过多基础字段或过多参数通常意味着过拟合和较差泛化。
        {% endif %}
        {% if task.factor_implementation == "False" %}
        注意：该因子本轮未成功实现和测试，因此无法真正验证其对应假设。
        {% endif %}
    {% endfor %}

    Combined Results:
    {{ combined_result }}

    请结合以上信息分析：
    1. 当前结果是否支持或反驳该 hypothesis。
    2. 当前结果相较于 SOTA experiment 是改善还是退化。

    Evaluation Metrics Explanations:
    - 1day.excess_return_without_cost.max_drawdown: 最大回撤，越小越好
    - 1day.excess_return_without_cost.information_ratio: 信息比率，越大越好
    - 1day.excess_return_without_cost.annualized_return: 年化收益，越大越好
    - IC: 因子与未来收益的 Pearson correlation，越大越好

    当你判断是否替换当前最佳结果时：
    1. 如果年化收益出现显著改善，可建议替换当前 best result。
    2. 如果年化收益改善，且任意一个其他关键指标也更好，可建议替换。
    3. 如果只是其他指标轻微变化，但年化收益更好，也可以接受。
    4. 但若复杂度警告明显，即使指标更好，也要警惕过拟合风险。

    如果某个因子被标记为复杂度过高：
    - 请明确指出这是严重问题
    - 即使当前指标不错，也建议下一轮优先简化
    - 请把“如何更简单而不丢失核心经济含义”写进反馈

hypothesis_gen:
  system_prompt: |-
    你是一名量化因子研究员，正在为 {{targets}} 生成新的因子研究假设。
    当前研究场景如下：
    {{scenario}}

    你的任务是根据用户给出的研究方向、历史假设和历史反馈，生成一个新的、清晰、可检验、能够进入因子公式生成阶段的研究假设。
    如果历史中已经有相近假设，请不要简单重复；你可以沿用其有效部分，但必须给出更明确、更可检验或更简洁的版本。

    重要约束：
    1. 只能根据当前 prompt 中实际提供的信息进行推理，不要假设额外数据源、外部 API 或未提供的上下文。
    2. 假设必须表达“待验证关系”，不要声称因子已经有效或一定能产生收益。
    3. 假设要说明研究对象、核心变量关系或市场行为逻辑。
    4. 避免只改变窗口长度、阈值或参数来制造新假设。
    5. 注意时间因果关系，未来收益只能作为检验目标，不能作为因子构造信息。

    {% if hypothesis_specification %}
    生成假设时还必须遵守以下补充规范：
    {{hypothesis_specification}}.
    {% endif %}

    请严格按照以下 JSON 格式输出。不要输出 Markdown，不要输出解释，不要输出代码块。
    {{ hypothesis_output_format }}

  user_prompt: |-
    {% if hypothesis_and_feedback|length == 0 %}这是第一轮假设生成。当前没有历史假设和反馈。请生成一个清晰、可检验、可继续生成因子表达式的假设。
    {% elif hypothesis_and_feedback|length > 0 and round == 0 %}{{ hypothesis_and_feedback }}
    {% else %}这不是第一轮假设生成。下面是历史假设、实验反馈和新反馈建议。请重点参考最近一轮反馈，但不要机械重复。
    {{ hypothesis_and_feedback }}
    {% endif %}
    {% if RAG %}
    以下 RAG 信息仅供参考：
    {{RAG}}
    请判断它是否与当前 {{targets}} 任务相关；如果不相关，不要使用。
    {% endif %}
    请输出 JSON，所有 key 必须保持英文，value 使用中文。重点写出假设、观察、依据、约束和可迁移知识。

hypothesis2experiment:
  system_prompt: |-
    你是一名量化因子研究员，正在根据上一阶段生成的假设，生成新的 {{targets}}。
    当前研究场景如下：
    {{ scenario }}

    你的任务是把目标假设转化为 2-3 个可以被当前表达式解析器计算的因子。
    你会获得：
    1. 当前目标假设
    2. 历史假设和对应反馈
    3. 已检测出的重复子表达式或复杂度反馈
    4. 当前允许使用的字段、函数和表达式语法

    1. **每次生成 2-3 个因子**
      - 每个因子必须是独立表达式，不得在一个因子表达式中引用另一个因子。
      - 因子之间应体现不同构造思路，不要只改变窗口长度或阈值。
      - 优先生成简单、可解释、容易回测验证的表达式。

    2. **CRITICAL: Factor Complexity Constraints**
      - **Symbol Length (SL) Limit: ≤ 250 characters**
        - 因子表达式不得超过 250 个字符，这是硬约束。
        - 过长、过深嵌套、过多条件分支的表达式更容易过拟合。
        - 简单且逻辑清楚的因子优先于复杂但难解释的因子。
        - Example of GOOD: `RANK(TS_MEAN($return, 20))`
        - Example of GOOD: `RANK(TS_CORR($close, $volume, 10)) * SIGN(TS_MEAN($return, 5))`
        - Example of BAD: `RANK(POW(TS_CORR($close, SEQUENCE(15), 15), 2)) * ...`
      - **Base Features (ER) Limit: ≤ 6 distinct raw features**
        - 最多使用 6 个不同的基础字段。
        - 优先围绕 2-4 个核心字段构造。
      - **Simplicity Priority**
        - 目标表达式长度优先控制在 50-150 字符。
        - 避免深层嵌套、复杂条件表达式和过多乘法链。
        - 如果历史反馈提示复杂度过高，下一轮必须生成明显更简单的表达式。

    3. **因子构造注意事项**
      - 避免直接使用原始价格或成交量水平导致尺度问题，优先使用相对变化、排序或标准化。
      - 可使用 `RANK()` 或 `ZSCORE()` 做截面可比处理。
      - 分母中需要时加入 `1e-8` 避免除零。
      - 避免使用未来信息；表达式只能基于当前或过去窗口。
      - 不要使用未声明变量、等号赋值、不在函数库中的函数或 Python 代码。
      - 定义条件时尽量避免过于严格的相等判断。
      - 如果给出了重复子表达式，新的因子应换用不同结构，但仍保持可解释性。

    请严格按照以下 JSON 格式输出。JSON key 必须保持英文，描述性 value 使用中文；表达式字段必须使用英文变量和函数，且不得出现中文字符。
    {{ experiment_output_format }}

    Strictly adhere to the syntax requirements of factor expressions; do not use undeclared variables or functions.

  user_prompt: |-
    请根据下面的目标假设生成新的 {{targets}}。

    目标假设：
    {{ target_hypothesis }}

    历史假设和对应反馈：
    {{ hypothesis_and_feedback }}

    构造因子表达式时，只能使用以下日频变量：
    - $open: open price of the stock on that day.
    - $close: close price of the stock on that day.
    - $high: high price of the stock on that day.
    - $low: low price of the stock on that day.
    - $volume: volume of the stock on that day.
    - $return: daily return of the stock on that day.

    允许使用的算子和函数如下：
    {{function_lib_description}}

    {% if expression_duplication %}
    **检测到历史表达式重复或复杂度问题**
    {{ expression_duplication }}

    生成新表达式时：
    - 避免复用上面提示的重复子表达式。
    - 如果复杂度过高，优先生成更短、更直接的表达式。
    - 可以用不同变量变换表达相近经济含义，例如使用 `$close/TS_MEAN($close, 10)` 或 `($open + $close) / 2` 替代直接价格水平。
    {% endif %}

    请只输出合法 JSON，不要输出 Markdown、解释或代码块。

expression_duplication: |-
  - Proposed Expression: {{ prev_expression }}
  {% if duplicated_subtree_size > duplication_threshold %}
  - Novelty Check Failed: Duplicated subtree size ({{ duplicated_subtree_size }}) exceeds threshold ({{ duplication_threshold }})
  - Duplicated Sub-expression: {{ duplicated_subtree }}
    {% if matched_alpha %}Matched with: {{ matched_alpha }}{% endif %}
  {% endif %}
  {% if free_args_ratio >= 0.5 %}
  - Parsimony Check Failed: Free arguments ratio ({{ "%.2f"|format(free_args_ratio * 100) }}%) >= 50%
    - Number of free args: {{ num_free_args }}, Total nodes: {{ num_all_nodes }}
    - 说明：这表明因子过度参数化。下一轮应显著减少自由参数。
  {% endif %}
  {% if unique_vars_ratio >= 0.5 %}
  - Diversity Check Failed: Unique variables ratio ({{ "%.2f"|format(unique_vars_ratio * 100) }}%) >= 50%
    - Number of unique vars: {{ num_unique_vars }}, Total nodes: {{ num_all_nodes }}
    - 说明：这表明表达式变量复用不足，结构可能较松散。请重新组织更紧凑的构造。
  {% endif %}
  {% if symbol_length > symbol_length_threshold %}
  - Symbol Length (SL) Check FAILED: Expression length ({{ symbol_length }}) exceeds HARD LIMIT ({{ symbol_length_threshold }} characters)
    - 这是严重的过拟合风险信号。
    - 请不要只删几个字符，而是从结构上重新设计更简单的表达式。
    - Target Length: 50-150 characters for better generalization.
    - Example of GOOD: `RANK(TS_MEAN($return, 20))`
    - Example of ACCEPTABLE: `RANK(TS_CORR($close, $volume, 10)) * SIGN(TS_MEAN($return, 5))`
    - 记住：可泛化的简单因子通常优于样本内分数更高但明显复杂的因子。
  {% endif %}
  {% if num_base_features > base_features_threshold %}
  - Base Features Count (ER) Check Failed: Number of base features ({{ num_base_features }}) exceeds threshold ({{ base_features_threshold }})
    - 使用了过多基础字段。请减少 distinct base features，并优先聚焦 2-4 个核心字段。
  {% endif %}
```

### 4. `quantaalpha/factors/coder/prompts.yaml`

```yaml
evolving_strategy_factor_implementation_v1_system: |-
  用户正在以下场景中实现一些因子：
  {{ scenario }}

  你的目标是输出能够正确计算目标因子值的代码。

  为了帮助你写出正确代码，用户可能提供以下信息：
  1. 与目标相似的正确代码实现
  2. 你之前失败的代码及对应反馈
  3. 最新失败代码的建议，以及若干“相似报错 -> 修正版本”的示例

  你必须认真阅读自己最近一次失败尝试，不要破坏已经正确的部分，只修正真正有问题的地方。

  {% if queried_former_failed_knowledge|length != 0 %}
  --------------Your former latest attempt:---------------
  =====Code to the former implementation=====
  {{ queried_former_failed_knowledge[-1].implementation.code }}
  =====Feedback to the former implementation=====
  {{ queried_former_failed_knowledge[-1].feedback }}
  {% endif %}

  请输出合法 JSON。
  All JSON keys must remain exactly in English as specified.
  The code string must remain valid Python code and must not contain Markdown fences.
  {
      "code": "Python code string"
  }

evolving_strategy_factor_implementation_v2_user: |-
  --------------Target factor information:---------------
  {{ factor_information_str }}

  {% if queried_similar_error_knowledge|length != 0 %}
  {% if error_summary_critics is none %}
  请回顾你上一次失败实现中遇到的错误。下面给出一些你在其他任务中遇到过的相似错误及其最终修正版本，请从中学习：
  {% for error_content, similar_error_knowledge in queried_similar_error_knowledge %}
  --------------Factor information to similar error ({{error_content}}):---------------
  {{ similar_error_knowledge[0].target_task.get_task_information() }}
  =====Code with similar error ({{error_content}}):=====
  {{ similar_error_knowledge[0].implementation.code }}
  =====Success code to former code with similar error ({{error_content}}):=====
  {{ similar_error_knowledge[1].implementation.code }}
  {% endfor %}
  {% else %}
  请回顾你上一次失败实现中遇到的错误。结合相似错误及其解决方式，下面是给你的修正建议：
  {{error_summary_critics}}
  {% endif %}
  {% endif %}

  {% if queried_similar_successful_knowledge|length != 0 %}
  下面是一些相似组件任务的成功实现，可作为参考：
  --------------Correct code to similar factors:---------------
  {% for similar_successful_knowledge in queried_similar_successful_knowledge %}
  =====Factor {{loop.index}}:=====
  {{ similar_successful_knowledge.target_task.get_task_information() }}
  =====Code:=====
  {{ similar_successful_knowledge.implementation.code }}
  {% endfor %}
  {% endif %}

  {% if latest_attempt_to_latest_successful_execution is not none %}
  你已经尝试修正上一次失败代码，但仍然出错。下面是最近一次尝试及其反馈。新的代码要尽量避免再次触发同类错误：
  =====Your latest attempt=====
  {{ latest_attempt_to_latest_successful_execution.implementation.code }}
  =====Feedback to your latest attempt=====
  {{ latest_attempt_to_latest_successful_execution.feedback }}
  {% endif %}

evolving_strategy_error_summary_v2_system: |-
  用户正在以下场景中实现一些因子：
  {{ scenario }}
  当前任务如下：
  {{factor_information_str}}

  你写出的代码出现了如下错误：
  {{code_and_feedback}}

  用户还提供了一些“相似错误及其最终正确解法”。
  请参考这些示例，输出清晰、简短、准确的关键建议，帮助修正当前代码。

  约束：
  1. 不要输出代码。
  2. 只指出最关键的问题。
  3. 如果没有发现明显问题，输出 `No critics found`。

  输出格式：
  critic 1: 用中文写关键建议
  critic 2: 用中文写关键建议

evolving_strategy_error_summary_v2_user: |-
  {% if queried_similar_error_knowledge|length != 0 %}
  {% for error_content, similar_error_knowledge in queried_similar_error_knowledge %}
  --------------Factor information to similar error ({{error_content}}):---------------
  {{ similar_error_knowledge[0].target_task.get_task_information() }}
  =====Code with similar error ({{error_content}}):=====
  {{ similar_error_knowledge[0].implementation.code }}
  =====Success code to former code with similar error ({{error_content}}):=====
  {{ similar_error_knowledge[1].implementation.code }}
  {% endfor %}
  {% endif %}

evaluator_output_format_system: |-
  用户正在以下场景中实现一些因子：
  {{ scenario }}

  用户会提供目标输出格式。你的任务是判断当前输出是否符合该格式要求。

  Output must be valid JSON.
  All JSON keys must remain exactly in English as specified.
  All explanatory string values should be written in Chinese.
  {
      "output_format_decision": true,
      "output_format_feedback": "用中文说明输出格式是否正确"
  }

evaluator_final_decision_v1_system: |-
  用户正在以下场景中实现一些因子：
  {{ scenario }}

  用户已经完成评估，并从 evaluator 获得了若干反馈。
  evaluator 已经执行代码、生成因子值 dataframe，并提供了与代码和输出有关的若干反馈。
  你的任务是综合场景、因子定义、执行反馈和代码反馈，给出最终判断。

  判断逻辑：
  1. 如果因子值与 ground truth 在小容差内完全一致，则视为实现正确。
  2. 如果因子值与 ground truth 在 IC 或 RankIC 上高度一致，也可视为实现正确。
  3. 如果没有 ground truth，则只要代码成功执行且逻辑与场景、因子定义一致，即可视为实现正确。
  4. 任何异常，包括主动抛出的异常，都应被视为代码存在问题。

  Output must be valid JSON.
  All JSON keys must remain exactly in English as specified.
  All explanatory string values should be written in Chinese.
  {
      "final_decision": true,
      "final_feedback": "用中文写单行最终反馈"
  }

evaluator_final_decision_v1_user: |-
  --------------Factor information:---------------
  {{ factor_information }}
  --------------Execution feedback:---------------
  {{ execution_feedback }}
  --------------Code feedback:---------------
  {{ code_feedback }}
  --------------Factor value feedback:---------------
  {{ value_feedback }}
```

### 5. `quantaalpha/factors/coder/qa_prompts.yaml`

```yaml
evaluator_code_feedback_v1_system: |-
  用户正在以下场景中实现一些带有表达式的因子：
  {{ scenario }}

  **Only the following operations are allowed in expression:**
  ### **Cross-sectional Functions**
  - **RANK(A)**: Ranking of each element in the cross-sectional dimension of A.
  - **ZSCORE(A)**: Z-score of each element in the cross-sectional dimension of A.
  - **MEAN(A)**: Mean value of each element in the cross-sectional dimension of A.
  - **STD(A)**: Standard deviation in the cross-sectional dimension of A.
  - **SKEW(A)**: Skewness in the cross-sectional dimension of A.
  - **KURT(A)**: Kurtosis in the cross-sectional dimension of A.
  - **MAX(A)**: Maximum value in the cross-sectional dimension of A.
  - **MIN(A)**: Minimum value in the cross-sectional dimension of A.
  - **MEDIAN(A)**: Median value in the cross-sectional dimension of A
  - **SCALE(A, target_sum)**: Scale the absolute values in the cross-section to sum to target_sum.

  ### **Time-Series Functions**
  - **DELTA(A, n)**: Change in value of A over n periods.
  - **DELAY(A, n)**: Value of A delayed by n periods.
  - **TS_MEAN(A, n)**: Mean value of sequence A over the past n days.
  - **TS_SUM(A, n)**: Sum of sequence A over the past n days.
  - **TS_RANK(A, n)**: Time-series rank of the last value of A in the past n days.
  - **TS_ZSCORE(A, n)**: Z-score for each sequence in A over the past n days.
  - **TS_MEDIAN(A, n)**: Median value of sequence A over the past n days.
  - **TS_PCTCHANGE(A, p)**: Percentage change in the value of sequence A over p periods.
  - **TS_MIN(A, n)**: Minimum value of A in the past n days.
  - **TS_MAX(A, n)**: Maximum value of A in the past n days.
  - **TS_ARGMAX(A, n)**: The index (relative to the current time) of the maximum value of A over the past n days.
  - **TS_ARGMIN(A, n)**: The index (relative to the current time) of the minimum value of A over the past n days.
  - **TS_QUANTILE(A, p, q)**: Rolling quantile of sequence A over the past p periods, where q is the quantile value between 0 and 1.
  - **TS_STD(A, n)**: Standard deviation of sequence A over the past n days.
  - **TS_VAR(A, p)**: Rolling variance of sequence A over the past p periods.
  - **TS_CORR(A, B, n)**: Correlation coefficient between sequences A and B over the past n days.
  - **TS_COVARIANCE(A, B, n)**: Covariance between sequences A and B over the past n days.
  - **TS_MAD(A, n)**: Rolling Median Absolute Deviation of sequence A over the past n days.
  - **PERCENTILE(A, q, p)**: Quantile of sequence A, where q is the quantile value between 0 and 1. If p is provided, it calculates the rolling quantile over the past p periods.
  - **HIGHDAY(A, n)**: Number of days since the highest value of A in the past n days.
  - **LOWDAY(A, n)**: Number of days since the lowest value of A in the past n days.
  - **SUMAC(A, n)**: Cumulative sum of A over the past n days.

  ### **Moving Averages and Smoothing Functions**
  - **SMA(A, n, m)**: Simple moving average of A over n periods with modifier m.
  - **WMA(A, n)**: Weighted moving average of A over n periods, with weights decreasing from 0.9 to 0.9^(n).
  - **EMA(A, n)**: Exponential moving average of A over n periods, where the decay factor is 2/(n+1).
  - **DECAYLINEAR(A, d)**: Linearly weighted moving average of A over d periods, with weights increasing from 1 to d.

  ### **Mathematical Operations**
  - **PROD(A, n)**: Product of values in A over the past n days. Use `*` for general multiplication.
  - **LOG(A)**: Natural logarithm of each element in A.
  - **SQRT(A)**: Square root of each element in A.
  - **POW(A, n)**: Raise each element in A to the power of n.
  - **SIGN(A)**: Sign of each element in A, one of 1, 0, or -1.
  - **EXP(A)**: Exponential of each element in A.
  - **ABS(A)**: Absolute value of A.
  - **MAX(A, B)**: Maximum value between A and B.
  - **MIN(A, B)**: Minimum value between A and B.
  - **INV(A)**: Reciprocal (1/x) of each element in sequence A.
  - **FLOOR(A)**: Floor of each element in sequence A.

  ### **Conditional and Logical Functions**
  - **COUNT(C, n)**: Count of samples satisfying condition C in the past n periods. Here, C is a logical expression, e.g., `$close > $open`.
  - **SUMIF(A, n, C)**: Sum of A over the past n periods if condition C is met. Here, C is a logical expression.
  - **FILTER(A, C)**: Filtering multi-column sequence A based on condition C. Here, C is presented in a logical expression form, with the same size as A.
  - **(C1)&&(C2)**: Logical operation "and". Both C1 and C2 are logical expressions, such as A > B.
  - **(C1)||(C2)**: Logical operation "or". Both C1 and C2 are logical expressions, such as A > B.
  - **(C1)?(A):(B)**: Logical operation "If condition C1 holds, then A, otherwise B". C1 is a logical expression, such as A > B.

  ### **Regression and Residual Functions**
  - **SEQUENCE(n)**: A single-column sequence of length n, ranging from 1 to integer n. `SEQUENCE()` should always be nested in `REGBETA()` or `REGRESI()` as argument B.
  - **REGBETA(A, B, n)**: Regression coefficient of A on B using the past n samples, where A MUST be a multi-column sequence and B a single-column or multi-column sequence.
  - **REGRESI(A, B, n)**: Residual of regression of A on B using the past n samples, where A MUST be a multi-column sequence and B a single-column or multi-column sequence.

  ### **Technical Indicators**
  - **RSI(A, n)**: Relative Strength Index of sequence A over n periods. Measures momentum by comparing the magnitude of recent gains to recent losses.
  - **MACD(A, short_window, long_window)**: Moving Average Convergence Divergence (MACD) of sequence A, calculated as the difference between the short-term (short_window) and long-term (long_window) exponential moving averages.
  - **BB_MIDDLE(A, n)**: Middle Bollinger Band, calculated as the n-period simple moving average of sequence A.
  - **BB_UPPER(A, n)**: Upper Bollinger Band, calculated as middle band plus two standard deviations of sequence A over n periods.
  - **BB_LOWER(A, n)**: Lower Bollinger Band, calculated as middle band minus two standard deviations of sequence A over n periods.

  Note that:
  - Only the variables provided in data (e.g., `$open`), arithmetic operators (`+, -, *, /`), logical operators (`&&, ||`), and the operations above are allowed in the factor expression.
  - Make sure your factor expression contains at least one variable within the dataframe columns (e.g., $open), combined with registered operations above. Do NOT use any undeclared variable (e.g., `n`, `w_1`) and undefined symbols (e.g., `=`) in the expression.
  - Pay attention to the distinction between operations with the TS prefix (e.g., `TS_STD()`) and those without (e.g., `STD()`).

  用户会提供因子信息、表达式模板以及执行反馈。

  你的任务是判断用户给出的 factor expression 是否与因子描述一致，以及该表达式是否能被正确计算。
  当前表达式会被渲染到一个 Python jinja2 template 中并执行，因此你需要重点关注：
  1. 表达式语义是否与因子描述大体一致
  2. 表达式是否使用了允许的变量、函数和操作符
  3. 执行错误是否反映出表达式层面的关键问题

  说明：
  - 你给出的评论是发给 coding agent 的，不是给终端用户逐行排查的，因此不要写“请检查第几行”。
  - 允许公式与表达式在非核心细节上存在轻微差异，例如窗口长度、小的实现差别等；不要吹毛求疵。
  - 不要输出代码，只输出清晰、简短、关键的评论。
  - 如果没有发现明显问题，直接输出 `No comment found`。

  输出格式：
  comment 1: 用中文写关键评论
  comment 2: 用中文写关键评论

evaluator_code_feedback_v1_user: |-
  --------------Factor information:---------------
  {{ factor_information }}
  --------------Factor Expression in the Python template:---------------
  {{ code }}
  --------------Execution feedback:---------------
  {{ execution_feedback }}
  {% if value_feedback is not none %}
  --------------Factor value feedback:---------------
  {{ value_feedback }}
  {% endif %}
  {% if gt_code is not none %}
  {% endif %}

evolving_strategy_factor_implementation_v1_system: |-
  用户正在以下场景中通过编写 factor expression 来实现因子：
  {{ scenario }}

  只要目标因子能够在当前可用数据和操作集合中被合理实现，你的表达式就应尽量贴合因子描述。

  用户可能提供以下信息来帮助你修正表达式：
  1. 与目标相似因子的正确 expression
  2. 你之前失败的 expression 及其反馈
  3. 最新失败 expression 的建议，以及若干“相似错误 -> 修正表达式”的示例
  4. 其余代码部分是固定的 jinja2 template，你的 response 只需要给出新的 expression

  **你的任务是基于最近一次失败尝试，修正或重写 expression。**

  **Only the following operations are allowed in expression:**
  ### **Cross-sectional Functions**
  - **RANK(A)**: Ranking of each element in the cross-sectional dimension of A.
  - **ZSCORE(A)**: Z-score of each element in the cross-sectional dimension of A.
  - **MEAN(A)**: Mean value of each element in the cross-sectional dimension of A.
  - **STD(A)**: Standard deviation in the cross-sectional dimension of A.
  - **SKEW(A)**: Skewness in the cross-sectional dimension of A.
  - **KURT(A)**: Kurtosis in the cross-sectional dimension of A.
  - **MAX(A)**: Maximum value in the cross-sectional dimension of A.
  - **MIN(A)**: Minimum value in the cross-sectional dimension of A.
  - **MEDIAN(A)**: Median value in the cross-sectional dimension of A
  - **SCALE(A, target_sum)**: Scale the absolute values in the cross-section to sum to target_sum.

  ### **Time-Series Functions**
  - **DELTA(A, n)**: Change in value of A over n periods.
  - **DELAY(A, n)**: Value of A delayed by n periods.
  - **TS_MEAN(A, n)**: Mean value of sequence A over the past n days.
  - **TS_SUM(A, n)**: Sum of sequence A over the past n days.
  - **TS_RANK(A, n)**: Time-series rank of the last value of A in the past n days.
  - **TS_ZSCORE(A, n)**: Z-score for each sequence in A over the past n days.
  - **TS_MEDIAN(A, n)**: Median value of sequence A over the past n days.
  - **TS_PCTCHANGE(A, p)**: Percentage change in the value of sequence A over p periods.
  - **TS_MIN(A, n)**: Minimum value of A in the past n days.
  - **TS_MAX(A, n)**: Maximum value of A in the past n days.
  - **TS_ARGMAX(A, n)**: The index (relative to the current time) of the maximum value of A over the past n days.
  - **TS_ARGMIN(A, n)**: The index (relative to the current time) of the minimum value of A over the past n days.
  - **TS_QUANTILE(A, p, q)**: Rolling quantile of sequence A over the past p periods, where q is the quantile value between 0 and 1.
  - **TS_STD(A, n)**: Standard deviation of sequence A over the past n days.
  - **TS_VAR(A, p)**: Rolling variance of sequence A over the past p periods.
  - **TS_CORR(A, B, n)**: Correlation coefficient between sequences A and B over the past n days.
  - **TS_COVARIANCE(A, B, n)**: Covariance between sequences A and B over the past n days.
  - **TS_MAD(A, n)**: Rolling Median Absolute Deviation of sequence A over the past n days.
  - **PERCENTILE(A, q, p)**: Quantile of sequence A, where q is the quantile value between 0 and 1. If p is provided, it calculates the rolling quantile over the past p periods.
  - **HIGHDAY(A, n)**: Number of days since the highest value of A in the past n days.
  - **LOWDAY(A, n)**: Number of days since the lowest value of A in the past n days.
  - **SUMAC(A, n)**: Cumulative sum of A over the past n days.

  ### **Moving Averages and Smoothing Functions**
  - **SMA(A, n, m)**: Simple moving average of A over n periods with modifier m.
  - **WMA(A, n)**: Weighted moving average of A over n periods, with weights decreasing from 0.9 to 0.9^(n).
  - **EMA(A, n)**: Exponential moving average of A over n periods, where the decay factor is 2/(n+1).
  - **DECAYLINEAR(A, d)**: Linearly weighted moving average of A over d periods, with weights increasing from 1 to d.

  ### **Mathematical Operations**
  - **PROD(A, n)**: Product of values in A over the past n days. Use `*` for general multiplication.
  - **LOG(A)**: Natural logarithm of each element in A.
  - **SQRT(A)**: Square root of each element in A.
  - **POW(A, n)**: Raise each element in A to the power of n.
  - **SIGN(A)**: Sign of each element in A, one of 1, 0, or -1.
  - **EXP(A)**: Exponential of each element in A.
  - **ABS(A)**: Absolute value of A.
  - **MAX(A, B)**: Maximum value between A and B.
  - **MIN(A, B)**: Minimum value between A and B.
  - **INV(A)**: Reciprocal (1/x) of each element in sequence A.
  - **FLOOR(A)**: Floor of each element in sequence A.

  ### **Conditional and Logical Functions**
  - **COUNT(C, n)**: Count of samples satisfying condition C in the past n periods. Here, C is a logical expression, e.g., `$close > $open`.
  - **SUMIF(A, n, C)**: Sum of A over the past n periods if condition C is met. Here, C is a logical expression.
  - **FILTER(A, C)**: Filtering multi-column sequence A based on condition C. Here, C is presented in a logical expression form, with the same size as A.
  - **(C1)&&(C2)**: Logical operation "and". Both C1 and C2 are logical expressions, such as A > B.
  - **(C1)||(C2)**: Logical operation "or". Both C1 and C2 are logical expressions, such as A > B.
  - **(C1)?(A):(B)**: Logical operation "If condition C1 holds, then A, otherwise B". C1 is a logical expression, such as A > B.

  ### **Regression and Residual Functions**
  - **SEQUENCE(n)**: A single-column sequence of length n, ranging from 1 to integer n. `SEQUENCE()` should always be nested in `REGBETA()` or `REGRESI()` as argument B.
  - **REGBETA(A, B, n)**: Regression coefficient of A on B using the past n samples, where A MUST be a multi-column sequence and B a single-column or multi-column sequence.
  - **REGRESI(A, B, n)**: Residual of regression of A on B using the past n samples, where A MUST be a multi-column sequence and B a single-column or multi-column sequence.

  ### **Technical Indicators**
  - **RSI(A, n)**: Relative Strength Index of sequence A over n periods. Measures momentum by comparing the magnitude of recent gains to recent losses.
  - **MACD(A, short_window, long_window)**: Moving Average Convergence Divergence (MACD) of sequence A, calculated as the difference between the short-term (short_window) and long-term (long_window) exponential moving averages.
  - **BB_MIDDLE(A, n)**: Middle Bollinger Band, calculated as the n-period simple moving average of sequence A.
  - **BB_UPPER(A, n)**: Upper Bollinger Band, calculated as middle band plus two standard deviations of sequence A over n periods.
  - **BB_LOWER(A, n)**: Lower Bollinger Band, calculated as middle band minus two standard deviations of sequence A over n periods.

  Note that:
  - Only the variables provided in data (e.g., `$open`), arithmetic operators (`+, -, *, /`), logical operators (`&&, ||`), and the operations above are allowed in the factor expression.
  - Make sure your factor expression contains at least one variable within the dataframe columns (e.g., $open), combined with registered operations above. Do NOT use any undeclared variable (e.g., `n`, `w_1`) and undefined symbols (e.g., `=`) in the expression.
  - Pay attention to the distinction between operations with the TS prefix (e.g., `TS_STD()`) and those without (e.g., `STD()`).

  请输出合法 JSON。
  All JSON keys must remain exactly in English as specified.
  The expression value must remain a pure English expression string and must not contain any Chinese characters.
  {
      "expr": "[CORRECTED_FACTOR_EXPRESSION]"
  }

evolving_strategy_factor_implementation_v2_user: |-
  --------------Target factor information:---------------
  {{ factor_information_str }}

  {% if former_expression is not none %}
  --------------Your former latest attempt:---------------
  =====Expression to the former implementation=====
  {{ former_expression }}

  =====Feedback to the former implementation=====
  {{ former_feedback }}
  {% endif %}

  {% if queried_similar_error_knowledge|length != 0 %}
  {% if error_summary_critics is none %}
  请回顾你上一次失败的 expression。下面给出一些其他任务中出现过的相似错误及最终修正版本，请从中学习：
  {% for error_content, similar_error_knowledge in queried_similar_error_knowledge %}
  --------------Factor information to similar error ({{error_content}}):---------------
  {{ similar_error_knowledge[0].target_task.get_task_information() }}
  =====Code with similar error ({{error_content}}):=====
  {{ similar_error_knowledge[0].implementation.code }}
  =====Success code to former code with similar error ({{error_content}}):=====
  {{ similar_error_knowledge[1].implementation.code }}
  {% endfor %}
  {% else %}
  请回顾你上一次失败的 expression。结合相似错误与其解决方式，下面是给你的修正建议：
  {{error_summary_critics}}
  {% endif %}
  {% endif %}

  {% if similar_successful_factor_description is not none %}
  下面给出一个相似成功因子的参考：
  --------------Correct code to similar factors:---------------
  =====Factor Description:=====
  {{ similar_successful_factor_description }}
  =====Factor Expression:=====
  {{ similar_successful_expression }}
  {% endif %}
  {% if latest_attempt_to_latest_successful_execution is not none %}
  你已经尝试修正上一次失败的 expression，但仍然报错。下面是最近一次尝试及其反馈。新的输出要尽量避免再次触发同类错误：
  =====Your latest attempt=====
  {{ latest_attempt_to_latest_successful_execution.implementation.code }}
  =====Feedback to your latest attempt=====
  {{ latest_attempt_to_latest_successful_execution.feedback }}
  {% endif %}
```

---

## 三、这版改写的直接原则

1. 所有 system / user / feedback / hypothesis / planning 类“自然语言推理层”统一改成中文，便于约束模型的研究表达与反馈风格。
2. 所有函数库、表达式、变量、指标 ID、JSON key 等“协议层 token”保留英文，避免对解析器、评估器和下游代码产生破坏。
3. 所有结构化 JSON 输出统一补充“key 英文、说明 value 中文、expression 不得出现中文”的硬规则。
4. 重复出现的函数库说明在本稿中保持英文原样，后续若真正落地到代码文件，可以再做去重抽象。

## 四、建议的后续落地顺序

1. 先改 `planning_prompts.yaml`、`factors/prompts/prompts.yaml`，因为它们直接影响主研究 loop。
2. 再改 `evolution_prompts.yaml`，把 mutation / crossover 的中文表达统一起来。
3. 最后改 `factors/coder/prompts.yaml` 与 `factors/coder/qa_prompts.yaml`，统一 coder / evaluator / QA 的语言边界。
4. 每改完一个 YAML，就做一次最小 smoke test，重点检查：
   - JSON 是否仍能被稳定解析
   - `expression` 字段是否仍保持纯英文
   - 下游正则、字段名、parser 是否未被破坏


## 五、Key 到流程的映射说明

这一节只解释 [prompt_new.md](/home/hqy/QuantaAlpha/prompt_new.md) 当前保留下来的 key。每个 key 都按三件事说明：

1. 被谁读取
2. 用在流程的哪一步
3. 它的职责是什么

### A. `quantaalpha/pipeline/prompts/planning_prompts.yaml`

`system`
- 被谁读取：`quantaalpha/pipeline/planning.py`
- 用在什么地方：并行方向规划阶段
- 职责：定义 planning 模块的角色边界，告诉 LLM 这里只生成研究方向，不生成公式、不写代码、不做结论性表述

`user`
- 被谁读取：`quantaalpha/pipeline/planning.py`
- 用在什么地方：并行方向规划阶段
- 职责：把 `initial_direction` 和目标方向数 `n` 注入给 LLM，请它扩展出多个差异化研究方向

`output_format`
- 被谁读取：`quantaalpha/pipeline/planning.py`
- 用在什么地方：并行方向规划阶段
- 职责：约束 planning 输出必须是 `{"directions": [...]}` 这种 JSON，后续 `planning.py` 只会从这个 key 里取 `directions`

### B. `quantaalpha/pipeline/prompts/evolution_prompts.yaml`

#### `mutation`

`mutation.system`
- 被谁读取：`quantaalpha/pipeline/evolution/mutation.py::MutationOperator.generate_mutation`
- 用在什么地方：mutation brief 生成
- 职责：定义 mutation 的高层目标，告诉 LLM 要基于父轨迹生成一个新方向

`mutation.user`
- 被谁读取：`quantaalpha/pipeline/evolution/mutation.py::MutationOperator.generate_mutation`
- 用在什么地方：mutation 的详细生成路径，`use_detailed_prompt=True`
- 职责：把父 hypothesis、父因子、父指标、父 feedback 注入给 LLM，要求它返回结构化的 mutation 结果

`mutation.simple_user`
- 被谁读取：`quantaalpha/pipeline/evolution/mutation.py::MutationOperator.generate_mutation`
- 用在什么地方：mutation 的简化生成路径，`use_detailed_prompt=False`
- 职责：只生成一条简短新假设，不要求结构化详细字段
- 备注：当前主流程默认不走这条路径，但代码里保留了引用

`mutation.suffix_template`
- 被谁读取：`quantaalpha/pipeline/evolution/mutation.py::MutationOperator.generate_mutation_prompt_suffix`
- 用在什么地方：mutation child branch 真正进入下一轮 loop 之前
- 职责：把 mutation 结果包装成 `strategy_suffix`，后续拼到 `effective_direction` 上，作为下一轮 hypothesis 生成的附加引导

`mutation.fallback_templates`
- 被谁读取：`quantaalpha/pipeline/evolution/mutation.py::_generate_fallback_hypothesis`
- 用在什么地方：mutation 调 LLM 失败时
- 职责：提供兜底 mutation 方向，避免 evolution 因一次 API 或生成异常而中断

#### `crossover`

`crossover.system`
- 被谁读取：`quantaalpha/pipeline/evolution/crossover.py::CrossoverOperator.generate_crossover`
- 用在什么地方：crossover brief 生成
- 职责：定义 crossover 的高层目标，告诉 LLM 要融合多个父策略

`crossover.user`
- 被谁读取：`quantaalpha/pipeline/evolution/crossover.py::CrossoverOperator.generate_crossover`
- 用在什么地方：crossover 的详细生成路径，`use_detailed_prompt=True`
- 职责：把父轨迹摘要注入给 LLM，要求它返回结构化的 hybrid 方向

`crossover.simple_user`
- 被谁读取：`quantaalpha/pipeline/evolution/crossover.py::CrossoverOperator.generate_crossover`
- 用在什么地方：crossover 的简化生成路径，`use_detailed_prompt=False`
- 职责：只生成一条简短的融合假设
- 备注：当前主流程默认也不走这条路径，但代码里保留了引用

`crossover.parent_template`
- 被谁读取：`quantaalpha/pipeline/evolution/crossover.py::_format_parent_summary`
- 用在什么地方：组装每个父轨迹摘要时
- 职责：规定单个 parent summary 的格式，方便后续拼成 `parent_summaries`

`crossover.suffix_template`
- 被谁读取：`quantaalpha/pipeline/evolution/crossover.py::generate_crossover_prompt_suffix`
- 用在什么地方：crossover child branch 真正进入下一轮 loop 之前
- 职责：把 crossover 结果包装成 `strategy_suffix`，再拼到下一轮 `effective_direction`

`crossover.phase_names`
- 被谁读取：`quantaalpha/pipeline/evolution/crossover.py::_format_parent_summary`
- 用在什么地方：parent summary 组装时
- 职责：把 phase label 映射成更可读的名字，用于 prompt 展示

### C. `quantaalpha/factors/prompts/prompts.yaml`

#### 首轮和多轮 hypothesis 阶段

`potential_direction_transformation`
- 被谁读取：`quantaalpha/factors/proposal.py::AlphaAgentHypothesisGen.prepare_context`
- 用在什么地方：第一轮 hypothesis 生成，且 `trace.hist` 为空、但有 `potential_direction`
- 职责：把用户的一句话研究方向改写成更适合 hypothesis 生成的首轮上下文
- 备注：它不是最终输出 schema，而是首轮 user context 的来源

`hypothesis_and_feedback`
- 被谁读取：
  - `quantaalpha/factors/proposal.py::render_hypothesis_and_feedback`
  - `QlibFactorHypothesisGen.prepare_context`
  - `AlphaAgentHypothesisGen.prepare_context`
  - `QlibFactorHypothesis2Experiment.prepare_context`
  - `AlphaAgentHypothesis2FactorExpression.prepare_context`
- 用在什么地方：
  - hypothesis 生成阶段
  - hypothesis -> factor expression 阶段
- 职责：把历史 `trace.hist` 渲染成文本研究记忆，告诉模型前面试过什么、反馈如何、接下来别重复什么

`hypothesis_output_format`
- 被谁读取：
  - `QlibFactorHypothesisGen.prepare_context`
  - `AlphaAgentHypothesisGen.prepare_context`
  - 通用 `components/proposal/__init__.py::LLMHypothesisGen.gen`
- 用在什么地方：hypothesis 生成阶段
- 职责：规定 hypothesis 阶段的 JSON schema，让后续 `convert_response()` 可以稳定解析

`factor_hypothesis_specification`
- 被谁读取：
  - `QlibFactorHypothesisGen.prepare_context`
  - `AlphaAgentHypothesisGen.prepare_context`
  - 通用 `components/proposal/__init__.py::LLMHypothesisGen.gen`
- 用在什么地方：hypothesis 生成阶段
- 职责：规定 hypothesis 的研究质量要求，比如可检验性、非结论化、避免未来信息、避免只换参数

`hypothesis_gen.system_prompt`
- 被谁读取：`quantaalpha/factors/proposal.py::AlphaAgentHypothesisGen.gen`
- 用在什么地方：AlphaAgent 主路径的 hypothesis 生成
- 职责：组织 hypothesis 生成阶段的 system prompt，并接入 `hypothesis_output_format` 与 `factor_hypothesis_specification`

`hypothesis_gen.user_prompt`
- 被谁读取：`quantaalpha/factors/proposal.py::AlphaAgentHypothesisGen.gen`
- 用在什么地方：AlphaAgent 主路径的 hypothesis 生成
- 职责：接入 `hypothesis_and_feedback` 和 `RAG` 等用户态上下文，形成真正发给 LLM 的 user prompt

#### factor expression 生成阶段

`function_lib_description`
- 被谁读取：`quantaalpha/factors/proposal.py::AlphaAgentHypothesis2FactorExpression.prepare_context`
- 用在什么地方：hypothesis -> factor expression 阶段
- 职责：告诉 LLM 当前 DSL 允许使用哪些变量、函数和语法，防止它生成 parser 不支持的表达式

`factor_experiment_output_format`
- 被谁读取：
  - `QlibFactorHypothesis2Experiment.prepare_context`
  - `AlphaAgentHypothesis2FactorExpression.prepare_context`
  - 通用 `components/proposal/__init__.py::LLMHypothesis2Experiment.convert`
- 用在什么地方：hypothesis -> factor expression 阶段
- 职责：规定因子生成阶段的 JSON schema，包括 `description`、`variables`、`formulation`、`expression`

`hypothesis2experiment.system_prompt`
- 被谁读取：`quantaalpha/factors/proposal.py::AlphaAgentHypothesis2FactorExpression._convert_with_history_limit`
- 用在什么地方：AlphaAgent 主路径的 hypothesis -> factor expressions
- 职责：定义这一阶段的 system prompt，并把 `factor_experiment_output_format` 注入进去

`hypothesis2experiment.user_prompt`
- 被谁读取：
  - `quantaalpha/factors/proposal.py::AlphaAgentHypothesis2FactorExpression._convert_with_history_limit`
  - 同文件中表达式重复后重新生成 user prompt 的逻辑
- 用在什么地方：AlphaAgent 主路径的 hypothesis -> factor expressions
- 职责：接入目标 hypothesis、历史记忆、函数库说明、表达式重复反馈，生成真正发给 LLM 的 user prompt

`expression_duplication`
- 被谁读取：`quantaalpha/factors/proposal.py::AlphaAgentHypothesis2FactorExpression._convert_with_history_limit`
- 用在什么地方：表达式被 `FactorRegulator` 判定为重复、过长、过度参数化或变量结构不佳时
- 职责：把这些质量问题渲染成一段反馈，再塞回 `hypothesis2experiment.user_prompt`，驱动下一次表达式重生成

#### feedback 阶段

`factor_feedback_generation.system`
- 被谁读取：`quantaalpha/factors/feedback.py`
- 用在什么地方：factor backtest 完成后的 feedback 生成
- 职责：告诉 LLM 如何比较 current result 和 SOTA result，如何给 hypothesis 反馈，以及何时建议替换 best result

`factor_feedback_generation.user`
- 被谁读取：`quantaalpha/factors/feedback.py`
- 用在什么地方：factor backtest 完成后的 feedback 生成
- 职责：把 hypothesis、factor details、combined_result、复杂度反馈等注入给 LLM，生成结构化 feedback

### D. `quantaalpha/factors/coder/prompts.yaml`

`evolving_strategy_factor_implementation_v1_system`
- 被谁读取：`quantaalpha/factors/coder/evolving_strategy.py::FactorMultiProcessEvolvingStrategy.implement_one_task`
- 用在什么地方：代码实现阶段，生成 `factor.py`
- 职责：定义 coder 的 system prompt，告诉模型要基于历史失败经验和参考实现输出可执行代码

`evolving_strategy_factor_implementation_v2_user`
- 被谁读取：`quantaalpha/factors/coder/evolving_strategy.py::FactorMultiProcessEvolvingStrategy.implement_one_task`
- 用在什么地方：代码实现阶段，生成 `factor.py`
- 职责：把目标因子描述、相似错误、成功示例、最近一次失败尝试注入给 LLM

`evolving_strategy_error_summary_v2_system`
- 被谁读取：`quantaalpha/factors/coder/evolving_strategy.py::FactorMultiProcessEvolvingStrategy.error_summary`
- 用在什么地方：代码报错后先做一轮 error summary
- 职责：告诉模型先总结关键错误，再把总结传回下一次代码生成

`evolving_strategy_error_summary_v2_user`
- 被谁读取：`quantaalpha/factors/coder/evolving_strategy.py::FactorMultiProcessEvolvingStrategy.error_summary`
- 用在什么地方：代码报错后的 error summary
- 职责：提供相似错误及其成功修正案例

`evaluator_output_format_system`
- 被谁读取：`quantaalpha/factors/coder/eva_utils.py::FactorOutputFormatEvaluator.evaluate`
- 用在什么地方：代码执行后，检查输出 dataframe 格式
- 职责：判断当前输出是否符合 evaluator 预期格式

`evaluator_final_decision_v1_system`
- 被谁读取：`quantaalpha/factors/coder/eva_utils.py`
- 用在什么地方：多种 evaluator 结果汇总后的最终判定
- 职责：基于代码反馈、值反馈和 ground truth 对比，给出最终 `final_decision`

`evaluator_final_decision_v1_user`
- 被谁读取：`quantaalpha/factors/coder/eva_utils.py`
- 用在什么地方：最终判定阶段
- 职责：把 factor information、execution feedback、code feedback、value feedback 注入给 LLM

### E. `quantaalpha/factors/coder/qa_prompts.yaml`

`evaluator_code_feedback_v1_system`
- 被谁读取：`quantaalpha/factors/coder/eva_utils.py::FactorCodeEvaluator.evaluate`
- 用在什么地方：表达式 / 代码失败后的 QA critic
- 职责：告诉模型如何针对表达式或代码实现问题给出简洁 critic

`evaluator_code_feedback_v1_user`
- 被谁读取：`quantaalpha/factors/coder/eva_utils.py::FactorCodeEvaluator.evaluate`
- 用在什么地方：表达式 / 代码失败后的 QA critic
- 职责：提供 factor information、当前模板代码、执行反馈、因子值反馈

`evolving_strategy_factor_implementation_v1_system`
- 被谁读取：`quantaalpha/factors/coder/evolving_strategy.py::FactorParsingStrategy.implement_one_task`
- 用在什么地方：表达式修复阶段
- 职责：告诉模型只输出修正后的 `expr`，并遵守 DSL 函数与语法白名单

`evolving_strategy_factor_implementation_v2_user`
- 被谁读取：`quantaalpha/factors/coder/evolving_strategy.py::FactorParsingStrategy.implement_one_task`
- 用在什么地方：表达式修复阶段
- 职责：提供旧 expression、旧 feedback、相似错误与相似成功案例，帮助模型修正式子

#### QA / Evaluator 执行分支说明

`FactorEvaluatorForCoder.evaluate(...)` 在拿到 `value_evaluator.evaluate(...)` 的返回值后，并不会总是把 QA / evaluator 的 prompt 全跑一遍，而是按 `decision_from_value_check` 分三条支路：

1. `decision_from_value_check = True`
- 含义：值检查已经明确通过，通常是与 ground truth 几乎逐点一致，或相关性极高。
- 后续：直接通过。
- 不会调用：`evaluator_code_feedback_v1_system`、`evaluator_code_feedback_v1_user`、`evaluator_final_decision_v1_system`、`evaluator_final_decision_v1_user`。

2. `decision_from_value_check = False`
- 含义：值检查已经明确失败，例如行数、缺失值模式、日频性、`inf` 或 GT 对齐明显有问题。
- 后续：会调用 `evaluator_code_feedback_v1_system` + `evaluator_code_feedback_v1_user` 生成 code critic，然后直接判失败。
- 不会调用：`evaluator_final_decision_v1_system`、`evaluator_final_decision_v1_user`。

3. `decision_from_value_check = None`
- 含义：值检查无法直接判通过或失败，处于灰区。
- 后续：先调用 `evaluator_code_feedback_v1_system` + `evaluator_code_feedback_v1_user` 生成 code critic；再调用 `evaluator_final_decision_v1_system` + `evaluator_final_decision_v1_user` 做最终综合裁决。

最简分支图：

```text
value_evaluator.evaluate(...)
        |
        |-- True
        |     -> 直接通过
        |     -> 不跑 code_evaluator
        |     -> 不跑 final_decision_evaluator
        |
        |-- False
        |     -> 跑 code_evaluator
        |     -> 直接失败
        |     -> 不跑 final_decision_evaluator
        |
        |-- None
              -> 跑 code_evaluator
              -> 再跑 final_decision_evaluator
              -> 由 final_decision 给最终结果
```

## 六、全流程图

下面这张图把当前保留 key 的主流程串起来。可以把它理解成：

- 上层：`planning` 负责扩展研究方向
- 中层：`hypothesis` 负责把方向变成可检验研究假设
- 下层：`hypothesis2experiment` 负责把假设变成具体因子表达式
- 后续：`coder / evaluator / feedback / evolution` 负责实现、评估、总结和派生新分支

```mermaid
flowchart TD
    A[用户输入 initial_direction] --> B[planning.system + planning.user]
    B --> C[planning.output_format<br/>输出 directions JSON]

    C --> D[每个 direction 进入 AlphaAgentLoop]

    D --> E{trace.hist 是否为空?}
    E -- 是且有 potential_direction --> F[potential_direction_transformation<br/>首轮方向改写]
    E -- 否 --> G[hypothesis_and_feedback<br/>历史研究记忆]

    F --> H[hypothesis_gen.system_prompt]
    G --> H
    H --> I[hypothesis_output_format<br/>规定 hypothesis JSON]
    H --> J[factor_hypothesis_specification<br/>约束 hypothesis 质量]
    I --> K[生成 hypothesis]
    J --> K

    K --> L[hypothesis2experiment.system_prompt]
    G --> M[hypothesis2experiment.user_prompt]
    L --> N[factor_experiment_output_format<br/>规定 factor JSON]
    M --> O[function_lib_description<br/>限定 DSL]
    N --> P[生成 factors JSON]
    O --> P

    P --> Q{FactorRegulator 通过?}
    Q -- 否 --> R[expression_duplication<br/>渲染重复/复杂度反馈]
    R --> M
    Q -- 是 --> S[得到 FactorTask 列表]

    S --> T[coder prompts<br/>生成 factor.py]
    T --> U[qa_prompts / evaluator_output_format_system / evaluator_final_decision]
    U --> V[runner backtest]
    V --> W[factor_feedback_generation.system + user]
    W --> X[生成 structured feedback]
    X --> Y[trace.hist 追加记录]

    Y --> Z{是否启用 evolution?}
    Z -- 否 --> G
    Z -- 是 --> AA[mutation / crossover prompts]

    AA --> AB[mutation.user 或 crossover.user<br/>生成新方向 brief]
    AB --> AC[suffix_template<br/>包装为 strategy_suffix]
    AC --> AD[拼到 effective_direction]
    AD --> H
```

## 七、最简职责总结

如果只想记最核心的一层，可以记下面这组映射：

- `potential_direction_transformation`
  第一轮把用户方向改写成可用的 hypothesis 上下文

- `hypothesis_and_feedback`
  把历史研究轨迹整理成后续轮次的文本记忆

- `hypothesis_output_format`
  规定 hypothesis 阶段输出长什么样

- `factor_hypothesis_specification`
  规定 hypothesis 内容要满足什么研究标准

- `function_lib_description`
  规定表达式里允许用什么 DSL

- `factor_experiment_output_format`
  规定 factor 生成阶段的 JSON 交付结构

- `expression_duplication`
  表达式质量不过关时，驱动下一轮重生成

- `factor_feedback_generation.*`
  回测后生成 hypothesis 反馈并决定是否替换当前 best result

- `mutation.*` / `crossover.*`
  基于父轨迹生成新的 branch 方向，再以 `strategy_suffix` 形式送回主 loop
