// src/utils/errorHandler.example.ts
/**
 * 错误处理工具函数示例
 */
import { message as antdMessage } from 'antd';
import { ApiError, ErrorCode } from '@/types/errors.example';

// 错误码映射表
const ERROR_MESSAGES: Record<ErrorCode, { message: string; suggestion?: string }> = {
  [ErrorCode.NETWORK_ERROR]: {
    message: '网络连接失败',
    suggestion: '请检查您的网络连接后重试'
  },
  [ErrorCode.TIMEOUT_ERROR]: {
    message: '请求超时',
    suggestion: '服务器响应较慢，请稍后重试'
  },
  [ErrorCode.UNAUTHORIZED]: {
    message: '登录已过期',
    suggestion: '请重新登录'
  },
  [ErrorCode.FORBIDDEN]: {
    message: '没有权限访问',
    suggestion: '请联系管理员获取权限'
  },
  [ErrorCode.TOKEN_EXPIRED]: {
    message: '登录已过期',
    suggestion: '请重新登录'
  },
  [ErrorCode.NOT_FOUND]: {
    message: '请求的资源不存在',
    suggestion: '请检查请求地址是否正确'
  },
  [ErrorCode.BAD_REQUEST]: {
    message: '请求参数错误',
    suggestion: '请检查输入的信息是否正确'
  },
  [ErrorCode.SERVER_ERROR]: {
    message: '服务器内部错误',
    suggestion: '服务器出现问题，请稍后重试'
  },
  [ErrorCode.UNKNOWN_ERROR]: {
    message: '未知错误',
    suggestion: '请稍后重试或联系技术支持'
  },
};

/**
 * 将 HTTP 状态码转换为错误码
 */
export function httpStatusToErrorCode(status: number): ErrorCode {
  switch (status) {
    case 400:
      return ErrorCode.BAD_REQUEST;
    case 401:
      return ErrorCode.UNAUTHORIZED;
    case 403:
      return ErrorCode.FORBIDDEN;
    case 404:
      return ErrorCode.NOT_FOUND;
    case 408:
      return ErrorCode.TIMEOUT_ERROR;
    case 500:
    case 502:
    case 503:
    case 504:
      return ErrorCode.SERVER_ERROR;
    default:
      return ErrorCode.UNKNOWN_ERROR;
  }
}

/**
 * 解析 axios 错误
 */
export function parseAxiosError(error: any): ApiError {
  if (error.response) {
    // 服务器返回错误
    const status = error.response.status;
    const data = error.response.data;
    const errorCode = httpStatusToErrorCode(status);
    const errorInfo = ERROR_MESSAGES[errorCode];

    return new ApiError({
      code: errorCode,
      message: data?.detail || data?.message || errorInfo.message,
      userMessage: errorInfo.message,
      suggestion: errorInfo.suggestion,
      originalError: error,
      statusCode: status,
    });
  } else if (error.request) {
    // 网络错误
    return new ApiError({
      code: ErrorCode.NETWORK_ERROR,
      message: error.message,
      userMessage: ERROR_MESSAGES[ErrorCode.NETWORK_ERROR].message,
      suggestion: ERROR_MESSAGES[ErrorCode.NETWORK_ERROR].suggestion,
      originalError: error,
    });
  } else {
    // 其他错误
    return new ApiError({
      code: ErrorCode.UNKNOWN_ERROR,
      message: error.message || '未知错误',
      userMessage: ERROR_MESSAGES[ErrorCode.UNKNOWN_ERROR].message,
      suggestion: ERROR_MESSAGES[ErrorCode.UNKNOWN_ERROR].suggestion,
      originalError: error,
    });
  }
}

/**
 * 解析 fetch 错误
 */
export function parseFetchError(error: any, response?: Response): ApiError {
  if (response && !response.ok) {
    const errorCode = httpStatusToErrorCode(response.status);
    const errorInfo = ERROR_MESSAGES[errorCode];

    return new ApiError({
      code: errorCode,
      message: `HTTP error! status: ${response.status}`,
      userMessage: errorInfo.message,
      suggestion: errorInfo.suggestion,
      originalError: error,
      statusCode: response.status,
    });
  } else if (error.name === 'AbortError') {
    // 请求被取消，不显示错误
    return new ApiError({
      code: ErrorCode.UNKNOWN_ERROR,
      message: 'Request aborted',
      userMessage: '请求已取消',
      originalError: error,
    });
  } else {
    // 网络错误或其他错误
    return new ApiError({
      code: ErrorCode.NETWORK_ERROR,
      message: error.message || '网络错误',
      userMessage: ERROR_MESSAGES[ErrorCode.NETWORK_ERROR].message,
      suggestion: ERROR_MESSAGES[ErrorCode.NETWORK_ERROR].suggestion,
      originalError: error,
    });
  }
}

/**
 * 显示错误提示
 */
export function showErrorMessage(error: ApiError, duration: number = 3) {
  const content = error.suggestion
    ? `${error.userMessage}：${error.suggestion}`
    : error.userMessage;

  antdMessage.error(content, duration);
}

/**
 * 统一错误处理函数
 */
export function handleError(error: any, showMessage: boolean = true): ApiError {
  const apiError = error instanceof ApiError
    ? error
    : parseAxiosError(error);

  // 记录错误日志
  console.error('[API Error]', {
    code: apiError.code,
    message: apiError.message,
    statusCode: apiError.statusCode,
    originalError: apiError.originalError,
  });

  // 显示错误提示
  if (showMessage && apiError.code !== ErrorCode.UNKNOWN_ERROR) {
    showErrorMessage(apiError);
  }

  return apiError;
}
