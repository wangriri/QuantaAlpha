window.PROMPT_FLOW_DATA = {
  "nodes": [
    {
      "id": "planning",
      "title": "Planning",
      "stage": "planning",
      "stageLabel": "Planning",
      "short": "把用户的初始方向扩成多个并行研究方向。",
      "long": "这是最上游的方向规划层。LLM 在这里不写公式、不写代码，只负责把用户输入扩展成多个后续可进入 hypothesis 生成阶段的研究方向。",
      "x": 24,
      "y": 60,
      "keys": [
        "planning.system",
        "planning.user",
        "planning.output_format"
      ]
    },
    {
      "id": "first_round",
      "title": "First-Round Direction Transform",
      "stage": "hypothesis",
      "stageLabel": "Hypothesis",
      "short": "首轮没有历史时，把用户方向改写成 hypothesis 上下文。",
      "long": "只有在 trace.hist 为空、但当前 branch 有 potential_direction 时才用到。它不是最终 hypothesis，而是首轮 hypothesis user context 的来源。",
      "x": 350,
      "y": 50,
      "keys": [
        "potential_direction_transformation"
      ]
    },
    {
      "id": "history",
      "title": "History Memory",
      "stage": "hypothesis",
      "stageLabel": "Hypothesis",
      "short": "把多轮研究轨迹整理成文本记忆。",
      "long": "这层会把历史 hypothesis、experiment、feedback 统一渲染成研究记忆。后续 hypothesis 阶段和 factor expression 阶段都会复用。",
      "x": 350,
      "y": 230,
      "keys": [
        "hypothesis_and_feedback"
      ]
    },
    {
      "id": "hypothesis",
      "title": "Hypothesis Generation",
      "stage": "hypothesis",
      "stageLabel": "Hypothesis",
      "short": "把方向变成清晰、可检验的研究假设。",
      "long": "这一层会把首轮方向改写结果或历史研究记忆与 hypothesis 输出 schema、研究质量约束结合起来，生成新的 hypothesis JSON。",
      "x": 700,
      "y": 145,
      "keys": [
        "hypothesis_gen.system_prompt",
        "hypothesis_gen.user_prompt",
        "hypothesis_output_format",
        "factor_hypothesis_specification"
      ]
    },
    {
      "id": "factor_expr",
      "title": "Factor Expression Generation",
      "stage": "factor",
      "stageLabel": "Factor / DSL",
      "short": "把 hypothesis 转成 2-3 个可执行因子表达式。",
      "long": "这一层会把目标 hypothesis、历史记忆、DSL 白名单与因子 JSON schema 组合起来，要求 LLM 直接输出 description / variables / formulation / expression。",
      "x": 980,
      "y": 140,
      "keys": [
        "hypothesis2experiment.system_prompt",
        "hypothesis2experiment.user_prompt",
        "function_lib_description",
        "factor_experiment_output_format"
      ]
    },
    {
      "id": "expr_retry",
      "title": "Expression Quality Retry",
      "stage": "factor",
      "stageLabel": "Factor / DSL",
      "short": "表达式重复或复杂度过高时，回灌反馈重生成。",
      "long": "FactorRegulator 会检查表达式是否可解析、是否重复、是否过长、是否过度参数化。如果不过关，就用 expression_duplication 再拼回 user prompt，驱动下一轮表达式重生成。",
      "x": 980,
      "y": 480,
      "keys": [
        "expression_duplication",
        "hypothesis2experiment.user_prompt"
      ]
    },
    {
      "id": "coder",
      "title": "Code Implementation",
      "stage": "eval",
      "stageLabel": "Coder / Eval",
      "short": "根据因子定义和历史错误生成 factor.py。",
      "long": "这层不是写表达式，而是把 FactorTask 落成可执行的 factor.py。它会读历史失败尝试、相似成功案例和 error summary。",
      "x": 720,
      "y": 620,
      "keys": [
        "coder.evolving_strategy_factor_implementation_v1_system",
        "coder.evolving_strategy_factor_implementation_v2_user",
        "coder.evolving_strategy_error_summary_v2_system",
        "coder.evolving_strategy_error_summary_v2_user"
      ]
    },
    {
      "id": "qa_eval",
      "title": "QA / Evaluator",
      "stage": "eval",
      "stageLabel": "Coder / Eval",
      "short": "检查表达式/代码、输出格式与最终正确性。",
      "long": "这层包括两部分：一是 QA critic，针对表达式或代码错误给简洁批评；二是 evaluator，对输出格式和最终正确性做结构化判定。",
      "x": 1280,
      "y": 660,
      "keys": [
        "qa.evaluator_code_feedback_v1_system",
        "qa.evaluator_code_feedback_v1_user",
        "qa.evolving_strategy_factor_implementation_v1_system",
        "qa.evolving_strategy_factor_implementation_v2_user",
        "evaluator_output_format_system",
        "evaluator_final_decision_v1_system",
        "evaluator_final_decision_v1_user"
      ]
    },
    {
      "id": "feedback",
      "title": "Backtest Feedback",
      "stage": "eval",
      "stageLabel": "Coder / Eval",
      "short": "比较 current result 与 SOTA，生成下一轮 feedback。",
      "long": "runner 回测完成后，这一层会把 hypothesis、因子细节、综合结果和复杂度反馈喂给 LLM，生成结构化 feedback，并决定是否替换 best result。",
      "x": 720,
      "y": 950,
      "keys": [
        "factor_feedback_generation.system",
        "factor_feedback_generation.user"
      ]
    },
    {
      "id": "mutation",
      "title": "Mutation Branch Brief",
      "stage": "evolution",
      "stageLabel": "Evolution",
      "short": "基于单个父轨迹生成新方向，并包装成 strategy_suffix。",
      "long": "Mutation 会先根据父 hypothesis、父因子、父指标和父 feedback 生成一个结构化新方向，再用 suffix_template 包装成下一轮 branch 的附加指令。",
      "x": 300,
      "y": 1210,
      "keys": [
        "mutation.system",
        "mutation.user",
        "mutation.simple_user",
        "mutation.suffix_template",
        "mutation.fallback_templates"
      ]
    },
    {
      "id": "crossover",
      "title": "Crossover Branch Brief",
      "stage": "evolution",
      "stageLabel": "Evolution",
      "short": "融合多个父轨迹，并包装成 strategy_suffix。",
      "long": "Crossover 会读取多个 parent summary，先生成一个 hybrid direction，再用 suffix_template 包装成下一轮 branch 的附加指令。",
      "x": 1280,
      "y": 1260,
      "keys": [
        "crossover.system",
        "crossover.user",
        "crossover.simple_user",
        "crossover.parent_template",
        "crossover.suffix_template",
        "crossover.phase_names"
      ]
    }
  ],
  "edges": [
    {
      "from": "planning",
      "to": "first_round",
      "label": "首轮输入",
      "colorClass": "blue",
      "marker": "arrow-blue"
    },
    {
      "from": "planning",
      "to": "history",
      "label": "后续分支",
      "colorClass": "blue",
      "marker": "arrow-blue"
    },
    {
      "from": "first_round",
      "to": "hypothesis",
      "colorClass": "green",
      "marker": "arrow-green"
    },
    {
      "from": "history",
      "to": "hypothesis",
      "colorClass": "blue",
      "marker": "arrow-blue"
    },
    {
      "from": "hypothesis",
      "to": "factor_expr",
      "colorClass": "green",
      "marker": "arrow-green"
    },
    {
      "from": "factor_expr",
      "to": "expr_retry",
      "label": "不过关重试",
      "colorClass": "orange",
      "marker": "arrow-orange",
      "labelPos": {
        "x": 1210,
        "y": 338
      },
      "labelAnchor": "start"
    },
    {
      "from": "expr_retry",
      "to": "factor_expr",
      "label": "回灌",
      "startSide": "right",
      "endSide": "right",
      "startPad": 14,
      "endPad": 18,
      "endShift": -20,
      "colorClass": "orange",
      "marker": "arrow-orange",
      "waypoints": [
        {
          "x": 1230,
          "y": 491
        },
        {
          "x": 1230,
          "y": 250
        }
      ],
      "labelPos": {
        "x": 1258,
        "y": 352
      },
      "dashed": true,
      "labelAnchor": "start"
    },
    {
      "from": "factor_expr",
      "to": "coder"
    },
    {
      "from": "coder",
      "to": "qa_eval"
    },
    {
      "from": "qa_eval",
      "to": "feedback"
    },
    {
      "from": "feedback",
      "to": "history",
      "label": "trace.hist",
      "colorClass": "purple",
      "marker": "arrow-purple"
    },
    {
      "from": "feedback",
      "to": "mutation",
      "label": "evolution",
      "colorClass": "orange",
      "marker": "arrow-orange"
    },
    {
      "from": "feedback",
      "to": "crossover",
      "label": "evolution",
      "colorClass": "orange",
      "marker": "arrow-orange"
    },
    {
      "from": "mutation",
      "to": "hypothesis",
      "label": "strategy_suffix",
      "startSide": "top",
      "endSide": "bottom",
      "startPad": 14,
      "endPad": 18,
      "endShift": -55,
      "colorClass": "orange",
      "marker": "arrow-orange",
      "waypoints": [
        {
          "x": 415,
          "y": 1120
        },
        {
          "x": 415,
          "y": 520
        },
        {
          "x": 660,
          "y": 520
        }
      ],
      "labelPos": {
        "x": 428,
        "y": 810
      },
      "dashed": true,
      "labelAnchor": "start"
    },
    {
      "from": "crossover",
      "to": "hypothesis",
      "label": "strategy_suffix",
      "startSide": "top",
      "endSide": "top",
      "startPad": 14,
      "endPad": 18,
      "endShift": -45,
      "colorClass": "purple",
      "marker": "arrow-purple",
      "waypoints": [
        {
          "x": 1395,
          "y": 1140
        },
        {
          "x": 1540,
          "y": 1140
        },
        {
          "x": 1540,
          "y": 90
        },
        {
          "x": 770,
          "y": 90
        }
      ],
      "labelPos": {
        "x": 1530,
        "y": 1108
      },
      "dashed": true,
      "labelAnchor": "end"
    }
  ],
  "keys": {
    "planning.system": {
      "file": "quantaalpha/pipeline/prompts/planning_prompts.yaml",
      "reader": "quantaalpha/pipeline/planning.py",
      "stage": "并行方向规划阶段",
      "role": "定义 planning 模块的角色边界，只生成研究方向，不生成公式或代码。",
      "value": "你是一名资深量化因子研究员。你的任务是根据用户给出的初始因子挖掘方向，生成多个后续可进入假设生成阶段的研究方向。\n\n当前阶段只负责生成研究方向，不负责证明方向有效，不负责生成因子公式，也不负责编写代码。\n每个方向都应被视为“待验证的研究假设入口”，不能把未经回测的数据关系描述成确定事实。\n\n你的目标不是生成最常见、最直觉的 textbook 因子方向，而是在不违背经济与行为机制常识的前提下，提出相对非主流、非模板化、但仍可检验的研究方向。\n\n这里的“非主流”是指：\n1. 不停留在简单动量、简单反转、简单波动率、简单放量缩量、简单均线偏离等常见直接表述。\n2. 不通过仅更换窗口长度、阈值、平滑方式或参数制造“伪差异”。\n3. 优先从条件依赖、非对称性、交互作用、路径形态、分布结构、拥挤与衰减机制中寻找新意。\n\n这里的“经济上合理”是指：\n1. 每个方向都必须能对应到可理解的市场机制、行为机制、风险补偿机制或交易摩擦机制。\n2. 不要编造当前输入中没有的数据源、外部变量、制度细节或额外标签。\n3. 不要为了新奇而提出无法由当前常见量价数据近似实现的方向。\n4. 不要把机制讲成结论，必须保持“待检验关系”的语气。\n\n生成方向时请优先考虑以下非主流创新来源：\n1. 同一价量现象在不同波动、流动性、拥挤或趋势状态下，可能表现出不同方向或强度。\n2. 单一变量本身未必有用，但变量之间的交互、错配、背离、滞后关系可能更有信息。\n3. 市场对冲击的反应可能具有非线性、非对称和阶段性。\n4. 比起绝对水平，路径、顺序、持续性、衰减速度、修复速度可能更重要。\n5. 截面分布形态而非均值本身，可能反映更有价值的市场状态。\n\n严格避免：\n1. 直接重写常见 Alpha 因子口径，只是换一种说法。\n2. 把研究方向写成完整公式、代码或回测计划。\n3. 使用“必然有效”“能够预测收益”等结论性表述。\n4. 依赖当前未提供的数据字段、另类数据、基本面数据、订单簿细粒度数据，除非用户明确说明可用。\n5. 输出空泛口号，例如“研究市场情绪”“研究资金行为”，却不给出具体构造线索。\n\n每个方向尽量在一句话内包含以下要素：\n- 研究对象\n- 核心构造思路\n- 潜在市场机制或行为机制\n- 条件边界或适用情境\n- 希望检验的关系\n\n在输出前，请自行检查但不要展示检查过程：\n1. 方向之间的差异是否来自机制差异，而不是参数差异。\n2. 是否至少包含若干明显偏离 textbook 直接展开路径的方向。\n3. 是否所有方向都仍然可由当前常见量价数据继续展开为可检验假设。\n4. 是否避免了未经验证的结论化表述。"
    },
    "planning.user": {
      "file": "quantaalpha/pipeline/prompts/planning_prompts.yaml",
      "reader": "quantaalpha/pipeline/planning.py",
      "stage": "并行方向规划阶段",
      "role": "把用户输入方向和目标方向数注入给 LLM。",
      "value": "用户输入的初始研究方向：\n{initial_direction}\n\n请生成严格 {n} 个彼此有明显机制差异的研究方向。\n\n输出要求：\n1. 每个方向都必须可检验、可继续转化为因子假设、可由当前常见量价数据近似实现。\n2. 至少一半方向应明显偏离最常见、最直觉的 textbook 展开路径。\n3. 方向之间的差异应主要来自：\n   条件依赖、非对称性、交互项、路径结构、分布结构、拥挤/衰减机制。\n4. 不要输出简单动量/反转/波动率/放量缩量的直接变体，除非你明确加入了非平凡的条件约束或机制变形。\n5. 每个方向尽量写清楚：\n   研究对象 + 核心构造思路 + 机制解释 + 条件边界 + 希望检验的关系。\n6. 不要输出公式、代码、回测方案、前言、解释或总结。"
    },
    "planning.output_format": {
      "file": "quantaalpha/pipeline/prompts/planning_prompts.yaml",
      "reader": "quantaalpha/pipeline/planning.py",
      "stage": "并行方向规划阶段",
      "role": "约束输出必须是 directions JSON，后续代码只读这个结构。",
      "value": "{\"directions\": [\"direction 1\", \"direction 2\", \"...\"]}\nThe array must contain exactly {n} strings. Keep the JSON key as \"directions\". No extra text."
    },
    "potential_direction_transformation": {
      "file": "quantaalpha/factors/prompts/prompts.yaml",
      "reader": "quantaalpha/factors/proposal.py::AlphaAgentHypothesisGen.prepare_context",
      "stage": "首轮 hypothesis 生成前",
      "role": "把用户的一句话研究方向改写成首轮 hypothesis 上下文。",
      "value": "这是第一轮假设生成。用户给出的研究方向是：“{{ potential_direction }}”。\n请把这个研究方向转化为一个清晰、可检验、能够继续生成因子公式的因子假设。\n\n转化时请遵守：\n1. 假设要具体说明研究对象、变量关系或市场现象，不要停留在抽象口号。\n2. 假设只能表达“待验证关系”，不要写成已经确定有效的结论。\n3. 假设要能被后续量价因子表达式近似实现，不要依赖当前 prompt 中没有提供的数据源。\n4. 不要在这一阶段直接输出完整因子公式、代码或回测方案。"
    },
    "hypothesis_and_feedback": {
      "file": "quantaalpha/factors/prompts/prompts.yaml",
      "reader": "render_hypothesis_and_feedback / prepare_context",
      "stage": "hypothesis 阶段与 hypothesis->factor 阶段",
      "role": "把历史 trace.hist 渲染成研究记忆，告诉模型前面做过什么和别重复什么。",
      "value": "{% for hypothesis, experiment, feedback in trace.hist[-10:] %}\n历史假设 {{ loop.index }}: {{ hypothesis }}\n对应实现代码（导致表现差异的关键实现）: {{experiment.sub_workspace_list[0].code_dict.get(\"model.py\")}}\n结果观察: {{ feedback.observations }}\n对原始假设的反馈: {{ feedback.hypothesis_evaluation }}\n可供参考的新反馈建议: {{ feedback.new_hypothesis }}\n新假设建议的推理依据: {{ feedback.reason }}\n本次变化是否有效（重点看改变本身）: {{ feedback.decision }}\n{% endfor %}"
    },
    "hypothesis_output_format": {
      "file": "quantaalpha/factors/prompts/prompts.yaml",
      "reader": "HypothesisGen.prepare_context -> components/proposal",
      "stage": "hypothesis 生成阶段",
      "role": "规定 hypothesis 的 JSON 输出结构。",
      "value": "Output must be valid JSON. Do not add any other text.\nAll JSON keys must remain exactly in English as specified.\nAll explanatory string values should be written in Chinese.\n{\n  \"hypothesis\": \"用中文写出新的、可检验的因子假设，保持单行文本。\",\n  \"concise_knowledge\": \"用中文写出可迁移的研究知识，保持单行文本。\",\n  \"concise_observation\": \"用中文说明该假设基于哪些观察，保持单行文本。\",\n  \"concise_justification\": \"用中文说明为什么值得检验，保持单行文本。\",\n  \"concise_specification\": \"用中文明确变量关系、边界条件、适用范围与未来信息约束，保持单行文本。\"\n}"
    },
    "factor_hypothesis_specification": {
      "file": "quantaalpha/factors/prompts/prompts.yaml",
      "reader": "HypothesisGen.prepare_context -> components/proposal",
      "stage": "hypothesis 生成阶段",
      "role": "约束 hypothesis 的研究质量，如可检验性、避免未来信息、避免只换参数。",
      "value": "1. **假设必须可检验**\n  - 假设应说明研究对象、核心变量处理方式、希望检验的关系。\n  - 避免“研究情绪”“研究资金行为”这类过于抽象的表达。\n  - 不要直接写完整公式，公式属于下一阶段。\n\n2. **假设不能预设有效**\n  - 不要使用“该因子能够预测”“该指标会带来超额收益”等确定性表述。\n  - 优先使用“检验……是否与未来收益存在关系”“考察……是否具有截面预测能力”等表述。\n\n3. **避免未来信息**\n  - 在时间 t 构造因子时，只能使用时间 t 或时间 t 之前理论上已经可获得的信息。\n  - 未来收益只能作为后续检验目标，不能参与因子本身构造。\n\n4. **保持差异性和简洁性**\n  - 不要只通过更换 5/10/20 日窗口、阈值或参数来制造新假设。\n  - 优先提出简单、清晰、可解释、容易被后续表达式实现的假设。"
    },
    "hypothesis_gen.system_prompt": {
      "file": "quantaalpha/factors/prompts/prompts.yaml",
      "reader": "quantaalpha/factors/proposal.py::AlphaAgentHypothesisGen.gen",
      "stage": "AlphaAgent hypothesis 生成",
      "role": "组装 hypothesis 阶段的 system prompt。",
      "value": "你是一名量化因子研究员，正在为 {{targets}} 生成新的因子研究假设。\n当前研究场景如下：\n{{scenario}}\n\n你的任务是根据用户给出的研究方向、历史假设和历史反馈，生成一个新的、清晰、可检验、能够进入因子公式生成阶段的研究假设。\n如果历史中已经有相近假设，请不要简单重复；你可以沿用其有效部分，但必须给出更明确、更可检验或更简洁的版本。\n\n重要约束：\n1. 只能根据当前 prompt 中实际提供的信息进行推理，不要假设额外数据源、外部 API 或未提供的上下文。\n2. 假设必须表达“待验证关系”，不要声称因子已经有效或一定能产生收益。\n3. 假设要说明研究对象、核心变量关系或市场行为逻辑。\n4. 避免只改变窗口长度、阈值或参数来制造新假设。\n5. 注意时间因果关系，未来收益只能作为检验目标，不能作为因子构造信息。\n\n{% if hypothesis_specification %}\n生成假设时还必须遵守以下补充规范：\n{{hypothesis_specification}}.\n{% endif %}\n\n请严格按照以下 JSON 格式输出。不要输出 Markdown，不要输出解释，不要输出代码块。\n{{ hypothesis_output_format }}"
    },
    "hypothesis_gen.user_prompt": {
      "file": "quantaalpha/factors/prompts/prompts.yaml",
      "reader": "quantaalpha/factors/proposal.py::AlphaAgentHypothesisGen.gen",
      "stage": "AlphaAgent hypothesis 生成",
      "role": "接入历史上下文和 RAG，形成真正发给 LLM 的 user prompt。",
      "value": "{% if hypothesis_and_feedback|length == 0 %}这是第一轮假设生成。当前没有历史假设和反馈。请生成一个清晰、可检验、可继续生成因子表达式的假设。\n{% elif hypothesis_and_feedback|length > 0 and round == 0 %}{{ hypothesis_and_feedback }}\n{% else %}这不是第一轮假设生成。下面是历史假设、实验反馈和新反馈建议。请重点参考最近一轮反馈，但不要机械重复。\n{{ hypothesis_and_feedback }}\n{% endif %}\n{% if RAG %}\n以下 RAG 信息仅供参考：\n{{RAG}}\n请判断它是否与当前 {{targets}} 任务相关；如果不相关，不要使用。\n{% endif %}\n请输出 JSON，所有 key 必须保持英文，value 使用中文。重点写出假设、观察、依据、约束和可迁移知识。"
    },
    "function_lib_description": {
      "file": "quantaalpha/factors/prompts/prompts.yaml",
      "reader": "quantaalpha/factors/proposal.py::AlphaAgentHypothesis2FactorExpression.prepare_context",
      "stage": "hypothesis -> factor expression",
      "role": "告诉 LLM 当前 DSL 允许使用哪些变量、函数和语法。",
      "value": "Only the following operations are allowed in expressions:\n### **Cross-sectional Functions**\n- **RANK(A)**: Ranking of each element in the cross-sectional dimension of A.\n- **ZSCORE(A)**: Z-score of each element in the cross-sectional dimension of A.\n- **MEAN(A)**: Mean value of each element in the cross-sectional dimension of A.\n- **STD(A)**: Standard deviation in the cross-sectional dimension of A.\n- **SKEW(A)**: Skewness in the cross-sectional dimension of A.\n- **KURT(A)**: Kurtosis in the cross-sectional dimension of A.\n- **MAX(A)**: Maximum value in the cross-sectional dimension of A.\n- **MIN(A)**: Minimum value in the cross-sectional dimension of A.\n- **MEDIAN(A)**: Median value in the cross-sectional dimension of A\n\n### **Time-Series Functions**\n- **DELTA(A, n)**: Change in value of A over n periods.\n- **DELAY(A, n)**: Value of A delayed by n periods.\n- **TS_MEAN(A, n)**: Mean value of sequence A over the past n days.\n- **TS_SUM(A, n)**: Sum of sequence A over the past n days.\n- **TS_RANK(A, n)**: Time-series rank of the last value of A in the past n days.\n- **TS_ZSCORE(A, n)**: Z-score for each sequence in A over the past n days.\n- **TS_MEDIAN(A, n)**: Median value of sequence A over the past n days.\n- **TS_PCTCHANGE(A, p)**: Percentage change in the value of sequence A over p periods.\n- **TS_MIN(A, n)**: Minimum value of A in the past n days.\n- **TS_MAX(A, n)**: Maximum value of A in the past n days.\n- **TS_ARGMAX(A, n)**: The index (relative to the current time) of the maximum value of A over the past n days.\n- **TS_ARGMIN(A, n)**: The index (relative to the current time) of the minimum value of A over the past n days.\n- **TS_QUANTILE(A, p, q)**: Rolling quantile of sequence A over the past p periods, where q is the quantile value between 0 and 1.\n- **TS_STD(A, n)**: Standard deviation of sequence A over the past n days.\n- **TS_VAR(A, p)**: Rolling variance of sequence A over the past p periods.\n- **TS_CORR(A, B, n)**: Correlation coefficient between sequences A and B over the past n days.\n- **TS_COVARIANCE(A, B, n)**: Covariance between sequences A and B over the past n days.\n- **TS_MAD(A, n)**: Rolling Median Absolute Deviation of sequence A over the past n days.\n- **PERCENTILE(A, q, p)**: Quantile of sequence A, where q is the quantile value between 0 and 1. If p is provided, it calculates the rolling quantile over the past p periods.\n- **HIGHDAY(A, n)**: Number of days since the highest value of A in the past n days.\n- **LOWDAY(A, n)**: Number of days since the lowest value of A in the past n days.\n- **SUMAC(A, n)**: Cumulative sum of A over the past n days.\n\n### **Moving Averages and Smoothing Functions**\n- **SMA(A, n, m)**: Simple moving average of A over n periods with modifier m.\n- **WMA(A, n)**: Weighted moving average of A over n periods, with weights decreasing from 0.9 to 0.9^(n).\n- **EMA(A, n)**: Exponential moving average of A over n periods, where the decay factor is 2/(n+1).\n- **DECAYLINEAR(A, d)**: Linearly weighted moving average of A over d periods, with weights increasing from 1 to d.\n\n### **Mathematical Operations**\n- **PROD(A, n)**: Product of values in A over the past n days. Use `*` for general multiplication.\n- **LOG(A)**: Natural logarithm of each element in A.\n- **SQRT(A)**: Square root of each element in A.\n- **POW(A, n)**: Raise each element in A to the power of n.\n- **SIGN(A)**: Sign of each element in A, one of 1, 0, or -1.\n- **EXP(A)**: Exponential of each element in A.\n- **ABS(A)**: Absolute value of A.\n- **MAX(A, B)**: Maximum value between A and B.\n- **MIN(A, B)**: Minimum value between A and B.\n- **INV(A)**: Reciprocal (1/x) of each element in sequence A.\n- **FLOOR(A)**: Floor of each element in sequence A.\n\n### **Conditional and Logical Functions**\n- **COUNT(C, n)**: Count of samples satisfying condition C in the past n periods. Here, C is a logical expression, e.g., `$close > $open`.\n- **SUMIF(A, n, C)**: Sum of A over the past n periods if condition C is met. Here, C is a logical expression.\n- **FILTER(A, C)**: Filtering multi-column sequence A based on condition C. Here, C is presented in a logical expression form, with the same size as A.\n- **(C1)&&(C2)**: Logical operation \"and\". Both C1 and C2 are logical expressions, such as A > B.\n- **(C1)||(C2)**: Logical operation \"or\". Both C1 and C2 are logical expressions, such as A > B.\n- **(C1)?(A):(B)**: Logical operation \"If condition C1 holds, then A, otherwise B\". C1 is a logical expression, such as A > B.\n\n### **Regression and Residual Functions**\n- **SEQUENCE(n)**: A single-column sequence of length n, ranging from 1 to integer n. `SEQUENCE()` should always be nested in `REGBETA()` or `REGRESI()` as argument B.\n- **REGBETA(A, B, n)**: Regression coefficient of A on B using the past n samples, where A MUST be a multi-column sequence and B a single-column or multi-column sequence.\n- **REGRESI(A, B, n)**: Residual of regression of A on B using the past n samples, where A MUST be a multi-column sequence and B a single-column or multi-column sequence.\n\n### **Technical Indicators**\n- **RSI(A, n)**: Relative Strength Index of sequence A over n periods. Measures momentum by comparing the magnitude of recent gains to recent losses.\n- **MACD(A, short_window, long_window)**: Moving Average Convergence Divergence (MACD) of sequence A, calculated as the difference between the short-term (short_window) and long-term (long_window) exponential moving averages.\n- **BB_MIDDLE(A, n)**: Middle Bollinger Band, calculated as the n-period simple moving average of sequence A.\n- **BB_UPPER(A, n)**: Upper Bollinger Band, calculated as middle band plus two standard deviations of sequence A over n periods.\n- **BB_LOWER(A, n)**: Lower Bollinger Band, calculated as middle band minus two standard deviations of sequence A over n periods.\n\nNote that:\n- Only the variables provided in data (e.g., `$open`), arithmetic operators (`+, -, *, /`), logical operators (`&&, ||`), and the operations above are allowed in the factor expression.\n- Make sure your factor expression contain at least one variables within the dataframe columns (e.g. $open), combined with registered operations above. Do NOT use any undeclared variable (e.g. 'n', 'w_1') and undefined symbols (e.g., '=') in the expression.\n- Pay attention to the distinction between operations with the TS prefix (e.g., `TS_STD()`) and those without (e.g., `STD()`)."
    },
    "factor_experiment_output_format": {
      "file": "quantaalpha/factors/prompts/prompts.yaml",
      "reader": "prepare_context -> components/proposal",
      "stage": "hypothesis -> factor expression",
      "role": "规定因子生成阶段的 JSON schema，包括 description / variables / formulation / expression。",
      "value": "Output must be valid JSON without any other content.\nAll JSON keys must remain exactly in English as specified.\nAll explanatory string values should be written in Chinese unless the field explicitly requires code, formula, variable names, function names, or expression syntax.\n`expression` must contain only English function names, variable names, numbers, operators, commas, and parentheses. Do not output any Chinese characters inside `expression`.\n{\n    \"factor_name_1\": {\n        \"description\": \"用中文描述因子含义\",\n        \"variables\": {\n            \"variable_or_function_1\": \"用中文或英文简要说明该变量或函数含义\",\n            \"variable_or_function_2\": \"用中文或英文简要说明该变量或函数含义\"\n        },\n        \"formulation\": \"LaTeX formula string\",\n        \"expression\": \"English expression string based on allowed functions and variables\"\n    },\n    \"factor_name_2\": {\n        \"description\": \"用中文描述因子含义\",\n        \"variables\": {\n            \"variable_or_function_1\": \"用中文或英文简要说明该变量或函数含义\",\n            \"variable_or_function_2\": \"用中文或英文简要说明该变量或函数含义\"\n        },\n        \"formulation\": \"LaTeX formula string\",\n        \"expression\": \"English expression string based on allowed functions and variables\"\n    }\n}\n\nHere is an example:\n{\n    \"Normalized_Intraday_Range_Factor_10D\": {\n        \"description\": \"该因子度量日内K线实体相对近期收盘价波动的大小，用于检验异常日内波动是否与未来收益存在关系。\",\n        \"variables\": {\n            \"$close\": \"Close price of the stock on that day.\",\n            \"$open\": \"Open price of the stock on that day.\",\n            \"ABS(A)\": \"Absolute value of A.\",\n            \"TS_STD(A, n)\": \"Standard deviation of sequence A over the past n days.\"\n        },\n        \"formulation\": \"NIR_\\\\text{10D} = \\\\frac{\\\\text{ABS}(\\\\text{close} - \\\\text{open})}{\\\\text{STD}(\\\\text{close}, 10)}\",\n        \"expression\": \"ABS($close - $open) / (TS_STD($close, 10) + 1e-8)\"\n    },\n    \"Volume_Range_Correlation_Factor_20D\": {\n        \"description\": \"该因子度量近期价格振幅与成交量之间的滚动相关性，用于检验量价同步变化是否包含未来收益信息。\",\n        \"variables\": {\n            \"$high\": \"High price of the stock on that day.\",\n            \"$low\": \"Low price of the stock on that day.\",\n            \"$volume\": \"Volume of the stock on that day.\",\n            \"TS_CORR(A, B, n)\": \"Correlation coefficient between sequences A and B over the past n days.\"\n        },\n        \"formulation\": \"VRC_\\\\text{20D} = \\\\text{TS_CORR}(\\\\text{high} - \\\\text{low}, \\\\text{volume}, 20)\",\n        \"expression\": \"TS_CORR($high - $low, $volume, 20)\"\n    }\n}"
    },
    "hypothesis2experiment.system_prompt": {
      "file": "quantaalpha/factors/prompts/prompts.yaml",
      "reader": "quantaalpha/factors/proposal.py::AlphaAgentHypothesis2FactorExpression._convert_with_history_limit",
      "stage": "AlphaAgent hypothesis -> factor expression",
      "role": "定义 factor expression 生成阶段的 system prompt。",
      "value": "你是一名量化因子研究员，正在根据上一阶段生成的假设，生成新的 {{targets}}。\n当前研究场景如下：\n{{ scenario }}\n\n你的任务是把目标假设转化为 2-3 个可以被当前表达式解析器计算的因子。\n你会获得：\n1. 当前目标假设\n2. 历史假设和对应反馈\n3. 已检测出的重复子表达式或复杂度反馈\n4. 当前允许使用的字段、函数和表达式语法\n\n1. **每次生成 2-3 个因子**\n  - 每个因子必须是独立表达式，不得在一个因子表达式中引用另一个因子。\n  - 因子之间应体现不同构造思路，不要只改变窗口长度或阈值。\n  - 优先生成简单、可解释、容易回测验证的表达式。\n\n2. **CRITICAL: Factor Complexity Constraints**\n  - **Symbol Length (SL) Limit: ≤ 250 characters**\n    - 因子表达式不得超过 250 个字符，这是硬约束。\n    - 过长、过深嵌套、过多条件分支的表达式更容易过拟合。\n    - 简单且逻辑清楚的因子优先于复杂但难解释的因子。\n    - Example of GOOD: `RANK(TS_MEAN($return, 20))`\n    - Example of GOOD: `RANK(TS_CORR($close, $volume, 10)) * SIGN(TS_MEAN($return, 5))`\n    - Example of BAD: `RANK(POW(TS_CORR($close, SEQUENCE(15), 15), 2)) * ...`\n  - **Base Features (ER) Limit: ≤ 6 distinct raw features**\n    - 最多使用 6 个不同的基础字段。\n    - 优先围绕 2-4 个核心字段构造。\n  - **Simplicity Priority**\n    - 目标表达式长度优先控制在 50-150 字符。\n    - 避免深层嵌套、复杂条件表达式和过多乘法链。\n    - 如果历史反馈提示复杂度过高，下一轮必须生成明显更简单的表达式。\n\n3. **因子构造注意事项**\n  - 避免直接使用原始价格或成交量水平导致尺度问题，优先使用相对变化、排序或标准化。\n  - 可使用 `RANK()` 或 `ZSCORE()` 做截面可比处理。\n  - 分母中需要时加入 `1e-8` 避免除零。\n  - 避免使用未来信息；表达式只能基于当前或过去窗口。\n  - 不要使用未声明变量、等号赋值、不在函数库中的函数或 Python 代码。\n  - 定义条件时尽量避免过于严格的相等判断。\n  - 如果给出了重复子表达式，新的因子应换用不同结构，但仍保持可解释性。\n\n请严格按照以下 JSON 格式输出。JSON key 必须保持英文，描述性 value 使用中文；表达式字段必须使用英文变量和函数，且不得出现中文字符。\n{{ experiment_output_format }}\n\nStrictly adhere to the syntax requirements of factor expressions; do not use undeclared variables or functions."
    },
    "hypothesis2experiment.user_prompt": {
      "file": "quantaalpha/factors/prompts/prompts.yaml",
      "reader": "quantaalpha/factors/proposal.py::AlphaAgentHypothesis2FactorExpression._convert_with_history_limit",
      "stage": "AlphaAgent hypothesis -> factor expression",
      "role": "接入目标 hypothesis、历史记忆、函数库说明和重复表达式反馈。",
      "value": "请根据下面的目标假设生成新的 {{targets}}。\n\n目标假设：\n{{ target_hypothesis }}\n\n历史假设和对应反馈：\n{{ hypothesis_and_feedback }}\n\n构造因子表达式时，只能使用以下日频变量：\n- $open: open price of the stock on that day.\n- $close: close price of the stock on that day.\n- $high: high price of the stock on that day.\n- $low: low price of the stock on that day.\n- $volume: volume of the stock on that day.\n- $return: daily return of the stock on that day.\n\n允许使用的算子和函数如下：\n{{function_lib_description}}\n\n{% if expression_duplication %}\n**检测到历史表达式重复或复杂度问题**\n{{ expression_duplication }}\n\n生成新表达式时：\n- 避免复用上面提示的重复子表达式。\n- 如果复杂度过高，优先生成更短、更直接的表达式。\n- 可以用不同变量变换表达相近经济含义，例如使用 `$close/TS_MEAN($close, 10)` 或 `($open + $close) / 2` 替代直接价格水平。\n{% endif %}\n\n请只输出合法 JSON，不要输出 Markdown、解释或代码块。"
    },
    "expression_duplication": {
      "file": "quantaalpha/factors/prompts/prompts.yaml",
      "reader": "quantaalpha/factors/proposal.py::AlphaAgentHypothesis2FactorExpression._convert_with_history_limit",
      "stage": "表达式质量检查失败后",
      "role": "把重复、复杂度、参数化等问题渲染成反馈，再回灌到下一次 expression 生成。",
      "value": "- Proposed Expression: {{ prev_expression }}\n{% if duplicated_subtree_size > duplication_threshold %}\n- Novelty Check Failed: Duplicated subtree size ({{ duplicated_subtree_size }}) exceeds threshold ({{ duplication_threshold }})\n- Duplicated Sub-expression: {{ duplicated_subtree }}\n  {% if matched_alpha %}Matched with: {{ matched_alpha }}{% endif %}\n{% endif %}\n{% if free_args_ratio >= 0.5 %}\n- Parsimony Check Failed: Free arguments ratio ({{ \"%.2f\"|format(free_args_ratio * 100) }}%) >= 50%\n  - Number of free args: {{ num_free_args }}, Total nodes: {{ num_all_nodes }}\n  - 说明：这表明因子过度参数化。下一轮应显著减少自由参数。\n{% endif %}\n{% if unique_vars_ratio >= 0.5 %}\n- Diversity Check Failed: Unique variables ratio ({{ \"%.2f\"|format(unique_vars_ratio * 100) }}%) >= 50%\n  - Number of unique vars: {{ num_unique_vars }}, Total nodes: {{ num_all_nodes }}\n  - 说明：这表明表达式变量复用不足，结构可能较松散。请重新组织更紧凑的构造。\n{% endif %}\n{% if symbol_length > symbol_length_threshold %}\n- Symbol Length (SL) Check FAILED: Expression length ({{ symbol_length }}) exceeds HARD LIMIT ({{ symbol_length_threshold }} characters)\n  - 这是严重的过拟合风险信号。\n  - 请不要只删几个字符，而是从结构上重新设计更简单的表达式。\n  - Target Length: 50-150 characters for better generalization.\n  - Example of GOOD: `RANK(TS_MEAN($return, 20))`\n  - Example of ACCEPTABLE: `RANK(TS_CORR($close, $volume, 10)) * SIGN(TS_MEAN($return, 5))`\n  - 记住：可泛化的简单因子通常优于样本内分数更高但明显复杂的因子。\n{% endif %}\n{% if num_base_features > base_features_threshold %}\n- Base Features Count (ER) Check Failed: Number of base features ({{ num_base_features }}) exceeds threshold ({{ base_features_threshold }})\n  - 使用了过多基础字段。请减少 distinct base features，并优先聚焦 2-4 个核心字段。\n{% endif %}"
    },
    "coder.evolving_strategy_factor_implementation_v1_system": {
      "file": "quantaalpha/factors/coder/prompts.yaml",
      "reader": "FactorMultiProcessEvolvingStrategy.implement_one_task",
      "stage": "代码实现阶段",
      "role": "定义生成 factor.py 的 system prompt。",
      "value": "用户正在以下场景中实现一些因子：\n{{ scenario }}\n\n你的目标是输出能够正确计算目标因子值的代码。\n\n为了帮助你写出正确代码，用户可能提供以下信息：\n1. 与目标相似的正确代码实现\n2. 你之前失败的代码及对应反馈\n3. 最新失败代码的建议，以及若干“相似报错 -> 修正版本”的示例\n\n你必须认真阅读自己最近一次失败尝试，不要破坏已经正确的部分，只修正真正有问题的地方。\n\n{% if queried_former_failed_knowledge|length != 0 %}\n--------------Your former latest attempt:---------------\n=====Code to the former implementation=====\n{{ queried_former_failed_knowledge[-1].implementation.code }}\n=====Feedback to the former implementation=====\n{{ queried_former_failed_knowledge[-1].feedback }}\n{% endif %}\n\n请输出合法 JSON。\nAll JSON keys must remain exactly in English as specified.\nThe code string must remain valid Python code and must not contain Markdown fences.\n{\n    \"code\": \"Python code string\"\n}"
    },
    "coder.evolving_strategy_factor_implementation_v2_user": {
      "file": "quantaalpha/factors/coder/prompts.yaml",
      "reader": "FactorMultiProcessEvolvingStrategy.implement_one_task",
      "stage": "代码实现阶段",
      "role": "提供目标因子描述、相似错误、成功示例和最新失败尝试。",
      "value": "--------------Target factor information:---------------\n{{ factor_information_str }}\n\n{% if queried_similar_error_knowledge|length != 0 %}\n{% if error_summary_critics is none %}\n请回顾你上一次失败实现中遇到的错误。下面给出一些你在其他任务中遇到过的相似错误及其最终修正版本，请从中学习：\n{% for error_content, similar_error_knowledge in queried_similar_error_knowledge %}\n--------------Factor information to similar error ({{error_content}}):---------------\n{{ similar_error_knowledge[0].target_task.get_task_information() }}\n=====Code with similar error ({{error_content}}):=====\n{{ similar_error_knowledge[0].implementation.code }}\n=====Success code to former code with similar error ({{error_content}}):=====\n{{ similar_error_knowledge[1].implementation.code }}\n{% endfor %}\n{% else %}\n请回顾你上一次失败实现中遇到的错误。结合相似错误及其解决方式，下面是给你的修正建议：\n{{error_summary_critics}}\n{% endif %}\n{% endif %}\n\n{% if queried_similar_successful_knowledge|length != 0 %}\n下面是一些相似组件任务的成功实现，可作为参考：\n--------------Correct code to similar factors:---------------\n{% for similar_successful_knowledge in queried_similar_successful_knowledge %}\n=====Factor {{loop.index}}:=====\n{{ similar_successful_knowledge.target_task.get_task_information() }}\n=====Code:=====\n{{ similar_successful_knowledge.implementation.code }}\n{% endfor %}\n{% endif %}\n\n{% if latest_attempt_to_latest_successful_execution is not none %}\n你已经尝试修正上一次失败代码，但仍然出错。下面是最近一次尝试及其反馈。新的代码要尽量避免再次触发同类错误：\n=====Your latest attempt=====\n{{ latest_attempt_to_latest_successful_execution.implementation.code }}\n=====Feedback to your latest attempt=====\n{{ latest_attempt_to_latest_successful_execution.feedback }}\n{% endif %}"
    },
    "coder.evolving_strategy_error_summary_v2_system": {
      "file": "quantaalpha/factors/coder/prompts.yaml",
      "reader": "FactorMultiProcessEvolvingStrategy.error_summary",
      "stage": "代码报错后的 error summary",
      "role": "先让模型提炼关键错误，再反馈给下一次代码生成。",
      "value": "用户正在以下场景中实现一些因子：\n{{ scenario }}\n当前任务如下：\n{{factor_information_str}}\n\n你写出的代码出现了如下错误：\n{{code_and_feedback}}\n\n用户还提供了一些“相似错误及其最终正确解法”。\n请参考这些示例，输出清晰、简短、准确的关键建议，帮助修正当前代码。\n\n约束：\n1. 不要输出代码。\n2. 只指出最关键的问题。\n3. 如果没有发现明显问题，输出 `No critics found`。\n\n输出格式：\ncritic 1: 用中文写关键建议\ncritic 2: 用中文写关键建议"
    },
    "coder.evolving_strategy_error_summary_v2_user": {
      "file": "quantaalpha/factors/coder/prompts.yaml",
      "reader": "FactorMultiProcessEvolvingStrategy.error_summary",
      "stage": "代码报错后的 error summary",
      "role": "提供相似错误及其成功修正案例。",
      "value": "{% if queried_similar_error_knowledge|length != 0 %}\n{% for error_content, similar_error_knowledge in queried_similar_error_knowledge %}\n--------------Factor information to similar error ({{error_content}}):---------------\n{{ similar_error_knowledge[0].target_task.get_task_information() }}\n=====Code with similar error ({{error_content}}):=====\n{{ similar_error_knowledge[0].implementation.code }}\n=====Success code to former code with similar error ({{error_content}}):=====\n{{ similar_error_knowledge[1].implementation.code }}\n{% endfor %}\n{% endif %}"
    },
    "evaluator_output_format_system": {
      "file": "quantaalpha/factors/coder/prompts.yaml",
      "reader": "FactorOutputFormatEvaluator.evaluate",
      "stage": "代码执行后检查输出格式",
      "role": "判断当前输出 dataframe 是否符合 evaluator 预期格式。",
      "value": "用户正在以下场景中实现一些因子：\n{{ scenario }}\n\n用户会提供目标输出格式。你的任务是判断当前输出是否符合该格式要求。\n\nOutput must be valid JSON.\nAll JSON keys must remain exactly in English as specified.\nAll explanatory string values should be written in Chinese.\n{\n    \"output_format_decision\": true,\n    \"output_format_feedback\": \"用中文说明输出格式是否正确\"\n}"
    },
    "evaluator_final_decision_v1_system": {
      "file": "quantaalpha/factors/coder/prompts.yaml",
      "reader": "quantaalpha/factors/coder/eva_utils.py",
      "stage": "最终 evaluator 判定",
      "role": "综合代码反馈、值反馈和 ground truth 对比给出 final_decision。",
      "value": "用户正在以下场景中实现一些因子：\n{{ scenario }}\n\n用户已经完成评估，并从 evaluator 获得了若干反馈。\nevaluator 已经执行代码、生成因子值 dataframe，并提供了与代码和输出有关的若干反馈。\n你的任务是综合场景、因子定义、执行反馈和代码反馈，给出最终判断。\n\n判断逻辑：\n1. 如果因子值与 ground truth 在小容差内完全一致，则视为实现正确。\n2. 如果因子值与 ground truth 在 IC 或 RankIC 上高度一致，也可视为实现正确。\n3. 如果没有 ground truth，则只要代码成功执行且逻辑与场景、因子定义一致，即可视为实现正确。\n4. 任何异常，包括主动抛出的异常，都应被视为代码存在问题。\n\nOutput must be valid JSON.\nAll JSON keys must remain exactly in English as specified.\nAll explanatory string values should be written in Chinese.\n{\n    \"final_decision\": true,\n    \"final_feedback\": \"用中文写单行最终反馈\"\n}"
    },
    "evaluator_final_decision_v1_user": {
      "file": "quantaalpha/factors/coder/prompts.yaml",
      "reader": "quantaalpha/factors/coder/eva_utils.py",
      "stage": "最终 evaluator 判定",
      "role": "注入 factor information、execution feedback、code feedback、value feedback。",
      "value": "--------------Factor information:---------------\n{{ factor_information }}\n--------------Execution feedback:---------------\n{{ execution_feedback }}\n--------------Code feedback:---------------\n{{ code_feedback }}\n--------------Factor value feedback:---------------\n{{ value_feedback }}"
    },
    "qa.evaluator_code_feedback_v1_system": {
      "file": "quantaalpha/factors/coder/qa_prompts.yaml",
      "reader": "FactorCodeEvaluator.evaluate",
      "stage": "表达式 / 代码失败后的 QA critic",
      "role": "告诉模型如何针对表达式或代码实现问题给出简洁 critic。",
      "value": "用户正在以下场景中实现一些带有表达式的因子：\n{{ scenario }}\n\n**Only the following operations are allowed in expression:**\n### **Cross-sectional Functions**\n- **RANK(A)**: Ranking of each element in the cross-sectional dimension of A.\n- **ZSCORE(A)**: Z-score of each element in the cross-sectional dimension of A.\n- **MEAN(A)**: Mean value of each element in the cross-sectional dimension of A.\n- **STD(A)**: Standard deviation in the cross-sectional dimension of A.\n- **SKEW(A)**: Skewness in the cross-sectional dimension of A.\n- **KURT(A)**: Kurtosis in the cross-sectional dimension of A.\n- **MAX(A)**: Maximum value in the cross-sectional dimension of A.\n- **MIN(A)**: Minimum value in the cross-sectional dimension of A.\n- **MEDIAN(A)**: Median value in the cross-sectional dimension of A\n- **SCALE(A, target_sum)**: Scale the absolute values in the cross-section to sum to target_sum.\n\n### **Time-Series Functions**\n- **DELTA(A, n)**: Change in value of A over n periods.\n- **DELAY(A, n)**: Value of A delayed by n periods.\n- **TS_MEAN(A, n)**: Mean value of sequence A over the past n days.\n- **TS_SUM(A, n)**: Sum of sequence A over the past n days.\n- **TS_RANK(A, n)**: Time-series rank of the last value of A in the past n days.\n- **TS_ZSCORE(A, n)**: Z-score for each sequence in A over the past n days.\n- **TS_MEDIAN(A, n)**: Median value of sequence A over the past n days.\n- **TS_PCTCHANGE(A, p)**: Percentage change in the value of sequence A over p periods.\n- **TS_MIN(A, n)**: Minimum value of A in the past n days.\n- **TS_MAX(A, n)**: Maximum value of A in the past n days.\n- **TS_ARGMAX(A, n)**: The index (relative to the current time) of the maximum value of A over the past n days.\n- **TS_ARGMIN(A, n)**: The index (relative to the current time) of the minimum value of A over the past n days.\n- **TS_QUANTILE(A, p, q)**: Rolling quantile of sequence A over the past p periods, where q is the quantile value between 0 and 1.\n- **TS_STD(A, n)**: Standard deviation of sequence A over the past n days.\n- **TS_VAR(A, p)**: Rolling variance of sequence A over the past p periods.\n- **TS_CORR(A, B, n)**: Correlation coefficient between sequences A and B over the past n days.\n- **TS_COVARIANCE(A, B, n)**: Covariance between sequences A and B over the past n days.\n- **TS_MAD(A, n)**: Rolling Median Absolute Deviation of sequence A over the past n days.\n- **PERCENTILE(A, q, p)**: Quantile of sequence A, where q is the quantile value between 0 and 1. If p is provided, it calculates the rolling quantile over the past p periods.\n- **HIGHDAY(A, n)**: Number of days since the highest value of A in the past n days.\n- **LOWDAY(A, n)**: Number of days since the lowest value of A in the past n days.\n- **SUMAC(A, n)**: Cumulative sum of A over the past n days.\n\n### **Moving Averages and Smoothing Functions**\n- **SMA(A, n, m)**: Simple moving average of A over n periods with modifier m.\n- **WMA(A, n)**: Weighted moving average of A over n periods, with weights decreasing from 0.9 to 0.9^(n).\n- **EMA(A, n)**: Exponential moving average of A over n periods, where the decay factor is 2/(n+1).\n- **DECAYLINEAR(A, d)**: Linearly weighted moving average of A over d periods, with weights increasing from 1 to d.\n\n### **Mathematical Operations**\n- **PROD(A, n)**: Product of values in A over the past n days. Use `*` for general multiplication.\n- **LOG(A)**: Natural logarithm of each element in A.\n- **SQRT(A)**: Square root of each element in A.\n- **POW(A, n)**: Raise each element in A to the power of n.\n- **SIGN(A)**: Sign of each element in A, one of 1, 0, or -1.\n- **EXP(A)**: Exponential of each element in A.\n- **ABS(A)**: Absolute value of A.\n- **MAX(A, B)**: Maximum value between A and B.\n- **MIN(A, B)**: Minimum value between A and B.\n- **INV(A)**: Reciprocal (1/x) of each element in sequence A.\n- **FLOOR(A)**: Floor of each element in sequence A.\n\n### **Conditional and Logical Functions**\n- **COUNT(C, n)**: Count of samples satisfying condition C in the past n periods. Here, C is a logical expression, e.g., `$close > $open`.\n- **SUMIF(A, n, C)**: Sum of A over the past n periods if condition C is met. Here, C is a logical expression.\n- **FILTER(A, C)**: Filtering multi-column sequence A based on condition C. Here, C is presented in a logical expression form, with the same size as A.\n- **(C1)&&(C2)**: Logical operation \"and\". Both C1 and C2 are logical expressions, such as A > B.\n- **(C1)||(C2)**: Logical operation \"or\". Both C1 and C2 are logical expressions, such as A > B.\n- **(C1)?(A):(B)**: Logical operation \"If condition C1 holds, then A, otherwise B\". C1 is a logical expression, such as A > B.\n\n### **Regression and Residual Functions**\n- **SEQUENCE(n)**: A single-column sequence of length n, ranging from 1 to integer n. `SEQUENCE()` should always be nested in `REGBETA()` or `REGRESI()` as argument B.\n- **REGBETA(A, B, n)**: Regression coefficient of A on B using the past n samples, where A MUST be a multi-column sequence and B a single-column or multi-column sequence.\n- **REGRESI(A, B, n)**: Residual of regression of A on B using the past n samples, where A MUST be a multi-column sequence and B a single-column or multi-column sequence.\n\n### **Technical Indicators**\n- **RSI(A, n)**: Relative Strength Index of sequence A over n periods. Measures momentum by comparing the magnitude of recent gains to recent losses.\n- **MACD(A, short_window, long_window)**: Moving Average Convergence Divergence (MACD) of sequence A, calculated as the difference between the short-term (short_window) and long-term (long_window) exponential moving averages.\n- **BB_MIDDLE(A, n)**: Middle Bollinger Band, calculated as the n-period simple moving average of sequence A.\n- **BB_UPPER(A, n)**: Upper Bollinger Band, calculated as middle band plus two standard deviations of sequence A over n periods.\n- **BB_LOWER(A, n)**: Lower Bollinger Band, calculated as middle band minus two standard deviations of sequence A over n periods.\n\nNote that:\n- Only the variables provided in data (e.g., `$open`), arithmetic operators (`+, -, *, /`), logical operators (`&&, ||`), and the operations above are allowed in the factor expression.\n- Make sure your factor expression contains at least one variable within the dataframe columns (e.g., $open), combined with registered operations above. Do NOT use any undeclared variable (e.g., `n`, `w_1`) and undefined symbols (e.g., `=`) in the expression.\n- Pay attention to the distinction between operations with the TS prefix (e.g., `TS_STD()`) and those without (e.g., `STD()`).\n\n用户会提供因子信息、表达式模板以及执行反馈。\n\n你的任务是判断用户给出的 factor expression 是否与因子描述一致，以及该表达式是否能被正确计算。\n当前表达式会被渲染到一个 Python jinja2 template 中并执行，因此你需要重点关注：\n1. 表达式语义是否与因子描述大体一致\n2. 表达式是否使用了允许的变量、函数和操作符\n3. 执行错误是否反映出表达式层面的关键问题\n\n说明：\n- 你给出的评论是发给 coding agent 的，不是给终端用户逐行排查的，因此不要写“请检查第几行”。\n- 允许公式与表达式在非核心细节上存在轻微差异，例如窗口长度、小的实现差别等；不要吹毛求疵。\n- 不要输出代码，只输出清晰、简短、关键的评论。\n- 如果没有发现明显问题，直接输出 `No comment found`。\n\n输出格式：\ncomment 1: 用中文写关键评论\ncomment 2: 用中文写关键评论"
    },
    "qa.evaluator_code_feedback_v1_user": {
      "file": "quantaalpha/factors/coder/qa_prompts.yaml",
      "reader": "FactorCodeEvaluator.evaluate",
      "stage": "表达式 / 代码失败后的 QA critic",
      "role": "提供 factor information、模板代码、执行反馈和因子值反馈。",
      "value": "--------------Factor information:---------------\n{{ factor_information }}\n--------------Factor Expression in the Python template:---------------\n{{ code }}\n--------------Execution feedback:---------------\n{{ execution_feedback }}\n{% if value_feedback is not none %}\n--------------Factor value feedback:---------------\n{{ value_feedback }}\n{% endif %}\n{% if gt_code is not none %}\n{% endif %}"
    },
    "qa.evolving_strategy_factor_implementation_v1_system": {
      "file": "quantaalpha/factors/coder/qa_prompts.yaml",
      "reader": "FactorParsingStrategy.implement_one_task",
      "stage": "表达式修复阶段",
      "role": "告诉模型只输出修正后的 expr，并遵守 DSL 白名单。",
      "value": "用户正在以下场景中通过编写 factor expression 来实现因子：\n{{ scenario }}\n\n只要目标因子能够在当前可用数据和操作集合中被合理实现，你的表达式就应尽量贴合因子描述。\n\n用户可能提供以下信息来帮助你修正表达式：\n1. 与目标相似因子的正确 expression\n2. 你之前失败的 expression 及其反馈\n3. 最新失败 expression 的建议，以及若干“相似错误 -> 修正表达式”的示例\n4. 其余代码部分是固定的 jinja2 template，你的 response 只需要给出新的 expression\n\n**你的任务是基于最近一次失败尝试，修正或重写 expression。**\n\n**Only the following operations are allowed in expression:**\n### **Cross-sectional Functions**\n- **RANK(A)**: Ranking of each element in the cross-sectional dimension of A.\n- **ZSCORE(A)**: Z-score of each element in the cross-sectional dimension of A.\n- **MEAN(A)**: Mean value of each element in the cross-sectional dimension of A.\n- **STD(A)**: Standard deviation in the cross-sectional dimension of A.\n- **SKEW(A)**: Skewness in the cross-sectional dimension of A.\n- **KURT(A)**: Kurtosis in the cross-sectional dimension of A.\n- **MAX(A)**: Maximum value in the cross-sectional dimension of A.\n- **MIN(A)**: Minimum value in the cross-sectional dimension of A.\n- **MEDIAN(A)**: Median value in the cross-sectional dimension of A\n- **SCALE(A, target_sum)**: Scale the absolute values in the cross-section to sum to target_sum.\n\n### **Time-Series Functions**\n- **DELTA(A, n)**: Change in value of A over n periods.\n- **DELAY(A, n)**: Value of A delayed by n periods.\n- **TS_MEAN(A, n)**: Mean value of sequence A over the past n days.\n- **TS_SUM(A, n)**: Sum of sequence A over the past n days.\n- **TS_RANK(A, n)**: Time-series rank of the last value of A in the past n days.\n- **TS_ZSCORE(A, n)**: Z-score for each sequence in A over the past n days.\n- **TS_MEDIAN(A, n)**: Median value of sequence A over the past n days.\n- **TS_PCTCHANGE(A, p)**: Percentage change in the value of sequence A over p periods.\n- **TS_MIN(A, n)**: Minimum value of A in the past n days.\n- **TS_MAX(A, n)**: Maximum value of A in the past n days.\n- **TS_ARGMAX(A, n)**: The index (relative to the current time) of the maximum value of A over the past n days.\n- **TS_ARGMIN(A, n)**: The index (relative to the current time) of the minimum value of A over the past n days.\n- **TS_QUANTILE(A, p, q)**: Rolling quantile of sequence A over the past p periods, where q is the quantile value between 0 and 1.\n- **TS_STD(A, n)**: Standard deviation of sequence A over the past n days.\n- **TS_VAR(A, p)**: Rolling variance of sequence A over the past p periods.\n- **TS_CORR(A, B, n)**: Correlation coefficient between sequences A and B over the past n days.\n- **TS_COVARIANCE(A, B, n)**: Covariance between sequences A and B over the past n days.\n- **TS_MAD(A, n)**: Rolling Median Absolute Deviation of sequence A over the past n days.\n- **PERCENTILE(A, q, p)**: Quantile of sequence A, where q is the quantile value between 0 and 1. If p is provided, it calculates the rolling quantile over the past p periods.\n- **HIGHDAY(A, n)**: Number of days since the highest value of A in the past n days.\n- **LOWDAY(A, n)**: Number of days since the lowest value of A in the past n days.\n- **SUMAC(A, n)**: Cumulative sum of A over the past n days.\n\n### **Moving Averages and Smoothing Functions**\n- **SMA(A, n, m)**: Simple moving average of A over n periods with modifier m.\n- **WMA(A, n)**: Weighted moving average of A over n periods, with weights decreasing from 0.9 to 0.9^(n).\n- **EMA(A, n)**: Exponential moving average of A over n periods, where the decay factor is 2/(n+1).\n- **DECAYLINEAR(A, d)**: Linearly weighted moving average of A over d periods, with weights increasing from 1 to d.\n\n### **Mathematical Operations**\n- **PROD(A, n)**: Product of values in A over the past n days. Use `*` for general multiplication.\n- **LOG(A)**: Natural logarithm of each element in A.\n- **SQRT(A)**: Square root of each element in A.\n- **POW(A, n)**: Raise each element in A to the power of n.\n- **SIGN(A)**: Sign of each element in A, one of 1, 0, or -1.\n- **EXP(A)**: Exponential of each element in A.\n- **ABS(A)**: Absolute value of A.\n- **MAX(A, B)**: Maximum value between A and B.\n- **MIN(A, B)**: Minimum value between A and B.\n- **INV(A)**: Reciprocal (1/x) of each element in sequence A.\n- **FLOOR(A)**: Floor of each element in sequence A.\n\n### **Conditional and Logical Functions**\n- **COUNT(C, n)**: Count of samples satisfying condition C in the past n periods. Here, C is a logical expression, e.g., `$close > $open`.\n- **SUMIF(A, n, C)**: Sum of A over the past n periods if condition C is met. Here, C is a logical expression.\n- **FILTER(A, C)**: Filtering multi-column sequence A based on condition C. Here, C is presented in a logical expression form, with the same size as A.\n- **(C1)&&(C2)**: Logical operation \"and\". Both C1 and C2 are logical expressions, such as A > B.\n- **(C1)||(C2)**: Logical operation \"or\". Both C1 and C2 are logical expressions, such as A > B.\n- **(C1)?(A):(B)**: Logical operation \"If condition C1 holds, then A, otherwise B\". C1 is a logical expression, such as A > B.\n\n### **Regression and Residual Functions**\n- **SEQUENCE(n)**: A single-column sequence of length n, ranging from 1 to integer n. `SEQUENCE()` should always be nested in `REGBETA()` or `REGRESI()` as argument B.\n- **REGBETA(A, B, n)**: Regression coefficient of A on B using the past n samples, where A MUST be a multi-column sequence and B a single-column or multi-column sequence.\n- **REGRESI(A, B, n)**: Residual of regression of A on B using the past n samples, where A MUST be a multi-column sequence and B a single-column or multi-column sequence.\n\n### **Technical Indicators**\n- **RSI(A, n)**: Relative Strength Index of sequence A over n periods. Measures momentum by comparing the magnitude of recent gains to recent losses.\n- **MACD(A, short_window, long_window)**: Moving Average Convergence Divergence (MACD) of sequence A, calculated as the difference between the short-term (short_window) and long-term (long_window) exponential moving averages.\n- **BB_MIDDLE(A, n)**: Middle Bollinger Band, calculated as the n-period simple moving average of sequence A.\n- **BB_UPPER(A, n)**: Upper Bollinger Band, calculated as middle band plus two standard deviations of sequence A over n periods.\n- **BB_LOWER(A, n)**: Lower Bollinger Band, calculated as middle band minus two standard deviations of sequence A over n periods.\n\nNote that:\n- Only the variables provided in data (e.g., `$open`), arithmetic operators (`+, -, *, /`), logical operators (`&&, ||`), and the operations above are allowed in the factor expression.\n- Make sure your factor expression contains at least one variable within the dataframe columns (e.g., $open), combined with registered operations above. Do NOT use any undeclared variable (e.g., `n`, `w_1`) and undefined symbols (e.g., `=`) in the expression.\n- Pay attention to the distinction between operations with the TS prefix (e.g., `TS_STD()`) and those without (e.g., `STD()`).\n\n请输出合法 JSON。\nAll JSON keys must remain exactly in English as specified.\nThe expression value must remain a pure English expression string and must not contain any Chinese characters.\n{\n    \"expr\": \"[CORRECTED_FACTOR_EXPRESSION]\"\n}"
    },
    "qa.evolving_strategy_factor_implementation_v2_user": {
      "file": "quantaalpha/factors/coder/qa_prompts.yaml",
      "reader": "FactorParsingStrategy.implement_one_task",
      "stage": "表达式修复阶段",
      "role": "提供旧 expression、旧 feedback、相似错误与相似成功案例。",
      "value": "--------------Target factor information:---------------\n{{ factor_information_str }}\n\n{% if former_expression is not none %}\n--------------Your former latest attempt:---------------\n=====Expression to the former implementation=====\n{{ former_expression }}\n\n=====Feedback to the former implementation=====\n{{ former_feedback }}\n{% endif %}\n\n{% if queried_similar_error_knowledge|length != 0 %}\n{% if error_summary_critics is none %}\n请回顾你上一次失败的 expression。下面给出一些其他任务中出现过的相似错误及最终修正版本，请从中学习：\n{% for error_content, similar_error_knowledge in queried_similar_error_knowledge %}\n--------------Factor information to similar error ({{error_content}}):---------------\n{{ similar_error_knowledge[0].target_task.get_task_information() }}\n=====Code with similar error ({{error_content}}):=====\n{{ similar_error_knowledge[0].implementation.code }}\n=====Success code to former code with similar error ({{error_content}}):=====\n{{ similar_error_knowledge[1].implementation.code }}\n{% endfor %}\n{% else %}\n请回顾你上一次失败的 expression。结合相似错误与其解决方式，下面是给你的修正建议：\n{{error_summary_critics}}\n{% endif %}\n{% endif %}\n\n{% if similar_successful_factor_description is not none %}\n下面给出一个相似成功因子的参考：\n--------------Correct code to similar factors:---------------\n=====Factor Description:=====\n{{ similar_successful_factor_description }}\n=====Factor Expression:=====\n{{ similar_successful_expression }}\n{% endif %}\n{% if latest_attempt_to_latest_successful_execution is not none %}\n你已经尝试修正上一次失败的 expression，但仍然报错。下面是最近一次尝试及其反馈。新的输出要尽量避免再次触发同类错误：\n=====Your latest attempt=====\n{{ latest_attempt_to_latest_successful_execution.implementation.code }}\n=====Feedback to your latest attempt=====\n{{ latest_attempt_to_latest_successful_execution.feedback }}\n{% endif %}"
    },
    "factor_feedback_generation.system": {
      "file": "quantaalpha/factors/prompts/prompts.yaml",
      "reader": "quantaalpha/factors/feedback.py",
      "stage": "回测完成后的 feedback 生成",
      "role": "告诉 LLM 如何比较 current result 和 SOTA result，并生成 hypothesis 反馈。",
      "value": "请先理解以下研究场景与操作逻辑，再生成适用于该场景的反馈：\n\n{{ scenario }}\n\n你将收到：\n1. 一个 hypothesis\n2. 多个 task 及其 factor 信息\n3. 当前实验结果\n4. 与 SOTA result 的对比\n\n你的反馈需要回答以下问题：\n1. 当前结果是否支持或反驳该 hypothesis\n2. 当前结果相较于上一轮 SOTA 是改善还是退化\n3. 如果下一轮继续研究，应如何优化当前方向或提出更合适的新假设\n\n请理解以下操作逻辑：\n1. Logic Explanation:\n  - 每个 hypothesis 都代表一个可以多轮迭代的理论框架。\n  - 当前更强调在同一理论框架内持续优化，而不是过早更换方向。\n  - 在考虑方向切换之前，应先充分探索同一研究思路下的多种实现。\n\n2. Development Directions:\n  - Hypothesis Refinement:\n    - 指出当前假设在因子构造上的具体改进空间\n    - 建议同一理论概念下更清晰或更稳健的数学表达方式\n    - 指出值得继续探索的参数范围、组合方式或结构变化\n  - Factor Enhancement:\n    - 对现有因子做结构优化，而不是只做表面参数扰动\n    - 关注标准化、归一化、加权方式等实现细节\n    - 对不同窗口与组合方式给出更具体建议\n  - Methodological Iteration:\n    - 在保留核心概念的前提下优化表达式结构\n    - 寻找同一理论框架内的补充信号\n    - 提出更稳健、可泛化的变体\n\n3. Final Goal:\n  - 最终目标是持续挖掘优于前一轮的因子或实验结果，以维持当前最佳 SOTA。\n\n当你分析结果时，请重点关注：\n1. **Factor Construction Analysis**\n  - 不同构造方式如何影响表现\n  - 哪些构造部分最影响性能\n  - 如何提升稳健性而非仅追求样本内高分\n\n2. **Parameter Sensitivity**\n  - 不同参数选择的影响\n  - 哪些参数区间更值得继续探索\n  - 哪些构造部件是关键，哪些只是噪声\n\n3. **Complexity Control**\n  - **Symbol Length (SL)**: 表达式超过 250 个字符时，极易过拟合；下一轮应显著简化。\n  - **Base Features Count (ER)**: 使用过多基础字段通常意味着过度工程化，应收缩到 2-4 个核心字段。\n  - **Free Parameters (PC)**: 自由参数过多说明过度参数化，应明显减少。\n  - 复杂表达式、深层嵌套和条件分支往往在训练阶段表现很好，但在测试集失效。\n  - 如果出现“训练指标高、测试指标差”的现象，应优先怀疑过拟合并建议大幅简化表达式。\n  - 当提供了复杂度反馈时，要将其视为严重问题，而不是轻微瑕疵。\n\n请重点强调持续优化：\n- 尽量挖掘当前理论框架内的有效变体\n- 记录哪些实现方式有效、哪些无效\n- **始终优先简单、清晰、可泛化的表达式**\n\n请输出合法 JSON。\nAll JSON keys must remain exactly in English as specified.\nAll explanatory string values should be written in Chinese.\n{\n  \"Observations\": \"用中文写总体观察\",\n  \"Feedback for Hypothesis\": \"用中文写与假设相关的反馈\",\n  \"New Hypothesis\": \"用中文写建议的新假设或新方向\",\n  \"Reasoning\": \"用中文写理由\",\n  \"Replace Best Result\": \"yes or no\"\n}"
    },
    "factor_feedback_generation.user": {
      "file": "quantaalpha/factors/prompts/prompts.yaml",
      "reader": "quantaalpha/factors/feedback.py",
      "stage": "回测完成后的 feedback 生成",
      "role": "注入 hypothesis、factor details、combined result 和复杂度反馈。",
      "value": "目标假设：\n{{ hypothesis_text }}\n\nTasks and Factors:\n{% for task in task_details %}\n  - {{ task.factor_name }}: {{ task.factor_description }}\n    - Factor Formulation: {{ task.factor_formulation }}\n    - Variables: {{ task.variables }}\n    - Factor Implementation: {{ task.factor_implementation }}\n    {% if task.get(\"complexity_feedback\") and task.complexity_feedback %}\n    - Complexity Feedback: {{ task.complexity_feedback }}\n      重要提示：该因子被标记为复杂度过高。请在后续建议中明确考虑简化表达式。过长表达式、过多基础字段或过多参数通常意味着过拟合和较差泛化。\n    {% endif %}\n    {% if task.factor_implementation == \"False\" %}\n    注意：该因子本轮未成功实现和测试，因此无法真正验证其对应假设。\n    {% endif %}\n{% endfor %}\n\nCombined Results:\n{{ combined_result }}\n\n请结合以上信息分析：\n1. 当前结果是否支持或反驳该 hypothesis。\n2. 当前结果相较于 SOTA experiment 是改善还是退化。\n\nEvaluation Metrics Explanations:\n- 1day.excess_return_without_cost.max_drawdown: 最大回撤，越小越好\n- 1day.excess_return_without_cost.information_ratio: 信息比率，越大越好\n- 1day.excess_return_without_cost.annualized_return: 年化收益，越大越好\n- IC: 因子与未来收益的 Pearson correlation，越大越好\n\n当你判断是否替换当前最佳结果时：\n1. 如果年化收益出现显著改善，可建议替换当前 best result。\n2. 如果年化收益改善，且任意一个其他关键指标也更好，可建议替换。\n3. 如果只是其他指标轻微变化，但年化收益更好，也可以接受。\n4. 但若复杂度警告明显，即使指标更好，也要警惕过拟合风险。\n\n如果某个因子被标记为复杂度过高：\n- 请明确指出这是严重问题\n- 即使当前指标不错，也建议下一轮优先简化\n- 请把“如何更简单而不丢失核心经济含义”写进反馈"
    },
    "mutation.system": {
      "file": "quantaalpha/pipeline/prompts/evolution_prompts.yaml",
      "reader": "MutationOperator.generate_mutation",
      "stage": "mutation brief 生成",
      "role": "定义 mutation 的高层目标。",
      "value": "你是一名量化研究中的策略演化专家，擅长在已有父分支基础上生成新的探索方向。\n\n你的任务是基于父策略，生成一个新的 mutation 方向。\n\n在当前版本中，mutation 的核心要求是：\n1. 新方向必须与父策略存在清晰差异，避免重复探索已经饱和的子空间。\n2. 差异可以来自不同的市场假设、不同的数据维度、不同的特征结构、不同的行为机制或不同的条件约束。\n3. 新方向仍需保持可实现、可检验、可由当前研究框架继续转化为因子。\n4. 不要把“差异”误写成仅仅更换窗口、阈值或参数。\n\n输出时请保持 JSON key 为英文，说明性 value 使用中文。\n"
    },
    "mutation.user": {
      "file": "quantaalpha/pipeline/prompts/evolution_prompts.yaml",
      "reader": "MutationOperator.generate_mutation",
      "stage": "mutation 详细生成路径",
      "role": "注入父 hypothesis、父因子、父指标、父 feedback。",
      "value": "请基于以下父策略信息，生成一个新的 mutation 研究方向。\n\n## Parent Strategy Information\n\n### Hypothesis\n{parent_hypothesis}\n\n### Factor Expressions\n{parent_factors}\n\n### Backtest Metrics\n{parent_metrics}\n\n### Evaluation Feedback\n{parent_feedback}\n\n---\n\n## Requirements\n\n请输出一个与父策略具有明确差异的新方向，并包含以下字段：\n\n1. **New Hypothesis**：新的待检验市场假设\n2. **Exploration Direction**：新的研究切入点或特征构造方向\n3. **Orthogonality Reasoning**：说明为什么该方向与父策略有实质差异\n4. **Expected Characteristics**：预期该方向可能产出的因子特征\n\n请注意：\n- 不要把新方向写成已经被证明有效。\n- 不要只通过参数微调制造“新方向”。\n- 保持技术上可实现。\n\nOutput must be valid JSON.\nAll JSON keys must remain exactly in English as specified.\nAll explanatory string values should be written in Chinese.\n\nExample JSON:\n{\n  \"new_hypothesis\": \"用中文描述新的待检验假设\",\n  \"exploration_direction\": \"用中文描述新的研究方向\",\n  \"orthogonality_reason\": \"用中文说明与父策略的实质差异\",\n  \"expected_characteristics\": \"用中文说明预期特征\"\n}\n"
    },
    "mutation.simple_user": {
      "file": "quantaalpha/pipeline/prompts/evolution_prompts.yaml",
      "reader": "MutationOperator.generate_mutation",
      "stage": "mutation 简化生成路径",
      "role": "只生成一条简短新假设。",
      "value": "请根据以下信息生成一个新的因子挖掘假设：\n\nParent Hypothesis: {parent_hypothesis}\n\nParent Factors: {parent_factors}\n\n请直接输出一条新的待检验假设。保持中文描述，但不要翻译字段名、函数名或表达式 token。\n"
    },
    "mutation.suffix_template": {
      "file": "quantaalpha/pipeline/prompts/evolution_prompts.yaml",
      "reader": "MutationOperator.generate_mutation_prompt_suffix",
      "stage": "mutation child branch 进入下一轮 loop 前",
      "role": "把 mutation 结果包装成 strategy_suffix。",
      "value": "---\n\n## Mutation Round Guidance\n\n这是一个 mutation 探索轮次。你需要在父策略基础上生成新的研究假设，但必须避免重复父分支已经覆盖的子空间。\n\n### Parent Strategy Summary\n{parent_summary}\n\n### Mutation Direction Suggestions\n- **New Hypothesis Direction**: {new_hypothesis}\n- **Exploration Dimension**: {exploration_direction}\n- **Orthogonality Reasoning**: {orthogonality_reason}\n\n### Important Notes\n1. 新假设必须与父策略存在实质差异，而不是参数级微调。\n2. 优先探索父策略尚未覆盖的市场机制、结构关系或条件依赖。\n3. 生成的新因子应尽量降低与父分支已有因子的重复度。\n\n请根据以上 mutation guidance 继续提出新的假设。\n"
    },
    "mutation.fallback_templates": {
      "file": "quantaalpha/pipeline/prompts/evolution_prompts.yaml",
      "reader": "MutationOperator._generate_fallback_hypothesis",
      "stage": "mutation 调 LLM 失败时",
      "role": "提供兜底 mutation 方向。",
      "value": "检验价格动量失效后是否出现更稳定的均值回归信号\n检验量价非线性偏离是否包含未来收益信息\n检验不同波动阶段下趋势切换的截面预测能力\n检验流动性约束与价格路径交互是否形成有效 alpha\n检验波动率状态切换是否改变传统价量信号的方向与强度\n检验板块轮动背景下个股相对位置是否产生附加 alpha"
    },
    "crossover.system": {
      "file": "quantaalpha/pipeline/prompts/evolution_prompts.yaml",
      "reader": "CrossoverOperator.generate_crossover",
      "stage": "crossover brief 生成",
      "role": "定义 crossover 的高层目标。",
      "value": "你是一名量化研究中的策略融合专家，擅长结合多个父策略的优势生成新的混合研究方向。\n\n你的任务是分析多个父策略，识别它们的优势、弱点和互补关系，并生成一个新的 hybrid strategy。\n\n在融合时请重点考虑：\n1. 每个父策略的核心假设和市场逻辑\n2. 哪些特征结构表现较好\n3. 父策略之间是否存在互补性或协同空间\n4. 如何避免把多个父策略共同的缺陷一起继承下来\n\n输出时请保持 JSON key 为英文，说明性 value 使用中文。\n"
    },
    "crossover.user": {
      "file": "quantaalpha/pipeline/prompts/evolution_prompts.yaml",
      "reader": "CrossoverOperator.generate_crossover",
      "stage": "crossover 详细生成路径",
      "role": "注入父轨迹摘要并要求输出结构化 hybrid 方向。",
      "value": "请基于以下多个父策略，生成一个新的 crossover 融合方向。\n\n## Parent Strategy Information\n\n{parent_summaries}\n\n---\n\n## Requirements\n\n请输出一个融合多个父策略优势的新方向，并包含以下字段：\n\n1. **Hybrid Hypothesis**：融合后的待检验市场假设\n2. **Fusion Logic**：说明如何结合各父策略的优势\n3. **Innovation Points**：说明新方向相对于父策略的新增特征\n4. **Expected Benefits**：说明为什么该融合方向可能优于单个父策略\n\n请注意：\n- 保持可实现、可检验，不要写成已经成立的结论。\n- 不要机械拼接父策略表述，要明确融合后的新机制。\n\nOutput must be valid JSON.\nAll JSON keys must remain exactly in English as specified.\nAll explanatory string values should be written in Chinese.\n\nExample JSON:\n{\n  \"hybrid_hypothesis\": \"用中文描述融合后的新假设\",\n  \"fusion_logic\": \"用中文说明融合逻辑\",\n  \"innovation_points\": \"用中文说明新特征\",\n  \"expected_benefits\": \"用中文说明预期优势\"\n}\n"
    },
    "crossover.simple_user": {
      "file": "quantaalpha/pipeline/prompts/evolution_prompts.yaml",
      "reader": "CrossoverOperator.generate_crossover",
      "stage": "crossover 简化生成路径",
      "role": "只生成一条简短的融合假设。",
      "value": "请综合以下父策略的优势，生成一个新的 hybrid hypothesis：\n\n{parent_summaries}\n\n请直接输出中文假设内容，不要翻译函数名、表达式 token 或字段名。\n"
    },
    "crossover.parent_template": {
      "file": "quantaalpha/pipeline/prompts/evolution_prompts.yaml",
      "reader": "CrossoverOperator._format_parent_summary",
      "stage": "组装 parent summary 时",
      "role": "规定单个父轨迹摘要的展示格式。",
      "value": "### Parent {idx}: {phase_name}\n**Direction ID**: {direction_id}\n**Hypothesis**: {hypothesis}\n**Factors**:\n{factors}\n**Metrics**:\n{metrics}\n**Feedback**:\n{feedback}\n---\n"
    },
    "crossover.suffix_template": {
      "file": "quantaalpha/pipeline/prompts/evolution_prompts.yaml",
      "reader": "CrossoverOperator.generate_crossover_prompt_suffix",
      "stage": "crossover child branch 进入下一轮 loop 前",
      "role": "把 crossover 结果包装成 strategy_suffix。",
      "value": "---\n\n## Crossover Round Guidance\n\n这是一个 crossover 融合探索轮次。你需要在多个父策略基础上生成新的混合研究方向。\n\n### Parent Strategy Summaries\n{parent_summaries}\n\n### Fusion Direction Suggestions\n- **Hybrid Hypothesis Direction**: {hybrid_hypothesis}\n- **Fusion Logic**: {fusion_logic}\n- **Innovation Points**: {innovation_points}\n\n### Important Notes\n1. 新假设应融合多个父策略的优势，而不是简单拼接措辞。\n2. 尽量避免继承多个父策略共有的弱点。\n3. 优先寻找真正具有协同效应的组合机制。\n4. 生成的新因子应能够体现融合后的综合特征。\n\n请根据以上 crossover guidance 提出融合假设。\n"
    },
    "crossover.phase_names": {
      "file": "quantaalpha/pipeline/prompts/evolution_prompts.yaml",
      "reader": "CrossoverOperator._format_parent_summary",
      "stage": "parent summary 组装时",
      "role": "把 phase label 映射成更可读的名字。",
      "value": "{\n  \"original\": \"Original Round\",\n  \"mutation\": \"Mutation Round\",\n  \"crossover\": \"Crossover Round\"\n}"
    }
  }
};
