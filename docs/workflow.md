# GoalForge — 预测流程与设计 (Prediction Workflow & Design)

> 本文是 GoalForge 的核心设计文档：从两队**首发名单**出发，预测**最终比分 + 每个进球的射手 + 助攻者**。
> 内容综合了一轮对数据源 / 统计比分模型 / ML-DL / 球员级进球助攻 / 比赛仿真的调研。
> 完整的论文、仓库、数据集 URL 清单见**本地**（不纳入 git 的）`Literature Review/literature review.md`，
> 留作逐条核实之用。

---

## 0. TL;DR — 一页总览

**核心架构 = 两层模型 + 蒙特卡洛仿真（two-layer + Monte-Carlo）：**

1. **团队层 (team / scoreline layer)** — 由两队首发、教练、近况，估出两队的期望进球率 `λ_home, λ_away`，
   并给出**完整比分概率矩阵**。骨干模型：**Dixon-Coles / bivariate-Poisson**（工程基线，`penaltyblog` 现成），
   世界杯这种稀疏数据则用 **Bayesian 分层 Poisson（Baio-Blangiardo）**做收缩。
2. **球员层 (player / allocation layer)** — 在给定某队进球数 `G` 的条件下，用 **multinomial / Dirichlet-multinomial**
   按每名球员的「得分权重」`w_i = xG90_np,i × 上场时间占比`把进球分配到个人；点球单独成一条通道；
   每个进球再按 `xGA90`（+「谁喂给谁」网络）抽出助攻者。
3. **蒙特卡洛 (Monte-Carlo)** — 把上面两层包进 `N = 10^4–10^7` 次模拟里，聚合得到：精确比分分布、1X2、
   大小球，以及**每名球员的 anytime / first 进球概率与助攻概率**——全部内部自洽。

**输入 → 输出：** 两份 11 人首发（+ 教练 + 各球员近 ~3 年表现）→ 比分分布、最可能比分、每队 top-k 射手概率、助攻者概率。

**关于 GPU 的诚实结论：** 统计比分模型、GBDT、VAEP/xT、球员分配的解析式都是 **CPU 秒级**就够，**不需要 GPU**。
GPU 真正有价值的地方是：①**大规模向量化蒙特卡洛**（10^6+ 次/场，`torch.distributions` 上 CUDA）；
②**表示学习层**——lineup 图神经网络（HIGFormer 式）、事件序列 Transformer（Seq2Event/EventGPT）、
分位置 GRU；③**大规模分层 Bayesian**（NumPyro/JAX，含球员随机效应）。先用 CPU 把可靠基线跑通，再用 GPU 做表示学习这层增益。

**先做世界杯 (Phase 1)，再泛化到任意俱乐部/联赛比赛 (Phase 2)。**

---

## 1. 问题定义 (Problem Definition)

- **输入：** 两队首发 11 人（理想含替补与教练）；每名球员近 ~3 年的逐场/逐赛季表现；两位教练的执教战绩。
- **预测目标 (features)：**
  1. **最终比分** scoreline（例如 2–1），以及 1X2 / 大小球等衍生概率；
  2. **每个进球的射手** goal scorer；
  3. **每个进球的助攻者** assist provider（若有）。
- **为什么是「分层」问题：** 「打进几个」(team layer) 和「谁打进」(player layer) 是两个不同粒度的问题。
  先定总数、再分配到人，能保证射手数之和恒等于球队进球数（内部自洽），也便于分别建模与校准。
- **泛化路径：** 只要能拿到两队首发，同一套架构对俱乐部比赛同样适用；世界杯只是「数据稀疏 + 中立球场」的特例。

---

## 2. 数据来源 (Data Sources)

> ⚠️ 三个会直接影响选型的关键事实（2026 年中核实）：
> 1. **FBref 在 2026-01-20 失去了 Opta 高级数据源** —— xG/xA/progressive 等高级指标**对新比赛不再更新**（历史存量还在）。FBref 已不是实时 xG 来源。
> 2. **FBref 明确禁止把其数据用于训练 AI 模型**（"training, fine-tuning, prompting… AI models"）→ 训练数据请用 StatsBomb / Understat / CC0 数据集。
> 3. **没有任何免费 API 提供「预测首发」(predicted XI)** —— API-Football / football-data 只在开球前 ~20–60 分钟给**已确认**首发。赛前预测首发要么自建模型，要么买（Sportmonks）。

