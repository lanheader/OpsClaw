// src/types/errors.ts
/**
 * 错误类型定义
 */

export enum ErrorCode {
  // 网络错误
  NETWORK_ERROR = 'NETWORK_ERROR',
  TIMEOUT_ERROR = 'TIMEOUT_ERROR',

  // 认证错误
  UNAUTHORIZED = 'UNAUTHORIZED',
  FORBIDDEN = 'FORBIDDEN',
  TOKEN_EXPIRED = 'TOKEN_EXPIRED',

  // 业务错误
  NOT_FOUND = 'NOT_FOUND',
  BAD_REQUEST = 'BAD_REQUEST',
  SERVER_ERROR = 'SERVER_ERROR',

  // 其他
  UNKNOWN_ERROR = 'UNKNOWN_ERROR',
}

export interface AppError {
  code: ErrorCode;
  message: string;
  userMessage: string;  // 用户友好的错误消息
  suggestion?: string;   // 错误恢复建议
  originalError?: any;   // 原始错误对象
  statusCode?: number;   // HTTP 状态码
}

export class ApiError extends Error implements AppError {
  code: ErrorCode;
  userMessage: string;
  suggestion?: string;
  originalError?: any;
  statusCode?: number;

  constructor(error: AppError) {
    super(error.message);
    this.name = 'ApiError';
    this.code = error.code;
    this.userMessage = error.userMessage;
    this.suggestion = error.suggestion;
    this.originalError = error.originalError;
    this.statusCode = error.statusCode;
  }
}
