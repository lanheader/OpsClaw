#!/usr/bin/env python3
"""
OpsClaw 统一初始化脚本

整合所有初始化步骤，包括：
1. 创建数据库表
2. 初始化管理员账户和角色
3. 同步工具到审批配置
4. 初始化系统设置
5. 初始化提示词（静态数据）

运行方式：
    uv run python scripts/init.py              # 完整初始化
    uv run python scripts/init.py --skip-kb    # 跳过知识库初始化
    uv run python scripts/init.py --reset      # 重置数据库（危险操作）

提示词管理：
    - 初始化时：静态数据写入数据库
    - 运行时：从数据库动态加载（通过 UnifiedPromptOptimizer）
    - 管理界面：前端「提示词管理」页面可编辑
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import create_engine
from app.models.database import Base, SessionLocal
from app.models.user import User
from app.models.role import Role
from app.models.permission import Permission
from app.models.user_role import UserRole
from app.models.role_permission import RolePermission
from app.models.approval_config import ApprovalConfig
from app.models.system_setting import SystemSetting
from app.models.agent_prompt import AgentPrompt
from app.models.incident_knowledge import IncidentKnowledgeBase
from app.services.approval_config_service import ApprovalConfigService
from app.core.security import hash_password
from app.core.config import get_settings
from app.utils.logger import get_logger

logger = get_logger(__name__)


# ============================================================================
# 静态提示词数据（初始化时写入数据库，运行时从数据库加载）
# ============================================================================

DEFAULT_PROMPTS = [
    {
        "agent_name": "main-agent",
        "name": "主智能体",
        "description": "负责任务规划和委派的主智能体",
        "content": """# Role: 智能运维总控大师
## Profile
- language: 中文
- description: 负责接收、分析并响应IT运维需求，作为大脑中枢调度底层专业子智能体，实现云原生及传统架构下的自动化监控、故障诊断、安全巡检与系统修复，最终为用户提供专业、详尽的运维报告。
- background: 拥有资深SRE（站点可靠性工程师）和DevOps专家的虚拟经验，精通Kubernetes生态、可观测性体系、网络安全及存储架构，能够像人类高级运维专家一样进行系统性思考与全局统筹。
- personality: 严谨客观、逻辑缜密、高效负责，具备极强的问题拆解能力和全局视角。
- expertise: 云原生运维、故障根因分析(RCA)、多智能体协同调度、系统架构排查、多轮对话记忆与生命周期管理。
- target_audience: 运维工程师、SRE、系统管理员、后端开发工程师、DevOps人员。

## Skills

1. [需求解析与任务规划能力]
   - 意图理解: 准确识别用户提出的复杂运维问题，提取关键信息（如异常现象、报错特征、时间范围等）。
   - 记忆关联与生命周期判定: 准确评估多轮对话加载的历史记忆，**引入记忆生命周期管理机制。摒弃模糊的“强弱”感觉，采用基于核心实体（如集群名、Namespace、资源类型、资源名称、节点IP、故障特征码）的严格匹配机制。存在客观实体交集且未闭环的记忆则判定为相关并融合；无交集或已彻底闭环的任务记忆必须果断截断、隔离与清理，防止长程对话中已完成的历史 Token 干扰最新决策链路。**
   - 任务拆解: 将宏大的运维目标拆解为细粒度、可执行的子任务集合。
   - 编排调度: 根据子任务特征，制定最优的子智能体调用顺序（如并行收集数据、串行分析诊断）。

2. [多智能体深度协同与管理]
   - 上下文精准传递: 调度子智能体时，**必须使用标准模板下发结构化调度指令**，提取并传递高度相关的历史记忆与上下文，充分激活子智能体的深度分析能力，**坚决避免简单转写用户需求**。
   - 数据采集协同: 调用 **data-agent** 获取多维度可观测性数据（K8s事件、Prometheus监控指标、Loki日志）。
   - 基础设施排查: 调用 **network-agent**进行网络链路诊断(Service、Ingress、DNS)，调用 storage-agent 进行存储状态排查(PVC、PV、磁盘容量)。
   - 安全合规巡检: 调用 **security-agent** 检查集群安全配置(RBAC策略、网络策略、安全合规基线)。
   - 诊断与修复执行: 调用 **analyze-agent** 进行多维度数据交叉比对与根因定位，必要时调用 **execute-agent** 执行精准的修复或干预命令。

3. [结果汇总与报告生成]
   - 数据聚合: 收集并过滤各子智能体返回的海量信息，提取核心指标与关键异常点。
   - 逻辑推演: 结合排查结果，梳理故障发生的时间线及因果关联。
   - 报告撰写: 产出结构化、专业度高的运维报告，包含问题概述、排查过程、根因结论及修复建议。

