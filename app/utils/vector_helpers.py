"""
向量辅助工具函数

提供向量计算和相似度搜索的通用函数
"""

import numpy as np
from typing import List, Tuple
import logging

from app.utils.logger import get_logger

logger = get_logger(__name__)


def cosine_similarity(vec1: np.ndarray, vec2: np.ndarray) -> float:
    """
    计算两个向量的余弦相似度

    Args:
        vec1: 向量 1 (numpy array)
        vec2: 向量 2 (numpy array)

    Returns:
        余弦相似度，范围 [-1, 1]，值越接近 1 表示越相似
    """
    # 确保是 numpy 数组
    vec1 = np.asarray(vec1, dtype=np.float32)
    vec2 = np.asarray(vec2, dtype=np.float32)

    # 计算点积
    dot_product = np.dot(vec1, vec2)

    # 计算模长（添加小值防止除零）
    norm1 = np.linalg.norm(vec1)
    norm2 = np.linalg.norm(vec2)

    # 计算余弦相似度
    similarity = dot_product / (norm1 * norm2 + 1e-8)

    return float(similarity)


def normalize_vector(vec: np.ndarray) -> np.ndarray:
    """
    归一化向量（L2 归一化）

    Args:
        vec: 输入向量

    Returns:
        归一化后的向量
    """
    vec = np.asarray(vec, dtype=np.float32)
    norm = np.linalg.norm(vec)
    if norm > 1e-8:
        return vec / norm
    return vec


def batch_cosine_similarity(
    query_vec: np.ndarray,
    candidates: List[np.ndarray]
) -> List[Tuple[int, float]]:
    """
    批量计算余弦相似度

    Args:
        query_vec: 查询向量
        candidates: 候选向量列表

    Returns:
        (索引, 相似度) 列表，按相似度降序排序
    """
    results = []
    for idx, candidate in enumerate(candidates):
        try:
            similarity = cosine_similarity(query_vec, candidate)
            results.append((idx, similarity))
        except Exception as e:
            logger.debug(f"计算相似度失败 (索引 {idx}): {e}")
            continue

    # 按相似度降序排序
    results.sort(key=lambda x: x[1], reverse=True)
    return results


def vector_to_blob(vec: np.ndarray) -> bytes:
    """
    将向量序列化为二进制格式（用于存储）

    Args:
        vec: 输入向量

    Returns:
        二进制数据
    """
    return vec.astype(np.float32).tobytes()


def blob_to_vector(blob: bytes) -> np.ndarray:
    """
    从二进制格式反序列化向量

    Args:
        blob: 二进制数据

    Returns:
        向量
    """
    return np.frombuffer(blob, dtype=np.float32)


__all__ = [
    "cosine_similarity",
    "normalize_vector",
    "batch_cosine_similarity",
    "vector_to_blob",
    "blob_to_vector",
]
