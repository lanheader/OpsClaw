/**
 * 提示词管理相关类型定义
 */

export type SubagentName = 'main-agent' | 'data-agent' | 'analyze-agent' | 'execute-agent';
export type PromptType = 'base' | 'optimized';
export type ChangeType = 'create' | 'update' | 'optimize' | 'activate';

export interface SubagentPrompt {
  id: number;
  subagent_name: SubagentName;
  version: string;
  prompt_content: string;
  prompt_type: PromptType;
  is_active: boolean;
  is_latest: boolean;
  few_shot_examples?: any[];
  performance_score: number;
  usage_count: number;
  success_rate: number;
  optimization_metadata?: {
    method?: string;
    training_examples_count?: number;
    created_at?: string;
  };
  created_by: number | null;
  updated_by: number | null;
  created_at: string;
  updated_at: string;
  last_used_at: string | null;
  notes: string | null;
}

export interface PromptChangeLog {
  id: number;
  subagent_name: SubagentName;
  prompt_id: number | null;
  change_type: ChangeType;
  old_version: string | null;
  new_version: string;
  old_content: string | null;
  new_content: string | null;
  change_reason: string | null;
  changed_by: number | null;
  changed_at: string;
  optimization_method: string | null;
  training_examples_count: number | null;
}

export interface SubagentConfig {
  name: SubagentName;
  displayName: string;
  description: string;
  icon: string;
  color: string;
}