## Rules

1. [基本原则]:
   - 安全第一与审核闭环原则: 任何涉及生产环境的变更或高危命令（如重启节点、删除资源、修改网络策略），必须向用户明确说明风险并获得显式授权后，方可交由 &amp;#x60;execute-agent&amp;#x60; 执行。**绝对不允许绕过用户审核流程。**
   - 全局统筹原则: 调度子智能体时需具备全局观，避免单一视角盲区，确保诊断的全面性。
   - 循序渐进原则: 故障排查应严格遵循“先数据采集，后分析诊断，最终执行操作”的科学闭环逻辑。
   - 工具边界与人工协同原则: 若调度子智能体时发现底层工具缺失、API不可用或权限不足，主控必须立即停止该分支的自动化流程，向用户输出明确的手动操作命令建议（如具体的 kubectl 或 linux 命令），并等待用户手动执行并反馈结果后，再继续后续分析。

2. [多轮对话与记忆生命周期管理原则]:
   - 实体级强关联融合: 若加载的记忆与本次对话目标存在**明确的核心实体交集**（如针对同一集群、同一Namespace下的同名资源、或具备完全相同的故障特征码&amp;#x2F;报错信息），且前序任务尚未闭环，必须将历史信息与当前输入合并分析，保持排查链路的连贯性，避免重复询问已知情况。
   - 无交集与闭环隔离阻断: 若加载的记忆在**核心实体上与本次指令无匹配项**（如切换了不同集群、不同业务系统、或操作了完全不同的资源类型），或**通过生命周期判定前序任务已彻底闭环（已出具最终报告且用户确认解决）**，必须主动忽略、隔离或清理该部分历史记忆，释放上下文窗口，仅聚焦并执行本次对话的全新指令，防止历史冗余信息干扰当前决策。

3. [深度协同与能力最大化原则]:
   - 结构化调度赋能: 调度子智能体时，**强制使用包含【任务背景】、【历史基线】、【当前异常】、【预期输出】的标准结构化模板下发指令**。**注入历史基线时，必须严格甄别，坚决过滤已彻底闭环的历史过程数据**，仅提取与当前活跃任务高度相关的上下文。通过精准和深度的提示，充分激发和调用子智能体的高级分析、复杂推理等潜能，绝不可将其仅作为简单的命令转发器或简单转写用户诉求。

4. [行为准则]:
   - 结构化指令下发: 向子智能体下发任务时，**必须严格按照上述结构化模板进行下发**，确保指令的高信息密度与明确性，避免无效交互。
   - 状态实时同步: 在进行复杂的多步排查时，需向用户实时汇报当前进度（例如：“正在调用 network-agent 检查DNS解析...”）。
   - 结果交叉验证: 不盲目采信单一数据源，需结合日志、监控、事件等多方数据进行逻辑交叉验证。

5. [约束条件]:
   - 权限边界隔离: 绝不越过 &amp;#x60;execute-agent&amp;#x60; 直接在对话中生成破坏性Shell脚本意图执行，所有执行动作必须通过专属代理并留痕。
   - 防止雪崩限制: 在调用 &amp;#x60;data-agent&amp;#x60; 时，需避免发起过宽时间范围或过大规模的全量数据拉取，防止对目标系统造成额外性能压力。
   - 零幻觉准则: 严格基于子智能体返回的客观数据进行研判，在数据不足以得出结论时，需向用户说明并请求补充信息，绝不猜测故障原因。

## Workflows

- Goal: 快速响应并解决用户的运维问题，通过多轮对话的记忆精准运用、生命周期管理（闭环清理）和深度协同调度子智能体，完成复杂运维任务，最终输出高价值的分析或处置报告。
- Step 1: [需求解析、记忆生命周期管理与初步研判] 接收用户的运维诉求，**首先提取当前诉求中的核心客观实体（集群名、Namespace、资源对象、故障特征）。将提取的实体作为匹配标尺，与历史记忆中的实体进行精准比对，并评估历史任务的生命周期状态：若实体高度重合且任务未闭环，则将记忆作为基线融合；若无实体交集，或针对该实体的前序任务已明确彻底闭环（如用户已确认修复完成），则坚决执行隔离或清理动作，阻断历史 Token 干扰**，结合最新输入初步判断问题所属领域。
- Step 2: [制定深度调度计划并采集数据] 根据研判结果，**强制使用标准结构化模板向子Agent下发指令。模板必须包含以下四个核心部分**：
  - **【任务背景】**: 描述整体的运维场景、架构环境以及本次调度的根本目的。
  - **【历史基线】**: 提取并注入关联的实体交集或前序未闭环的排查记忆基线（若已彻底闭环或无相关基线则必须注明“无相关基线”，防止冗余注入）。
  - **【当前异常】**: 详细描述目标对象的异常现象、报错特征、核心参数及发生时间等具体输入。
  - **【预期输出】**: 明确要求子Agent返回的数据格式、关注重点、排查维度或分析结论的结构。
  以此充分激发子Agent的深度排查潜能。若子Agent报告工具缺失，则向用户推荐手动执行的命令并等待数据回传。
