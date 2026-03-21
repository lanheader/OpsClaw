"""
Skills 插件系统

用户可以将自定义技能（.md 或 .py 文件）放在此目录，
系统会自动扫描并加载这些技能。
"""

import os
import glob
from pathlib import Path
from typing import Dict, List, Any
from app.utils.logger import get_logger

logger = get_logger(__name__)

# Skills 目录路径
SKILLS_DIR = Path(__file__).parent


def scan_skills() -> Dict[str, Any]:
    """
    扫描 skills 目录中的所有技能文件

    支持的格式：
    - .md 文件 - Markdown 格式的技能文档
    - .py 文件 - Python 技能模块

    Returns:
        包含所有找到的技能信息的字典
        {
            "skills": [
                {"name": "skill_name", "type": "md", "path": "...", "content": "..."},
                ...
            ],
            "total": N
        }
    """
    skills = []

    # 扫描 Markdown 技能文件
    for md_file in SKILLS_DIR.glob("*.md"):
        try:
            with open(md_file, 'r', encoding='utf-8') as f:
                content = f.read()
            skills.append({
                "name": md_file.stem,
                "type": "md",
                "path": str(md_file),
                "content": content,
                "size": len(content)
            })
            logger.info(f"✅ 找到 Markdown 技能: {md_file.name}")
        except Exception as e:
            logger.error(f"❌ 读取技能文件失败 {md_file}: {e}")

    # 扫描 Python 技能文件
    for py_file in SKILLS_DIR.glob("*.py"):
        if py_file.name.startswith("_"):
            continue  # 跳过 __init__.py
        try:
            with open(py_file, 'r', encoding='utf-8') as f:
                content = f.read()
            skills.append({
                "name": py_file.stem,
                "type": "py",
                "path": str(py_file),
                "content": content,
                "size": len(content)
            })
            logger.info(f"✅ 找到 Python 技能: {py_file.name}")
        except Exception as e:
            logger.error(f"❌ 读取技能文件失败 {py_file}: {e}")

    logger.info(f"📊 Skills 扫描完成: 共找到 {len(skills)} 个技能")

    return {
        "skills": skills,
        "total": len(skills),
        "directory": str(SKILLS_DIR)
    }


def get_skill(skill_name: str) -> Dict[str, Any]:
    """
    获取指定名称的技能

    Args:
        skill_name: 技能名称（不含扩展名）

    Returns:
        技能信息字典，如果未找到返回 None
    """
    all_skills = scan_skills()
    for skill in all_skills["skills"]:
        if skill["name"] == skill_name:
            return skill
    return None


def list_skill_names() -> List[str]:
    """
    列出所有可用的技能名称

    Returns:
        技能名称列表
    """
    all_skills = scan_skills()
    return [skill["name"] for skill in all_skills["skills"]]


def get_skills_info() -> str:
    """
    获取技能信息摘要（用于显示）

    Returns:
        格式化的技能信息字符串
    """
    result = scan_skills()
    skills = result["skills"]

    if not skills:
        return "📁 Skills 目录为空\n\n用户可以将自定义技能文件（.md 或 .py）放入此目录。"

    lines = ["📁 可用技能列表:\n"]
    for skill in skills:
        icon = "📄" if skill["type"] == "md" else "🐍"
        lines.append(f"{icon} **{skill['name']}** ({skill['type']})")
        lines.append(f"   路径: `{skill['path']}`")
        lines.append(f"   大小: {skill['size']} 字节")
        lines.append("")

    return "\n".join(lines)


__all__ = [
    "scan_skills",
    "get_skill",
    "list_skill_names",
    "get_skills_info",
]