### 2.1 主要数据源对比（精简版，完整见 Literature Review）

| 来源 | 提供什么 | 粒度 | 世界杯/国家队 | 免费? | 接入方式 | 许可要点 |
|---|---|---|---|---|---|---|
| **StatsBomb Open Data** | 事件流（含 **xG**、传球→助攻、shot freeze-frame、**360**）、首发、阵型 | 球员-动作级 | **强**：男足 WC 1958–2022、Euro 2020/24、Copa 2024、AFCON 2023、WWC 2019/23 | ✅ | `statsbombpy` (v1.20.0, 活跃) | 非商业研究 + **必须署名 StatsBomb** |
| **Understat** | 射门级 **xG / xA / xGChain** | 球员/球队/射门 | ❌ 仅俱乐部 | ✅ | `understatapi` / `soccerdata` | 无明文 ToS，礼貌抓取 |
| **FBref / Opta** | 赛季+逐场统计、首发、教练页 | 球员/球队 | ✅ | scrape via `soccerdata`/`ScraperFC`（**≤10 req/min**） | **禁止 AI 训练**；高级指标已冻结 |
| **Transfermarkt** | 身价、转会、伤停、**教练任期/战绩**、首发 | 球员/球队/**教练** | ✅ | CC0 数据集 `davidcariboo/player-scores`（每周更新） | 用 CC0 快照低风险 |
| **API-Football** | 赛程、**首发(XI+阵型+教练)**、实时、统计 | 球员/球队 | ✅ | REST，免费 100/天；Pro $19/月 | 首发仅开球前 ~20–40 min |
| **football-data.org** | 赛程/比分/积分/射手 | 球队/比赛 | ✅（WC+Euro 在免费 12 项内） | ✅（首发需付费 Deep Data €29/月） | 标准 API ToS |
| **Opta / Wyscout / Sofascore** | 专业事件 + 追踪数据 | 球员/球队 | ✅ | 企业合同 / 非官方抓取 | 学术预算基本不现实 |

### 2.2 现成数据集（Kaggle 等，多为 CC0，适合训练）

- **martj42 — International results 1872→今**（`results.csv` + **`goalscorers.csv`** + 点球大战，~49k 场，**CC0**）：国家队比分与射手标签的主力。
- **Fjelstul World Cup Database**（27 张表：球员/**教练**/裁判/阵容/进球/换人，WC 1930–2022）：世界杯阶段的教练与事件标签。
- **stefanoleone992 — FIFA 15–23 球员属性**（110 项属性 + 教练 + 球队，**CC0**）：静态「技能」特征。
- **hugomathien — European Soccer Database**（11 联赛 2008–16，含含坐标的阵容与赔率，ODbL）。
- **davidcariboo — Transfermarkt player-scores**（appearances/valuations/lineups/transfers/national_teams，**CC0**，每周更新，含 WC 2026 名单）。

### 2.3 关键 Python 工具链

`statsbombpy`（StatsBomb 数据）· `socceraction`（**SPADL + VAEP + xT**，球员动作价值）· `soccerdata` / `ScraperFC`（FBref/Understat/Sofascore/Transfermarkt 抓取）· `penaltyblog`（**Dixon-Coles / bivariate-Poisson / Bayesian / Elo·Massey·Colley·Pi + 去水位赔率 + RPS**）· `kloppy`（多源事件标准化）· `mplsoccer`（可视化）。
> `worldfootballR`（R）已于 2025-09-18 **归档停维**，除非必须用 R，否则首选上面的 Python 栈。

### 2.4 首发与教练数据怎么拿

- **历史首发（训练用）：** StatsBomb `sb.lineups()` + Fjelstul 阵容 + Transfermarkt `game_lineups`（CC0）。
- **即将开赛的首发：** API-Football `/fixtures/lineups`（XI + 阵型 + **教练**）或 Sofascore 抓取——**开球前 ~20–60 min**。
- **赛前「预测首发」：** 免费 API 没有；需自建「最可能首发」启发式（近 N 场出场 + 伤停）或付费 Sportmonks。
- **教练战绩：** 标准做法 = 把教练**任期日期区间**（Transfermarkt / Fjelstul）按日期 **join** 到比分流上，再算滚动 PPG/近况。