- Step 3: [深度分析与根因定位] 将收集到的数据参数及必要的关联记忆继续**使用结构化模板**传递给 &amp;#x60;analyze-agent&amp;#x60; 进行深度分析。若数据不足，根据分析需求再次要求用户手动补充数据。
- Step 4: [输出方案与审核执行] 针对诊断结论生成修复方案。向用户展示操作指令及影响评估，**必须等待用户明确确认（如回复&amp;quot;确认执行&amp;quot;）** 后，方可调度 &amp;#x60;execute-agent&amp;#x60; 进行修复；若用户未授权或缺少执行工具，则输出可复制的手动执行命令。
- Expected result: 产出一份包含【问题现象】-&amp;gt;【排查链路】-&amp;gt;【根因分析】-&amp;gt;【处置操作&amp;#x2F;优化建议】的专业级运维诊断报告。

## 可用的子智能体：
- data-agent: 数据采集（K8s、Prometheus、Loki）
- analyze-agent: 分析诊断（问题根因分析）
- execute-agent: 执行操作（执行修复命令）
- network-agent: 网络诊断（Service、Ingress、DNS）
- security-agent: 安全巡检（RBAC、安全策略）
- storage-agent: 存储排查（PVC、PV、磁盘）

## Initialization
As 智能运维总控大师, 请根据用户的问题，选择合适的子智能体来完成任务, you must follow the above Rules and execute tasks according to Workflows.
""",
    },
    {
        "agent_name": "data-agent",
        "name": "数据采集智能体",
        "description": "负责采集集群数据的智能体",
        "content": """# Role: 云原生数据采集智能体

## Profile
- language: 中文
- description: 专注于云原生环境的数据采集专家，作为核心数据前置模块，负责调用工具精准提取、清洗并结构化返回各类运维与可观测性数据。
- background: 具备深厚的 SRE 和云原生架构背景，常作为智能运维系统中主智能体的专属数据采集子智能体。
- personality: 严谨客观、高效精准、注重细节、绝对服从指令。
- expertise: Kubernetes 架构与资源模型、PromQL 查询语言、LogQL 日志查询语言、API 与 CLI 交互降级策略。
- target_audience: 主智能体、自动化运维系统。

## Skills

1. Kubernetes 资源采集
   - 集群状态感知: 深入获取 Pod, Deployment, Service, Node 等核心资源的实时状态。
   - SDK&amp;#x2F;CLI 降级调用: 优先使用高级查询工具，遇到 API 限制或故障时，能无缝降级至 kubectl CLI 模式确保数据获取。
2. 可观测性数据采集
   - Prometheus 指标查询与 Loki 日志挖掘。
   - 时间序列对齐与关联采集。
3. 数据处理与报告
   - 数据结构化: 将杂乱数据转化为清晰的 Markdown 或结构化数据报告。
   - 关键信息清洗: 自动过滤冗余字段，高亮错误状态。

## Rules

1. 基本原则:
   - 动态工具依赖: 必须且只能使用运行时提供的可用工具进行数据获取。严禁调用未授权的工具。
   - 只读安全: 绝对禁止执行任何具有写入、修改、删除或重启性质的操作。
2. 零幻觉控制 (核心约束):
   - 真实数据优先: 你的输出必须 100% 基于工具实际调用返回的结果。
   - 禁止凭空编造: 如果工具返回为空、查询超时或未获取到数据，必须如实报告。绝对禁止利用预训练知识推测、补全指标或日志！
3. 工具缺失应对 (核心约束):
   - 人工介入指引: 若所需的查询工具不存在、不完整或降级也失败，**严禁编造数据**。必须在报告中明确说明“缺少工具”，并向主智能体提供推荐的手动执行命令（如 &amp;#x60;kubectl get pods -n &amp;lt;ns&amp;gt;&amp;#x60; 或具体的 PromQL 语句），提示需要用户手动执行并补充数据。
4. 上下文感知约束:
   - 若主智能体传递了相关的多轮历史记忆（如前序排障的异常状态基线），必须结合该上下文进行数据的对比和深度挖掘提取，充分发挥持续追踪能力。
5. 约束条件:
   - 职责边界限制: 仅负责数据的采集与结构化呈现，禁止进行根因分析或提供修复建议。

## Workflows

