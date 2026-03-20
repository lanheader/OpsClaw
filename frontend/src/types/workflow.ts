// src/types/workflow.ts
/**
 * 工作流相关类型定义
 */

export type TaskType =
  | 'scheduled_inspection'
  | 'alert_triggered'
  | 'manual_command'
  | 'emergency_response';

export type WorkflowStatus =
  | 'pending'
  | 'running'
  | 'paused_approval'
  | 'completed'
  | 'failed';

export type HealthStatus = 'healthy' | 'degraded' | 'unhealthy';

export type ApprovalStatus = 'approved' | 'rejected' | null;

export interface WorkflowExecuteRequest {
  task_type: TaskType;
  target_plugin: string;
  trigger_source?: string;
  trigger_user?: string;
  environment?: string;
}

export interface WorkflowExecuteResponse {
  task_id: string;
  status: WorkflowStatus;
  current_step: string;
  success: boolean;
  health_status?: HealthStatus;
  needs_approval: boolean;
  approval_status?: ApprovalStatus;
  message: string;
}

export interface WorkflowStatusResponse {
  task_id: string;
  status: WorkflowStatus;
  current_step: string;
  health_status?: HealthStatus;
  needs_approval: boolean;
  approval_status?: ApprovalStatus;
  success?: boolean;
  messages: Array<{
    role: string;
    content: string;
  }>;
}

export interface WorkflowResumeRequest {
  approval_decision: 'approved' | 'rejected';
  approver?: string;
  comment?: string;
}

export interface WorkflowListItem {
  task_id: string;
  task_type: TaskType;
  target_plugin: string;
  status: WorkflowStatus;
  health_status?: HealthStatus;
  success?: boolean;
  needs_approval: boolean;
  created_at: string;
  updated_at?: string;
}

export interface WorkflowDetail extends WorkflowStatusResponse {
  created_at: string;
  updated_at?: string;
  trigger_source?: string;
  trigger_user?: string;
  environment?: string;
  execution_result?: Record<string, any>;
  notifications?: Array<{
    type: string;
    chat_id?: string;
    message_id?: string;
    status: string;
  }>;
}

export interface WorkflowStatistics {
  total: number;
  running: number;
  completed: number;
  failed: number;
  success_rate: number;
  avg_duration: number;
}