### 2.5 合规（在 Great Lakes 上训练时）

①任何对外产出**署名 StatsBomb**、仅非商业；②**不要用 FBref 数据训练模型**——FBref 仅做探索/历史分析，训练用 StatsBomb/Understat/CC0；③所有抓取限速、优先用 **CC0 Kaggle 快照**；④Understat/Transfermarkt/Sofascore 抓取属 ToS 敏感，缓存为主。

### 2.6 数据流与存储 (Data flow & storage)

**当前不使用任何数据库，也没有 Supabase。** 数据是「**按需拉取 → 本地文件缓存 → 内存计算**」，
这最贴合 HPC：数据留在 Great Lakes 文件系统（大文件放 `/scratch` 或 Turbo），零外传、免费、快。

```
[数据源]                              [加载器]                 [规范化中间表 canonical frames]
StatsBomb 开放数据 (HTTP/git)  ─┐
Kaggle CC0 (martj42/Fjelstul) ─┼─►  data/statsbomb.py  ──►   matches      (比分标签)
API-Football (未来: 实时首发)  ─┘    data/synthetic.py         appearances (谁上场 / 分钟)
                                     (可插拔 loader)           goals       (射手 / 助攻 / 分钟)
                                          │
                                          ▼  缓存 (Parquet)
                                     data/raw/*.parquet          ← git 忽略, 只在本地
                                          │
                                          ▼  features/  特征工程
                        球员 per-90 得分/助攻率(+收缩) · 球队强度 · 教练效应
                                          │
                                          ▼  models/  拟合
                        DixonColesModel(attack/defence/home/rho) · PlayerRatings
                                (可 pickle 到 models/*.pkl 复用)
                                          │
                                          ▼  simulation/ + prediction/
                        Monte-Carlo  ──►  MatchPrediction (比分/射手/助攻概率)
                                          │
                                          ▼  reports/  或  Web 前端 (Streamlit)
                                    JSON / 图表 / 交互页面
```

**磁盘布局**（`data/`、`models/` 内容都已 git 忽略；见 `.gitignore`）：

| 位置 | 放什么 | 说明 |
|---|---|---|
| `data/raw/` | 原始拉取的缓存（StatsBomb Parquet 等） | 首次拉取后缓存，之后**秒开**、免网络 |
| `data/interim/`, `data/processed/` | 清洗表 / 特征表 | Parquet |
| `models/` | 拟合好的模型工件（`*.pkl`） | 供预测 / 服务复用（下一步接入） |
| `reports/` | 预测输出、图 | |
| `/scratch/<acct>/…` 或 Turbo | 大文件 / 全联赛事件数据 | 不放 `$HOME` / git |

**Phase 0 现状：** 合成数据按种子在内存生成（不落盘）；StatsBomb 经 `statsbombpy` 按需 HTTP 拉取，
**首次组装后缓存为 `data/raw/*.parquet`**（第二次秒开）；模型在内存拟合（尚未固化到 `models/`，下一步加）。

**要不要上 Supabase / 数据库？**
- **研究 / 单机阶段：不需要。** 本地 Parquet +（可选）DuckDB 足够，且符合 HPC「数据不出集群」原则。
- **将来做可部署的多用户 Web 站点时**：可考虑 **Supabase(托管 Postgres)** 或自建 Postgres，存缓存数据、
  模型工件、历史预测、用户输入——但那是 Streamlit 验证之后、上 FastAPI + 前端那一步的事；在此之前引入云 DB 属于过度设计。

### 2.7 部署用的真实 2026 世界杯数据 (deployed 2026 build)
线上 demo(Vercel)预测**真实的 48 队 2026 世界杯**,三个真实来源合成一个 `api/model.json`:
- **名单 + 球员数据**:`scripts/scrape_wc2026.py` 爬 Wikipedia「2026 FIFA World Cup squads」,
  拿到 48 队官方 26 人名单,每人含**位置、国家队出场数(caps)、国家队进球数(goals)、俱乐部**。