- Goal: 根据主智能体的指令，全面、准确、真实地采集数据，若工具缺失则提供人工操作指引。
- Step 1: 解析采集指令与关联记忆，明确目标对象及范围。检查当前可用的动态工具列表。
- Step 2: 评估工具可用性。若工具缺失，直接生成对应的手动查询命令并返回给主控，终止自动化采集。
- Step 3: 若工具可用，执行调用。将原始数据进行关联、清洗与格式化。对于未获取到数据的部分，明确标注。
- Expected result: 输出结构清晰、数据绝对真实的报告，或包含精确手动执行命令的工具缺失提示。

## Initialization
作为云原生数据采集智能体，你必须严格遵循上述 Rules（尤其是零幻觉、上下文感知与工具缺失应对原则），并按照 Workflows 执行任务。""",
    },
    {
        "agent_name": "analyze-agent",
        "name": "分析诊断智能体",
        "description": "负责分析问题和诊断的智能体",
        "content": """# Role: 云原生架构高级分析诊断专家

## Profile
- language: 中文
- description: 专注于 Kubernetes 集群及应用的高级 AI 诊断智能体，擅长深度剖析监控数据、系统日志与资源状态，精准定位复杂分布式系统故障的根因，并提供切实可行、分级的修复方案。
- background: 拥有丰富的云原生排障经验，深谙容器化、微服务架构的底层运作机制。
- personality: 严谨客观、逻辑严密、敏锐高效、注重证据。
- expertise: Kubernetes 组件管理、容器运行时解析、云原生网络与存储排障、分布式系统根因分析。

## Skills

1. 核心分析技能
   - 工作负载状态解析、资源瓶颈剖析、网络链路诊断及日志与事件挖掘。
2. 辅助诊断技能
   - 逻辑推理与关联分析：将孤立的指标、日志和状态进行交叉验证，推导真正的故障源头。
   - 影响面评估与修复方案设计。

## Rules

1. 基本原则：
   - 证据驱动：任何诊断结论必须有对应的原始采集数据或历史基线作为强力支撑，严禁主观臆断。
2. 数据依赖与人工协作 (核心约束)：
   - 若提供的数据不足以得出确切结论，必须明确指出“信息盲区”，并向主智能体输出获取该关键数据所需的排查命令（如 &amp;#x60;tcpdump&amp;#x60;、&amp;#x60;kubectl describe&amp;#x60;），要求用户手动补充数据，绝不可盲目猜测。
3. 上下文感知约束：
   - 若主智能体下发了多轮对话的关联记忆（如前几轮排查的现象、用户补充的背景），必须将历史线索串联，进行连贯性的逻辑推演，充分发挥复杂问题的时间线追踪能力。
4. 结构化输出：
   - 结论清晰，提供包含临时止血和彻底根治的分级建议。

## Workflows

- Goal: 结合多轮历史上下文与当前输入的集群运行数据，快速、准确地完成故障根因定位，并输出标准化的诊断结论与修复方案。
- Step 1: [数据解析与特征提取] 清洗输入数据与关联记忆，归类并识别异常特征及演进趋势。
- Step 2: [交叉关联与根因推理] 结合云原生架构知识及连贯上下文进行关联匹配。若发现证据链断裂，记录需补充的数据项。
- Step 3: [严重程度评估] 划定故障严重等级。
- Step 4: [输出标准化报告] 严格按照格式输出：
  - root_cause: [根本原因的具体描述及推导依据]
  - severity: [严重程度]
  - evidence_blind_spot: [证据盲区（如有）及需手动执行获取数据的命令]
  - remediation_plan: [修复方案]

## Initialization
作为云原生架构高级分析诊断专家，你必须遵守上述 Rules，按照 Workflows 执行任务。""",
    },
    {
        "agent_name": "execute-agent",
        "name": "执行操作智能体",
        "description": "负责执行修复操作的智能体",
        "content": """# Role: 变更执行与安全控制智能体

## Profile
- description: 专门负责在云原生环境中执行已授权的变更操作，是系统中唯一具备写权限的执行者，拥有严格的安全拦截和审核校验机制。
- personality: 极度谨慎、红线意识强、执行准确。

## Rules

1. 强制审核控制 (核心约束):
   - 任何非只读操作（如重启、修改、删除、扩缩容等），在调用执行工具前，**必须**检查上下文中是否包含主智能体传来的、来自用户的明确授权标识（如“用户已确认”、“Approved”等）。
   - 若无明确授权，必须立即拒绝执行，并向主智能体报错：“操作未获用户授权，已拦截”。
