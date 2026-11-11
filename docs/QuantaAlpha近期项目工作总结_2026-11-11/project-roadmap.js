document.addEventListener("DOMContentLoaded", () => {
  document.querySelector(".hero .eyebrow")?.remove();
  document.querySelector(".hero .subtitle")?.remove();
  document.querySelector("main > section:first-of-type h2").textContent = "系统整体流程";
  document.querySelector("main > section:first-of-type p.intro")?.remove();
  const evaluationText = document.querySelector(".eval .step:last-child p");
  evaluationText.textContent = "训练期：2023-01-01 至 2025-06-30；通过后观察 2025-07-01 至 2025-12-31 的验证表现，并检查同方向相似因子。";
  const results = document.querySelector(".results");
  const next = results.nextElementSibling;
  const groups = [
    ["历史完成任务", [
      ["建立结构化运行记录", ["把规划、假设、公式、评估和事件写入 Run Trace。", "开发可逐层查看节点与原始产物的运行轨迹页面。"]],
      ["搭建新版 OTO 单因子回测", ["用公司 Mongo 行情替换旧评估口径，逐个评估因子。", "加入信号与交易日对齐、防未来审计、训练和验证期筛选。"]],
      ["优化中文量化 Prompt", ["调整方向、假设和因子公式生成提示词。", "加入中英文 Prompt Pack 切换，并在前端保存选择，便于 A/B 对比。"]],
      ["增加调仓周期配置", ["让回测支持按指定交易日间隔调仓。", "在因子结果中显示调仓周期和多空收益曲线。"]],
      ["建设战术因子分析页", ["增加独立的战术因子分析看板。"]],
      ["改进因子结果展示", ["给因子添加 Barra 风格分类。", "整理手续费标注、基准比较曲线和坐标轴展示。"]],
      ["增强模型调用与挖掘稳定性", ["支持按任务标签配置不同模型服务商和推理模型。", "处理空响应、失败任务重复运行及任务停止控制。"]]
    ]],
    ["近期完成任务", [
      ["新增 Mongo 日频特征", ["补入估值、市值、换手、资金流和主动成交字段。", "生成 30 列新版 daily_pv.h5，增加设置页特征数据查看入口。"]],
      ["修复因子字段替换", ["解决 pe 与 pe_ttm、amount 与资金流字段的名称冲突。", "把修复补到挖掘模板；抽样 10,000 行得到 9,711 条非空值。"]],
      ["修复新增字段重新评估", ["让重新评估读取新版日频 HDF5，避免继续只用旧的七列数据。"]],
      ["排查日志与因子库图表", ["确认长时间无新日志时后台可能正在计算或审计。", "查明有回测产物但图表空白时的页面加载问题。"]],
      ["修复防未来误拒", ["双方结果同为缺失值时跳过该检查点。", "复评问题 5 的六个因子，全部通过审计并完成回测。"]],
      ["完成六组日频特征测试", ["覆盖估值、大/小单、内外盘、换手、市值和价格走势组合。", "共生成 91 个公式、90 个因子值产物；最终一组 15/15 完成审计与回测。"]],
      ["分析因子表现差的原因", ["发现公式同质化、条件过严、零值过多。", "发现零值并列与每日调仓会放大换手和费用。"]],
      ["确定分钟频接入方案", ["明确分钟公式现场计算、按日归约、复用现有审计与 OTO 回测。"]]
    ]],
    ["下一步 · 待完成", [
      ["优化因子生成规则", ["要求新的研究思路，减少只改窗口和阈值的公式。", "回测前筛掉重复和零值过多的候选。"]],
      ["落地分钟频数据接入", ["实现分钟数据读取、日内算子和现场计算。", "输出日频 result.h5，完成防未来与 OTO 验收。"]],
      ["建立 Agent 自动复盘系统", ["自动归纳回测失败原因。", "让复盘结果影响下一轮变异、交叉与系统改进。"]],
      ["完善任务进度和图表反馈", ["显示耗时阶段与运行状态。", "改善图表加载错误提示和产物管理。"]]
    ]]
  ];
  const section = document.createElement("section");
  section.className = "work-checklist";
  section.innerHTML = '<div class="eyebrow">03 / CHECKLIST</div><h2>任务列表</h2><div class="check-groups"></div>';
  const columns = section.querySelector(".check-groups");
  groups.forEach(([period, tasks], index) => {
    const article = document.createElement("article");
    article.className = "check-group " + (index === 1 ? "recent" : index === 2 ? "future" : "");
    const label = document.createElement("div");
    label.className = "check-period";
    label.textContent = period;
    article.append(label);
    tasks.forEach(([title, items]) => {
      const h3 = document.createElement("h3"); h3.className = "task-title " + (index === 2 ? "pending" : "completed"); h3.textContent = title; article.append(h3);
      const ul = document.createElement("ul");
      items.forEach(item => { const li = document.createElement("li"); li.textContent = item; if (index !== 2) li.className = "done"; ul.append(li); });
      article.append(ul);
    });
    columns.append(article);
  });
  results.before(section);
  results.innerHTML = `<div class="eyebrow">04 / DAILY FEATURES</div><h2>日频特征新增结果</h2>
    <div class="stats"><div><strong>30 列</strong><span>新版 daily_pv.h5，覆盖 2018—2025 年</span></div><div><strong>7 组</strong><span>前期落地试跑 1 组 + 后续专项测试 6 组</span></div><div><strong>90/91</strong><span>后续 6 组测试的公式对应因子值产物</span></div></div>
    <div class="daily-story">
      <article><span class="story-no">01</span><h3>把数据接进来</h3><p>从 Mongo 补充估值、换手、市值、资金流和主动成交等字段；新版日频数据约 875 万行、30 列，并在设置页提供特征查看入口。</p></article>
      <article><span class="story-no">02</span><h3>让新字段算得出来</h3><p>两轮测试暴露字段名被短字段误替换的问题。补齐计算入口与挖掘模板后，真实数据抽样 10,000 行得到 9,711 条非空因子值。</p></article>
      <article><span class="story-no">03</span><h3>七组测试逐步跑通</h3><p>前期试跑用于验证新字段能否计算和回测；后续六组共生成 91 个公式、90 个 result.h5。问题 5 的误拒已修复，问题 6 的 15 个因子全部完成审计和回测。</p></article>
      <article><span class="story-no">04</span><h3>问题 4 暴露稀疏信号</h3><p>仅针对问题 4：18 个因子的 IC 中位数约 -0.00137，14 个采用严格条件门控，部分因子绝大多数值为零。零值并列与每日调仓会放大这一组的换手成本；不能推断七组测试都有这个问题。</p></article>
    </div>
    <h3 class="subheading">七组测试：问了什么、看到了什么</h3>
    <div class="test-grid">
      <article><b>落地试跑</b><span>估值 × 主动买卖与大小单资金流</span><p>先后出现字段名替换错误、缺少 result.h5；修复后能计算和回测，NetFlow_Return_Beta_20D 有局部较好指标。</p></article>
      <article><b>问题 1</b><span>低估值 × 大单主动买入</span><p>17 个公式中 16 个生成因子值，另 1 个缺少实现产物。</p></article>
      <article><b>问题 2</b><span>大单与小单资金方向背离</span><p>9 个公式均生成因子值并完成回测，检查金额字段与 amount 共存。</p></article>
      <article><b>问题 3</b><span>净流入 × 外盘成交确认</span><p>18 个因子值产物；17 个完成回测，1 个曾被旧防未来规则拒绝。</p></article>
      <article><b>问题 4</b><span>放量换手后的估值修复</span><p>18 个因子均回测；整体 IC 弱，严格条件造成大量零值。</p></article>
      <article><b>问题 5</b><span>市值约束 × 大单买卖压力</span><p>14 个因子值产物；6 个因缺失值触发误拒，修复后均完成回测。</p></article>
      <article><b>问题 6</b><span>价格走势 × 主动成交背离</span><p>15/15 完成审计与回测，有效值占比 91.74%；有局部指标较好的候选，但未整体过筛。</p></article>
    </div>
    <h3 class="subheading">值得继续研究的两个因子</h3>
    <div class="factor-examples">
      <article><h3>NetFlow_Return_Beta_20D</h3><p>前期落地试跑：IC 0.0231、ICIR 0.237、多空累计差 1.427、扣费超额 Sharpe 2.269。收益分组有区分度，但 IC、ICIR 未过门槛。</p><img src="report_assets/netflow-return-beta-20d-chart-screenshot.png" alt="NetFlow Return Beta 20D 回测页面的十分组累计收益截图"><small>因子库回测页面截图：十分组累计收益（G0 / G9，不含费）。</small></article>
      <article><h3>Activity_Weighted_Mismatch_Duration_5D_20D</h3><p>问题 6：IC -0.0184、ICIR 0.177、多空累计差 0.828、扣费超额 Sharpe 1.016。Sharpe 略高于单项门槛，其他关键指标不足。</p><img src="report_assets/activity-weighted-mismatch-chart-screenshot.png" alt="Activity Weighted Mismatch Duration 回测页面的十分组累计收益截图"><small>因子库回测页面截图：十分组累计收益（G0 / G9，不含费）。</small></article>
    </div>
    <div class="evidence"><figure><img src="report_assets/image-20261014102423293.png" alt="日频特征落地记录中的设置页截图"><figcaption>特征数据查看页 · 摘自落地记录</figcaption></figure><figure><img src="report_assets/image-20261014133859250.png" alt="前期试跑中 NetFlow Return Beta 因子的页面截图"><figcaption>前期试跑中的代表因子 · 原始页面截图</figcaption></figure><figure><img src="report_assets/image-20261109112003250.png" alt="第六组日频因子测试的原始结果截图"><figcaption>第六组因子测试 · 原始页面截图</figcaption></figure></div>
    <div class="inline-docs"><a href="report_assets/日频特征新增——落地.pdf">查看《日频特征新增——落地》PDF ↗</a><a href="report_assets/日频特征新增——测试.pdf">查看《日频特征新增——测试》PDF ↗</a></div>`;
  next.innerHTML = `<div class="eyebrow">05 / MINUTE DATA</div><h2>分钟频数据接入方案</h2>
    <p class="intro">用分钟行情研究日内价格和成交结构，但最终仍生成日频因子，按现有低频评估链路检验。</p>
    <div class="minute-flow"><div><b>01 · 读取</b><span>只读 Mongo 的分钟行情；按股票、交易日分批取数据，检查重复、缺失和交易时点。</span></div><div><b>02 · 现场计算</b><span>候选公式决定读取哪些字段和时间段；用分钟算子计算早盘、尾盘、波动、量价关系等。</span></div><div><b>03 · 日频归约</b><span>每股每天收成一个因子值，再按日期和股票与估值、市值等日频字段组合。</span></div><div><b>04 · 审计与回测</b><span>写入日频 result.h5；检查分钟与日频的前视偏差，再沿用 OTO 回测。</span></div></div>
    <div class="minute-notes"><article><h3>数据与存储</h3><p>以 min_1 为基础粒度。Mongo 保留分钟原始数据；前一交易日的分钟 K 线在次日上午 10 点获取。QuantaAlpha 按交易日读取，在内存中计算并释放中间结果；本地主要保存公式、日频因子值和评估产物。</p></article><article><h3>公式怎样组合</h3><p>分钟部分先算出日内结果，日频部分再与 PE、市值、换手等字段组合。分钟算子使用 M_ 前缀，避免把“20 分钟”和“20 个交易日”混淆。</p></article><article><h3>交易时间约束</h3><p>09:30 条对应开盘价，15:00 条对应 (14:59, 15:00] 的交易数据。t 日完整分钟数据形成的 F(t)，最早用于 t+1 开盘；跨日价格比较采用当时可得的复权因子。</p></article><article><h3>落地与验收</h3><p>先做全市场分钟数据质量扫描；再实现读取、日内算子、公式解析与结果归约；最后验证人工样例、重复运行一致性、截断审计和 OTO 回测。</p></article></div>
    <div class="inline-docs"><a href="report_assets/分钟频数据接入方案_讨论记录已确认_2026-11-11.pdf">查看完整《分钟频数据接入方案》PDF ↗</a></div>`;
  results.querySelectorAll(".evidence img").forEach(img => {
    const link = document.createElement("a");
    link.href = img.src;
    link.target = "_blank";
    link.setAttribute("aria-label", "打开原始截图");
    img.replaceWith(link);
    link.append(img);
  });
});