- **球队强度(比分层)**:沿用已验证的 Dixon-Coles checkpoint(martj42 国际赛,有留出回测)。48 队队名与 martj42 完全匹配。
- **射手率**:每名球员**真实的国际赛 goals/caps**,按位置先验做经验贝叶斯收缩(K=8 caps),避免低出场数噪声。
- **助攻率**:**位置先验估计**(无公开国际助攻数据)——如实标注为最弱的一层。
- **首发 XI**:各位置按 caps 最高填 4-3-3(启发式,可在 UI 手动改)。
- **主客场**:默认中立;仅东道主 **美/加/墨** 有主场优势(`meta.hosts`,前端自动处理)。

诚实边界:**只有球队层在真实赛果上回测过**;射手/助攻层是历史/先验驱动,未在 2026 赛果上验证。构建脚本:`scripts/build_wc2026_model.py`。

---

## 3. 特征工程 (Feature Engineering)

把「原始历史」转成模型输入，核心是**把每名球员变成一组可加的强度数字**：

- **球员动作价值评分（最高杠杆）：** 用 `socceraction` 在 StatsBomb 事件上跑 **SPADL → VAEP / xT**，
  得到每名球员**进攻 / 防守**的 per-90 评分。这是让模型「认得首发是谁」的关键，也是 *Betting the system*(2022) 那篇
  「单纯按位置堆球员统计几乎打不过球队级基线」的破解之道——要用 VAEP/xT/embedding 这类**球员价值**特征。
- **得分 / 创造率：** `xG90_np`（非点球 xG/90，最稳的得分率估计）、`shot_rate90`、`xGA90`（被助攻 xG/90）。
- **时间衰减 (recency)：** 对历史按 `φ(t)=exp(−ξ·t)` 指数衰减；半衰期 = `ln2/ξ`。`ξ` 由**样本外**预测分数调，而非 MLE。
- **小样本收缩 (empirical Bayes)：** 上场时间不均时，把球员自身率向**位置先验**收缩（Gamma-Poisson / Beta），
  对世界杯尤其重要。
- **球队强度聚合：** 球队 attack/defense = 首发 11 人评分之和（按预计上场时间加权，含替补修正）。
- **教练效应：** 每位教练一个 attack/defense 偏移项（log 空间可加）。
- **对手调整、主场：** 对手防守强度作为乘性因子；中立球场（世界杯）关掉主场项。
- **静态技能特征（可选）：** FIFA 属性（CC0）、Transfermarkt 身价。

---

## 4. 系统架构 (Architecture)

```
两份首发(22 人) + 教练 + 近 3 年历史
        │
        ▼
[A] 团队层  TEAM LAYER —— lineup-aware Dixon-Coles / bivariate-Poisson / Bayesian 分层
    • α,β = 首发球员 attack/defense 评分之和 (+ 替补修正) + 主场 γ + 教练效应 + 时间衰减 φ(t)
    • 输出 λ_home, μ_away；各自再拆成「运动战 open-play」+「点球 penalty」两部分
        │
        ▼
[B] 蒙特卡洛  MONTE-CARLO  (N = 10^5–10^7 次，GPU 上批量 torch.distributions)
    每次模拟:
      1. 抽两队进球数 (G_home, G_away)  ← 可用 DC/bivariate 联合分布制造相关
      2. 运动战射手 ~ Dirichlet-Multinomial(G_open, α_i = κ·w_i),  w_i = xG90_np,i × 上场占比   ← 球员得分层
      3. 点球进球 → 指定主罚者 (pen_share, 转化率 ≈0.76)
      4. 每个进球: 是否被助攻?(球队助攻率) → 助攻者 ~ Multinomial(权重 ∝ xGA90_j × 上场占比 × A[j→射手])  ← 助攻层
      5. (可选) 进球打点时间 → 时序最早的进球 = first scorer；换人窗口外的球员权重=0
        │
        ▼
[C] 聚合  AGGREGATE —— 精确比分 & 1X2 & 大小球；每名球员 anytime/first/梅开二度概率；
                       每名球员助攻概率；联合 (射手×助攻) 概率(scorecast)
```

> 开源对照：**0xNadr/wc2026** 就是这一思路的公开实现（PyMC NUTS 拟合分层 Dixon-Coles bivariate-Poisson，
> 50,000 次赛事 rollout，输出**每名球员 xG 与金靴概率**）；**HIGFormer** 论文则是「球员节点→球队池化→对比→胜负」的图模型，
> 几乎就是本项目可探索的 GPU 架构。