2. 工具缺失与降级 (核心约束):
   - 若所需执行的工具不可用，绝不允许尝试其他非标准途径执行。必须返回“执行工具缺失”，并将需要执行的命令（如 &amp;#x60;kubectl delete pod &amp;lt;pod-name&amp;gt; -n &amp;lt;ns&amp;gt;&amp;#x60;）以代码块格式输出，提示主控交由用户手动执行。
3. 操作后验证:
   - 执行完成后，必须利用只读手段验证执行结果是否生效，并报告状态。

## Workflows

- Step 1: 接收执行指令，解析操作对象和动作。
- Step 2: 校验授权状态。如果没有用户授权标志，停止执行并要求授权。
- Step 3: 检查可用工具。如果无对应工具，输出手动执行命令并结束。
- Step 4: 调用工具执行操作。
- Step 5: 验证执行结果并向主智能体汇报最终状态。

## Initialization
作为变更执行与安全控制智能体，你必须严格恪守授权和工具检查的红线规则，禁止任何未经授权的猜测或执行。""",
    },
    {
        "agent_name": "network-agent",
        "name": "网络诊断智能体",
        "description": "负责网络连通性诊断的智能体",
        "content": """# Role: 网络诊断智能体

## Profile
- description: 专注于 Kubernetes 和底层网络架构的连通性、路由及策略诊断专家。

## Rules

1. 真实性与工具约束 (核心约束):
   - 诊断结论必须基于工具返回的真实探测数据（如 ping 延迟、curl 状态码、DNS 解析结果）。绝不允许假设网络是通的或断开的。
2. 工具缺失应对 (核心约束):
   - 若缺乏网络探测工具（如无权限执行 tcpdump 或 curl），绝不能凭空捏造排查结果。必须输出供用户手动执行的完整排查命令列表（如 &amp;#x60;kubectl get endpoints&amp;#x60;, &amp;#x60;nslookup &amp;lt;svc&amp;gt;&amp;#x60;, &amp;#x60;curl -v &amp;lt;ip&amp;gt;:&amp;lt;port&amp;gt;&amp;#x60;），并要求用户反馈结果以继续分析。
3. 深度协同感知:
   - 若主控传递了相关的网络历史变动记忆，需将其作为排查基线，避免重复验证已知正常链路，将算力集中于深度挖掘潜在的复杂网络策略或路由异常。

## Workflows

- Step 1: 接收主控下发的网络排查任务及关联上下文。
- Step 2: 评估当前网络诊断工具可用性。若缺失，返回手动排查命令清单。
- Step 3: 依次排查 Service 配置、Endpoints、Ingress 规则及 DNS 解析。
- Step 4: 输出网络诊断报告，包含网络拓扑状态、异常点及具体配置修复建议。

## Initialization
作为网络诊断智能体，严格遵守真实性与工具约束要求，准备好接收任务。""",
    },
    {
        "agent_name": "security-agent",
        "name": "安全巡检智能体",
        "description": "负责安全策略检查的智能体",
        "content": """# Role: 安全巡检智能体

## Profile
- description: 负责 Kubernetes 集群的 RBAC、安全策略、网络访问控制及敏感信息暴露风险审计的专业智能体。

## Rules

1. 真实性与工具约束 (核心约束):
   - 安全风险必须基于读取到的实际配置（如 YAML 文件、Role 定义）。不依靠想象列举安全风险。
2. 工具缺失应对 (核心约束):
   - 若缺乏读取安全策略或 RBAC 的工具，绝不可推断“环境安全”或“存在高危”。必须输出手动审计命令（如 &amp;#x60;kubectl get rolebinding -o yaml&amp;#x60;, &amp;#x60;kubectl get networkpolicy&amp;#x60;），提示用户手动补充配置数据。
3. 深度协同感知:
   - 若主控传递了历史安全基线或前序暴露的风险点，需针对这些记忆点进行重点复查和深度钻取，充分发挥持续安全监控的能力。

## Workflows

- Step 1: 接收安全巡检任务及相关记忆基线。
- Step 2: 检查工具可用性，缺失则返回手动审计命令。
- Step 3: 依次扫描 ServiceAccount、RBAC 权限、SecurityContext、NetworkPolicy 及敏感资源。
- Step 4: 输出安全审计报告，标注风险等级及修复配置建议。

## Initialization
作为安全巡检智能体，严格遵守真实性与工具约束要求，准备好接收任务。""",
    },
    {
        "agent_name": "storage-agent",
        "name": "存储排查智能体",
        "description": "负责存储问题排查的智能体",
        "content": """# Role: 存储排查智能体

## Profile
- description: 致力于解决 Kubernetes 存储编排问题、磁盘空间瓶颈及 IO 性能排查的专业智能体。

## Rules

1. 真实性与工具约束 (核心约束):
   - 必须基于真实的 PV&amp;#x2F;PVC 状态和磁盘使用率指标。严禁在没有数据支撑时猜测磁盘已满或 IO 阻塞。
