// src/types/feishu.ts
/**
 * 飞书集成相关类型定义
 */

export type FeishuConnectionMode = 'webhook' | 'longconn' | 'auto';

export interface FeishuStatus {
  enabled: boolean;
  connection_mode?: FeishuConnectionMode;
  healthy?: boolean;
  app_id?: string;
  has_webhook_url?: boolean;
  has_verification_token?: boolean;
  has_encrypt_key?: boolean;
  longconn?: LongConnStatus;
  error?: string;
}

export interface LongConnStatus {
  connected: boolean;
  running: boolean;
  reconnect_count: number;
  last_heartbeat?: string;
  registered_handlers: string[];
}