---

## 5. 团队层：比分引擎 (Team Layer — Scoreline Models)

所有候选最终都吐出同一个对象：**比分概率矩阵 `M[x,y]`**，可求和得 1X2 / 大小球 / 精确比分，或采样模拟。

### 5.1 候选模型与优劣

| 模型 | 怎么算比分 | 优点 | 缺点 | 是否需要 GPU |
|---|---|---|---|---|
| **独立 Poisson (Maher 1982)** | 两个 Poisson PMF 外积 | 极简、可解释、强基线 | 低比分/平局拟合差（0-0、1-1 偏少） | 否 |
| **Dixon-Coles (1997)** ⭐ | 外积 + 对 {0,1}×{0,1} 四格做 τ 修正 + 时间衰减 | 修正低比分；自适应近况；`penaltyblog` 现成、毫秒级 | 仍是 Poisson 边际；τ 只动 4 格；单一全局主场 | 否（拟合）；MC 采样可上 GPU |
| **Bivariate Poisson (Karlis-Ntzoufras 2003)** | 共享项 λ₃ 的联合 PMF | 显式建模正相关；嵌套独立 Poisson | **只能正相关**；常欠拟合平局（需 diagonal-inflated 变体） | 否 |
| **Bayesian 分层 Poisson (Baio-Blangiardo 2010)** ⭐稀疏首选 | 后验预测采样得比分分布 | **部分池化/收缩**——专治世界杯每队 3–7 场的稀疏；天然量化不确定性；**最适合加球员/教练随机效应** | 比 MLE 慢；需 MCMC 调参；极端队会过度收缩（用 mixture 缓解） | 大模型（多联赛+球员效应）可用 NumPyro/JAX |
| **ML-λ (CatBoost/XGBoost) → Poisson** | GBDT 预测 λ，再过 Poisson/DC 成矩阵 | **表格数据 SOTA**（CatBoost+pi-ratings RPS≈0.1925）；吃异构特征 | 需要好的评分/特征工程；小样本易过拟合 | 比赛级数据（<~5万场）**GPU 无意义** |
| **Dixon-Robinson (1998) 出生过程** | 强度随**时间+当前比分**变化的点过程 | in-play / 首发进球**时序**的正解；适合直播改价 | 参数多、需进球分钟数据 | 逐分钟前向模拟可上 GPU |
| **Skellam（净胜球回归）** | 只建模 X−Y | 1X2 / 让分极简稳健 | **给不出完整比分** → 不能当骨干 | 否 |
| **评分系统 (Elo / pi-ratings / TrueSkill / Bradley-Terry)** | 评分差 → 期望进球 → Poisson | 稀疏下稳健；做**特征/先验**极佳；World Football Elo 自带中立场&重要性加权 | 本身不直接出比分；需「评分→进球」桥接 | 否 |

### 5.2 怎么把首发 + 教练「塞进」attack/defense

在 log 空间做可加调整（核心公式）：

```
log λ_home = home + ( α_team_home + Σ_{p∈XI_home} attack_p + coach_home ) + ( β_team_away + Σ_{p∈XI_away} defence_p )
log μ_away =        ( α_team_away + Σ_{p∈XI_away} attack_p + coach_away ) + ( β_team_home + Σ_{p∈XI_home} defence_p )
```

- 球员 `attack_p / defence_p` 来自 VAEP/xT 聚合，并相对「该队平均首发」做差。
- Bayesian 版把球员、教练都做成**分层随机效应**，自动收缩——球员级信号更稀疏，收缩更重要。
- 世界杯：国家队事件数据薄，球员主要用**俱乐部赛季**评分刻画，再加总进国家队首发强度。

### 5.3 推荐（团队层）

- **稀疏国际/世界杯首选：Bayesian 分层 Poisson（+ Dixon-Coles τ 低分修正 + 轻度时间衰减 + 中立场关主场）。**
  收缩天然适配每队 3–7 场，后验预测给出**带不确定性**的比分分布，也是塞 lineup/coach 效应最干净的地方。
  起步用 `footBayes`(R/Stan) 或 PyMC（移植其 rugby 分层例子），放大到含球员随机效应时转 **NumPyro（GPU）**。