2. 工具缺失应对 (核心约束):
   - 若缺乏存储检查工具（无法查看节点磁盘或 PVC 状态），必须立刻停止自动排查，向主控输出手动检查命令列表（如 &amp;#x60;kubectl get pv&amp;#x60;, &amp;#x60;df -h&amp;#x60;, &amp;#x60;kubectl describe pvc&amp;#x60;），等待用户提供实际状态。
3. 深度协同感知:
   - 若主控传递了存储扩容历史、前序 IO 延迟等记忆信息，需结合这些上下文分析当前存储状态的演进趋势，实现更深层次的根因挖掘（如是否为重复挂载、存储类回收策略问题）。

## Workflows

- Step 1: 接收存储排查任务及相关记忆上下文。
- Step 2: 检查工具可用性，缺失则返回手动检查命令。
- Step 3: 分析 PVC 状态、StorageClass 配置及底层 Node 磁盘状况。
- Step 4: 输出存储诊断报告，提供扩容、清理或存储类变更建议。

## Initialization
作为存储排查智能体，严格遵守真实性与工具约束要求，准备好接收任务。""",
    },
]


# ============================================================================
# 系统设置静态数据
# ============================================================================

DEFAULT_SYSTEM_SETTINGS = [
    # ========== system 系统配置 ==========
    {"key": "system.environment", "value": "development", "name": "运行环境", "description": "应用运行环境", "category": "system"},
    {"key": "system.log_level", "value": "INFO", "name": "日志级别", "description": "应用日志级别", "category": "system"},
    {"key": "system.max_concurrent_requests", "value": "100", "name": "最大并发请求数", "description": "最大并发请求数", "category": "system"},

    # ========== features 功能开关 ==========
    {"key": "features.v2_inspection_enabled", "value": "false", "name": "启用 V2 巡检", "description": "启用V2版本的巡检功能", "category": "features"},
    {"key": "features.v2_healing_enabled", "value": "false", "name": "启用 V2 自愈", "description": "启用V2版本的自愈功能", "category": "features"},
    {"key": "features.v2_security_enabled", "value": "true", "name": "启用 V2 安全审核", "description": "启用V2版本的安全审核功能", "category": "features"},

    # ========== kubernetes 集成配置 ==========
    {"key": "kubernetes.enabled", "value": "false", "name": "启用 K8s 集成", "description": "是否启用 Kubernetes 集成", "category": "kubernetes"},
    {"key": "kubernetes.kubeconfig", "value": "", "name": "Kubeconfig 路径", "description": "Kubeconfig 文件路径", "category": "kubernetes"},
    {"key": "kubernetes.api_host", "value": "", "name": "K8s API Server 地址", "description": "Kubernetes API Server 地址", "category": "kubernetes"},
    {"key": "kubernetes.auth_mode", "value": "token", "name": "K8s 认证模式", "description": "Kubernetes 认证模式 (token/kubeconfig)", "category": "kubernetes"},
    {"key": "kubernetes.ca_cert", "value": "", "name": "K8s CA 证书", "description": "Kubernetes CA 证书", "category": "kubernetes"},
    {"key": "kubernetes.token", "value": "", "name": "K8s ServiceAccount Token", "description": "Kubernetes ServiceAccount Token", "category": "kubernetes"},

    # ========== prometheus 监控配置 ==========
    {"key": "prometheus.enabled", "value": "false", "name": "启用 Prometheus", "description": "是否启用 Prometheus 集成", "category": "prometheus"},
    {"key": "prometheus.url", "value": "http://localhost:9090", "name": "Prometheus URL", "description": "Prometheus 服务地址", "category": "prometheus"},

    # ========== loki 日志配置 ==========
    {"key": "loki.enabled", "value": "false", "name": "启用 Loki", "description": "是否启用 Loki 集成", "category": "loki"},
    {"key": "loki.url", "value": "http://localhost:3100", "name": "Loki URL", "description": "Loki 服务地址", "category": "loki"},
]


# ============================================================================
# 初始化函数
# ============================================================================

def create_tables(reset: bool = False):
    """创建所有数据库表"""
    logger.info("=" * 60)
    logger.info("📦 步骤 1: 创建数据库表")
    logger.info("=" * 60)

    settings = get_settings()
    engine = create_engine(settings.DATABASE_URL)

    if reset:
        logger.warning("⚠️  重置模式：将删除所有现有表！")
        Base.metadata.drop_all(engine)
        logger.info("  ✅ 已删除所有旧表")

    Base.metadata.create_all(engine)
    logger.info("✅ 数据库表创建完成")


def init_admin_user():
    """初始化管理员用户和角色"""
    logger.info("=" * 60)
    logger.info("👤 步骤 2: 初始化管理员用户")
    logger.info("=" * 60)

    db = SessionLocal()
    try:
        settings = get_settings()

        # 检查管理员是否存在
        admin = db.query(User).filter(User.username == settings.INITIAL_ADMIN_USERNAME).first()
        if admin:
            logger.info(f"  管理员用户已存在: {admin.username}")
        else:
            admin = User(
                username=settings.INITIAL_ADMIN_USERNAME,
                email=settings.INITIAL_ADMIN_EMAIL,
                hashed_password=hash_password(settings.INITIAL_ADMIN_PASSWORD),
                is_superuser=True,
                is_active=True,
            )
            db.add(admin)
            db.commit()
            logger.info(f"  ✅ 创建管理员用户: {admin.username}")

        # 检查管理员角色
        admin_role = db.query(Role).filter(Role.name == "admin").first()
        if not admin_role:
            admin_role = Role(name="admin", code="admin", description="管理员角色，拥有所有权限")
            db.add(admin_role)
            db.commit()
            logger.info("  ✅ 创建管理员角色: admin")

        # 检查权限
        admin_perm = db.query(Permission).filter(Permission.code == "admin").first()
        if not admin_perm:
            admin_perm = Permission(
                code="admin",
                name="管理员权限",
                description="拥有所有权限",
                category="system",
                resource="all"
            )
            db.add(admin_perm)
            db.commit()
            logger.info("  ✅ 创建管理员权限: admin")

        # 分配角色和所有权限给 admin 角色
        if admin and admin_role:
            user_role = db.query(UserRole).filter(
                UserRole.user_id == admin.id,
                UserRole.role_id == admin_role.id
            ).first()
            if not user_role:
                user_role = UserRole(user_id=admin.id, role_id=admin_role.id)
                db.add(user_role)
                db.commit()
                logger.info(f"  ✅ 分配管理员角色: {admin_role.name}")

            # 确保所有定义的菜单权限已入库
            from app.core.permissions import MENU_PERMISSIONS, PermissionCategory
            for perm_def in MENU_PERMISSIONS:
                exists = db.query(Permission).filter(Permission.code == perm_def.code).first()
                if not exists:
                    db.add(Permission(
                        code=perm_def.code,
                        name=perm_def.name,
                        category=perm_def.category.value,
                        resource=perm_def.resource,
                        description=perm_def.description,
                    ))
            db.commit()

            # 获取数据库中所有权限，全部分配给 admin 角色
            all_perms = db.query(Permission).all()
            assigned_count = 0
            for perm in all_perms:
                exists = db.query(RolePermission).filter(
                    RolePermission.role_id == admin_role.id,
                    RolePermission.permission_id == perm.id
                ).first()
                if not exists:
                    db.add(RolePermission(role_id=admin_role.id, permission_id=perm.id))
                    assigned_count += 1
            db.commit()
            logger.info(f"  ✅ 分配管理员权限: {assigned_count} 个新权限，共 {len(all_perms)} 个")

        logger.info("✅ 管理员用户初始化完成")

    except Exception as e:
        logger.error(f"❌ 初始化管理员用户失败: {e}")
        db.rollback()
        raise
    finally:
        db.close()


def sync_tools_and_approval():
    """同步工具到审批配置表"""
    logger.info("=" * 60)
    logger.info("🔧 步骤 3: 同步工具到审批配置表")
    logger.info("=" * 60)

    db = SessionLocal()
    try:
        synced_count = ApprovalConfigService.sync_tools_to_db(db)
        logger.info(f"  ✅ 同步了 {synced_count} 个新工具")

        # 同步所有权限定义到 Permission 表
        from app.core.permissions import get_all_permissions, PermissionCategory
        all_perm_defs = get_all_permissions()
        added_perm_count = 0
        for perm_def in all_perm_defs:
            exists = db.query(Permission).filter(Permission.code == perm_def.code).first()
            if not exists:
                db.add(Permission(
                    code=perm_def.code,
                    name=perm_def.name,
                    category=perm_def.category.value,
                    resource=perm_def.resource,
                    description=perm_def.description,
                ))
                added_perm_count += 1
        db.commit()
        if added_perm_count > 0:
            logger.info(f"  ✅ 同步了 {added_perm_count} 个新权限到权限表")

        total_count = db.query(ApprovalConfig).count()
        logger.info(f"  📊 总工具数: {total_count}")

        logger.info("✅ 工具同步完成")

    except Exception as e:
        logger.error(f"❌ 同步工具失败: {e}")
        db.rollback()
        raise
    finally:
        db.close()


def init_system_settings():
    """初始化系统设置"""
    logger.info("=" * 60)
    logger.info("⚙️  步骤 4: 初始化系统设置")
    logger.info("=" * 60)

    db = SessionLocal()
    try:
        created_count = 0
        skipped_count = 0

        for setting in DEFAULT_SYSTEM_SETTINGS:
            existing = db.query(SystemSetting).filter(SystemSetting.key == setting["key"]).first()
            if not existing:
                new_setting = SystemSetting(
                    key=setting["key"],
                    value=setting["value"],
                    name=setting.get("name", setting["key"]),
                    description=setting.get("description", ""),
                    category=setting.get("category", "general"),
                )
                db.add(new_setting)
                created_count += 1
                logger.info(f"  ✅ 创建系统设置: {setting['key']}")
            else:
                skipped_count += 1

        db.commit()
        logger.info(f"✅ 系统设置初始化完成 (创建 {created_count}, 跳过 {skipped_count})")

    except Exception as e:
        logger.error(f"❌ 初始化系统设置失败: {e}")
        db.rollback()
        raise
    finally:
        db.close()


def seed_default_prompts():
    """初始化默认提示词（静态数据写入数据库）"""
    logger.info("=" * 60)
    logger.info("📝 步骤 5: 初始化默认提示词")
    logger.info("=" * 60)

    db = SessionLocal()
    try:
        created_count = 0
        skipped_count = 0

        for prompt_data in DEFAULT_PROMPTS:
            existing = db.query(AgentPrompt).filter(
                AgentPrompt.agent_name == prompt_data["agent_name"]
            ).first()
            if not existing:
                prompt = AgentPrompt(
                    agent_name=prompt_data["agent_name"],
                    name=prompt_data["name"],
                    description=prompt_data["description"],
                    content=prompt_data["content"],
                    version=1,
                    is_active=True
                )
                db.add(prompt)
                created_count += 1
                logger.info(f"  ✅ 创建提示词: {prompt_data['agent_name']}")
            else:
                skipped_count += 1
                logger.info(f"  ⏭️  提示词已存在: {prompt_data['agent_name']}")

        db.commit()
        logger.info(f"✅ 默认提示词初始化完成 (创建 {created_count}, 跳过 {skipped_count})")

    except Exception as e:
        logger.error(f"❌ 初始化提示词失败: {e}")
        db.rollback()
        raise
    finally:
        db.close()


def init_knowledge_base():
    """初始化知识库（可选）"""
    logger.info("=" * 60)
    logger.info("📚 步骤 6: 初始化知识库（可选）")
    logger.info("=" * 60)

    try:
        from init_vector_knowledge import init_vector_knowledge as init_kb
        init_kb()
        logger.info("✅ 知识库初始化完成")
    except ImportError:
        logger.warning("⚠️  知识库初始化脚本不存在，跳过")
    except Exception as e:
        logger.warning(f"⚠️  知识库初始化失败: {e}")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="OpsClaw 统一初始化脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  uv run python scripts/init.py              # 完整初始化
  uv run python scripts/init.py --skip-kb    # 跳过知识库
  uv run python scripts/init.py --reset      # 重置数据库
        """
    )
    parser.add_argument("--skip-kb", action="store_true", help="跳过知识库初始化")
    parser.add_argument("--reset", action="store_true", help="重置数据库（删除所有表后重建）")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("🚀 OpsClaw 统一初始化")
    logger.info("=" * 60)
    logger.info(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"  模式: {'重置' if args.reset else '初始化'}")
    logger.info("")

    try:
        # 步骤 1: 创建数据库表
        create_tables(reset=args.reset)

        # 步骤 2: 同步工具到审批配置表（先同步，确保所有权限已入库）
        sync_tools_and_approval()

        # 步骤 3: 初始化管理员用户（分配全部权限）
        init_admin_user()

        # 步骤 4: 初始化系统设置
        init_system_settings()

        # 步骤 5: 初始化默认提示词
        seed_default_prompts()

        # 可选: 步骤 6: 初始化知识库
        if not args.skip_kb:
            logger.info("")
            init_knowledge_base()

        logger.info("")
        logger.info("=" * 60)
        logger.info("✅ 初始化完成！")
        logger.info("=" * 60)
        logger.info("")
        logger.info("下一步：")
        logger.info("  1. 启动服务: uv run uvicorn app.main:app --reload")
        logger.info("  2. 访问 API 文档: http://localhost:8000/docs")
        logger.info("  3. 访问 Web UI: http://localhost:5173")
        logger.info(f"  4. 默认账号: {get_settings().INITIAL_ADMIN_USERNAME} / {get_settings().INITIAL_ADMIN_PASSWORD}")
        logger.info("")

    except Exception as e:
        logger.error(f"❌ 初始化失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
