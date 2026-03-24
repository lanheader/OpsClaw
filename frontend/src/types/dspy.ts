// src/types/dspy.ts
/**
 * DSPy 提示词优化相关类型定义
 */

/**
 * Subagent 状态
 */
export type SubagentStatus = 'not_optimized' | 'optimizing' | 'optimized' | 'failed';

/**
 * 示例类型 - 根据任务意图分类
 */
export type ExampleType = 'query' | 'diagnose' | 'execute';

/**
 * Subagent 名称
 */
export type SubagentName = 'data-agent' | 'analyze-agent' | 'execute-agent';

/**
 * DSPy 统计信息（后端 StatsResponse）
 */
export interface DSPyStats {
  /** DSPy 是否可用 */
  dspy_available: boolean;
  /** DSPy 是否已配置 */
  configured: boolean;
  /** 训练示例总数 */
  total_examples: number;
  /** 按类型统计 */
  by_type: Record<string, number>;
  /** 按来源统计 */
  by_source: Record<string, number>;
}

/**
 * Subagent 统计信息
 */
export interface SubagentStats {
  /** Subagent 名称 */
  name: SubagentName;
  /** 状态 */
  status: SubagentStatus;
  /** 示例数量 */
  example_count: number;
  /** 最后优化时间 */
  last_optimized_at?: string;
  /** 使用的演示数量 */
  max_demos?: number;
}

/**
 * 训练示例
 */
export interface TrainingExample {
  /** 示例 ID */
  id?: number;
  /** 示例类型 */
  type: ExampleType;
  /** 用户输入 / 任务描述 */
  input: string;
  /** AI 输出 / 期望结果 */
  output: string;
  /** 元数据 */
  metadata: Record<string, any>;
}

/**
 * 优化选项（后端 OptimizeRequest）
 */
export interface OptimizeOptions {
  /** 收集最近 N 天的数据用于训练 */
  days: number;
  /** 最多标注的示例数量 */
  max_labeled_demos: number;
  /** 优化轮数 */
  max_rounds: number;
}

/**
 * 优化结果（后端 OptimizeResponse）
 */
export interface OptimizationResult {
  /** Subagent 名称 */
  subagent_name: SubagentName;
  /** 状态: success/error */
  status: string;
  /** 训练示例数量 */
  training_examples: number;
  /** 编译后的提示词路径 */
  compiled_prompt_path?: string;
  /** 可用的版本列表 */
  versions_available: string[];
  /** 错误信息 */
  error?: string;
}

/**
 * 编译后的提示词版本（后端返回格式）
 */
export interface CompiledPromptVersion {
  /** Subagent 名称 */
  subagent_name: string;
  /** 版本标识 */
  version: string;
  /** 编译时间 */
  compiled_at: string;
  /** 演示 */
  demos: any[];
}

/**
 * 编译后的提示词（前端使用）
 */
export interface CompiledPrompt {
  /** Subagent 名称 */
  subagent_name: SubagentName;
  /** 完整提示词 */
  full_prompt: string;
  /** 使用的演示 */
  demos: TrainingExample[];
  /** 元数据 */
  metadata: Record<string, any>;
  /** 编译时间 */
  compiled_at: string;
}

/**
 * 编译提示词列表响应
 */
export interface CompiledPromptsListResponse {
  /** Subagent 名称 */
  subagent_name: string;
  /** 版本列表 */
  versions: string[];
  /** 总数 */
  total: number;
}