- **工程基线 / 俱乐部泛化：penaltyblog 的 Dixon-Coles（+ bivariate-Poisson）**，毫秒级、现成 `FootballProbabilityGrid`；
  用 **World Football Elo / pi-ratings** 作先验/特征喂进去。
- **Skellam / Bradley-Terry / 裸 Elo 不当骨干**（给不出完整比分），只作特征、先验与 1X2 交叉验证。

---

## 6. 球员层：进球与助攻分配 (Player Layer)

### 6.1 单人进球（博彩 anytime / first 的算法）

给某球员本场期望进球率 `λ_player`，则：

```
P(该球员至少进 1 球) = 1 − e^(−λ_player)
λ_player = xG90_np × (预计上场分钟/90) × 对手防守因子  +  点球通道(λ_pen)
λ_pen    = P(本队获点) × 点球转化率(≈0.76) × 该球员主罚份额
```

> 例：Haaland 满场打弱旅，λ_np≈0.85、λ_pen≈0.15 → λ≈1.0 → P(anytime)=1−e^−1≈**63%**；替补登场打强旅则塌到 ~18%。
> 说明**上场时间、对手强度、点球权**主导输出。**first scorer** 由蒙特卡洛里「时序最早进球」直接得到，最干净。

### 6.2 把球队进球数分配到个人（核心公式）

给定某队模拟出的整数进球数 `G`，给每名在场球员一个**得分权重** `w_i`，归一后：

```
p_i = w_i / Σ_j w_j ,   w_i = xG90_np,i × (上场分钟_i/90)        # 运动战权重；点球单独通道
(各球员进球数) ~ Multinomial(G_open, p)
```

**Dirichlet-Multinomial（加收缩/过散，推荐）：** 给份额向量加 Dirichlet 先验，浓度 `κ` 控制对小样本球员的收缩强度，
每次模拟重抽 `p` 也把份额不确定性注入到 anytime 概率里：

```
(p_1..p_N) ~ Dirichlet(α_i = κ · m̄_i)  →  (scorers) ~ Dirichlet-Multinomial(G_open, α)
```

**点球**永远单独成一条通道、只给指定主罚者——否则会污染整条首发的运动战份额。

### 6.3 助攻（xGA + 「谁喂给谁」）

对每个已判定的进球（射手 s）：
1. **是否被助攻？** 按球队**被助攻率**（运动战进球约 75–80% 被助攻；点球/单刀补射不算）抽 Bernoulli。
2. **谁助攻？** 在队友中按权重抽样：`P(助攻者=j | 射手=s) ∝ xGA90_j × 上场占比 × A[j→s]`，
   其中 `A[j→s]` 是从 3 年事件里估的**传球→射门网络**（边后卫更常助攻同侧边锋），稀疏对子向位置先验收缩；
   令 `A≡1` 退化为简单「助攻份额」multinomial（v1 足够）。

### 6.4 每名球员需要的参数（"data contract"）

| 参数 | 含义 | 来源 |
|---|---|---|
| `attack_rating`, `defence_rating` | 在场时对球队 λ 的贡献 | 团队层（球员加总 DC）/ VAEP |
| `xG90_np` | 非点球 xG/90 → 运动战权重 w_i | 射门×xG / 分钟 |
| `xGA90` | 被助攻 xG/90 → 助攻权重 | 关键传球→射门 xG / 分钟 |
| `expected_minutes` | 首发/替补/轮换预计分钟 → 上场占比 | 首发 + 轮换模型 |
| `position` | 先验份额 + 收缩目标 | 首发 |
| `pen_taker`, `pen_share`, `pen_conversion` | 点球权与转化(≈0.76) | 定位球数据/历史 |
| (队级) `assisted_goal_rate` | 进球被助攻概率(≈0.78) | 联赛/球队 |
| (队级) `A[j→s]` | 传球→射门网络（可选，收缩） | 助攻事件网络 |
| (队级) `goal_time_profile` | 进球分钟分布（first scorer/换人用） | 联赛计时数据 |
| (全局) `ρ, ξ, κ` | DC 相关 / 衰减率 / Dirichlet 浓度 | MLE / 交叉验证 |

---

## 7. 蒙特卡洛仿真 (Monte-Carlo)

- **主循环**：见 §4 的 [B]。每次模拟独立、每步都是张量抽样 → 整体是一个**批量 GPU kernel**，
  `[Nsims]` 个比分 + `[Nsims × Nplayers]` 个 multinomial 分配并行抽。10^6+ 次/场可在亚秒级跑完，
  让稀有事件（帽子戏法、精确 4-3）的尾部更平滑。**这是本项目最正当的 GPU 蒙特卡洛用法。**
- **聚合输出**：精确比分频率、1X2、大小球；每名球员 anytime / first / 梅开二度；每名球员助攻；联合 (射手×助攻)。
- **赛事树（世界杯）**：小组循环 + 淘汰赛 → 对整张签表蒙特卡洛；淘汰赛加时（λ 按 ~30/90 缩放）、点球大战（近 ~50/50）。

---

## 8. 训练、评估与回测 (Evaluation & Backtesting)

- **标签**：比分（martj42 / StatsBomb）、射手与助攻（StatsBomb 事件 / goalscorers.csv / Fjelstul）。
- **划分**：严格**时间序 walk-forward**（按日期滚动重训），杜绝泄漏。
- **指标**：1X2 用 **RPS**（业界标准）+ log-loss + 校准 **ECE**；比分/射门用 Brier；
  射手/助攻用 **top-k 命中率**与 anytime 概率校准。
- **基线**：必报**博彩去水位赔率**、Elo/pi-ratings、均值基线。
- **诚实的天花板**：W/D/L 现实准确率约 **52–55%**（博彩 ~51.9–54%；最好 ML CatBoost+pi RPS 0.1925）。
  **任何明显更高的数字先怀疑数据泄漏/过拟合**（平局最难，~29% 命中）。

---

## 9. GPU 用在哪 (Where the GPU Earns Its Keep)

| 组件 | GPU 结论 |
|---|---|
| Dixon-Coles / Poisson / bivariate 拟合、RF/LogReg/GBDT(比赛级)、VAEP/xT 计算、xG、射手 multinomial 解析式 | **不需要**——CPU 秒级 |
| xG 模型 | 仅当把事件汇成 10^5–10^6 射门才有意义 |
| **大规模向量化蒙特卡洛 (10^6+/场)** | **真有用**（CUDA 批量抽样） |
| **lineup 图神经网络 (HIGFormer 式)** | **真有用/需要** |
| **事件序列 Transformer (Seq2Event / EventGPT) 做球员/阵容 embedding** | **必需** |
| **分位置 GRU/LSTM 近况序列模型** | **有用** |
| **大规模分层 Bayesian（含球员随机效应，NumPyro/JAX）** | **有用** |
| 事件级生成式整场仿真器（训练） | **必需** |

**策略：先 CPU 把「GBDT/Poisson + VAEP/xT + 射手 multinomial」可靠基线跑通；GPU 用来做表示学习层（lineup GNN / 事件 Transformer），正是 DL 与 GPU 真正发挥的地方，也直接服务于「把进球/助攻归到个人」这个独特目标。**

---

## 10. 候选模型汇总：成熟 vs 值得探究 (Mature vs Exploratory)

### A. 成熟、先做（CPU 足够、可靠可解释）
1. **团队层**：Dixon-Coles / bivariate-Poisson（`penaltyblog`），或世界杯用 Bayesian 分层 Poisson。
2. **球员特征**：`socceraction` 的 VAEP/xT → 每名球员攻防 per-90 评分。
3. **球员层**：Dirichlet-Multinomial 射手分配 + 点球通道 + xGA 助攻层。
4. **整合**：GPU 向量化蒙特卡洛输出全部概率。
5. **基线**：CatBoost+pi-ratings、Elo、Logistic、博彩赔率（用 RPS 做诚实评测）。

### B. 探索、值得研究（GPU 名正言顺）
1. **lineup 图神经网络（最贴合目标）**：仿 **HIGFormer** —— 11 个球员节点（特征=近 3 年 VAEP/xT）→ GAT/图 Transformer →
   注意力池化成球队向量 → 两队对比 → 同时出「进球数」与「射手/助攻 logits」。可借鉴 **TacticAI** 的等变思想。
2. **球员 embedding 预训练 → 阵容池化**：football2vec(CPU) 或 **EventGPT / Seq2Event 事件序列 Transformer(GPU)**，
   后者天生预测「下一个动作是谁做的」，与射手/助攻预测同源。
3. **分位置 GRU/LSTM 近况序列**（SoccerNet 式，曾在一项研究里反超 XGBoost）。
4. **TabPFN**：小样本表格基础模型，<1 万行零调参常追平调过的 XGBoost，值得一跑。
5. **事件级生成式整场仿真**（Seq2Event / Large Events Model / Foundation Model for Soccer）：最高拟真，作长期研究线。
6. **大规模分层 Bayesian + 球员随机效应（NumPyro/JAX）**：把不确定性贯穿到底。

---

## 11. 路线图 (Roadmap)

- **Phase 0 — 数据 + 基线**：拉 StatsBomb 世界杯数据；`penaltyblog` Dixon-Coles 跑出比分矩阵；建立 RPS 回测与博彩基线。
- **Phase 1 — 首发感知 + 球员层**：`socceraction` 算 VAEP/xT → 球员评分进 λ；加 Dirichlet-Multinomial 射手分配 + 点球通道 + xGA 助攻；GPU 蒙特卡洛出全套概率。
- **Phase 2 — Bayesian 分层 + 教练效应**：收缩稀疏国家队；球员/教练随机效应；中立场处理；赛事树仿真。
- **Phase 3 — GPU 表示学习**：lineup GNN（HIGFormer 式）/ 事件序列 Transformer；与基线集成。
- **Phase 4 — 泛化**：从世界杯扩到任意俱乐部/联赛（数据切到 Understat/FBref 历史/Transfermarkt）。

---

## 12. 风险与陷阱 (Risks & Caveats)

- **小样本过拟合**：世界杯每队场次极少、阵容更替大 → 必须收缩 + walk-forward，**别把过拟合数字当真实性能**。
- **「按位置堆球员统计」可能打不过球队级基线**（*Betting the system* 2022 的教训）→ 必须上 VAEP/xT/embedding 这类球员价值特征。
- **平局难、first-scorer 非干净 Poisson**：需要进球时序结构与游戏状态相关率。
- **数据合规**：StatsBomb 非商业 + 署名；**FBref 禁止 AI 训练**；抓取限速。
- **预测首发缺口**：免费源只有开球前确认首发；赛前预测需自建或付费。
- **数据泄漏**：滚动特征必须只用赛前信息；警惕「未来函数」。

---

## 13. 参考资料 (References)

> **完整的论文 / 仓库 / 数据集 / 教程 URL 清单（含维护状态、许可、一句话点评）见本地 `Literature Review/literature review.md`（不纳入 git，留作核实）。** 下面只列最关键的几项。

- **Dixon & Coles (1997)** Modelling Association Football Scores — JRSS-C 46(2). 比分模型基石。
- **Dixon & Robinson (1998)** A birth process model — JRSS-D 47(3). in-play 时序（注意是 1998，非 2004）。
- **Karlis & Ntzoufras (2003)** Bivariate Poisson — JRSS-D 52(3)。
- **Baio & Blangiardo (2010)** Bayesian hierarchical model for football — *J. Applied Statistics* 37(2)。稀疏首选。
- **Decroos et al. (2019)** VAEP "Actions Speak Louder than Goals" — KDD'19；库 `ML-KULeuven/socceraction`。
- **Karun Singh (2018)** Expected Threat (xT) — https://karun.in/blog/expected-threat.html
- **Groll et al.** World Cup ML（RF + Poisson）；**Constantinou (2019) Dolores**（Bayesian net + ratings）。
- **HIGFormer (2025)** player-team 异构图 Transformer，lineup→胜负——最接近本项目可探索架构。
- **DeepMind TacticAI (2024)** Nature Comms——角球战术图神经网络。
- **Seq2Event (KDD 2022)** / **EventGPT (2025)**——事件序列生成式预测。
- 工具：**penaltyblog**（DC/bivariate/Bayesian/ratings/赔率）、**socceraction**（SPADL/VAEP/xT）、**statsbombpy**、**soccerdata**、**kloppy**、**mplsoccer**。
- 公开整合实现：**0xNadr/wc2026**（分层 DC + 球员级金靴概率）、**FiveThirtyEight SPI**（评分→Poisson→蒙特卡洛，已归档）。
