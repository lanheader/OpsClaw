"""
Skills 管理模块

Skills 是可复用的提示词片段，用于增强 Agent 的能力。
支持两种格式：
1. 单个 .md 文件：skill-name.md
2. 目录：skill-name/ (包含 README.md 或 index.md)

使用方式：
    from app.skills import get_skill, list_skills

    # 获取 skill
    skill_content = get_skill("k8s-troubleshooting")

    # 在 SubAgent 配置中使用
    subagent_config["skills"] = ["k8s-troubleshooting"]
"""

from typing import Dict, List, Optional
from pathlib import Path

# Skills 注册表
_SKILLS_REGISTRY: Dict[str, str] = {}


def register_skill(name: str, content: str) -> None:
    """注册一个 skill"""
    _SKILLS_REGISTRY[name] = content


def get_skill(name: str) -> Optional[str]:
    """获取 skill 内容"""
    return _SKILLS_REGISTRY.get(name)


def list_skills() -> List[str]:
    """列出所有已注册的 skill 名称"""
    return sorted(_SKILLS_REGISTRY.keys())


def _load_skill_from_file(skill_file: Path) -> tuple[str, str]:
    """从文件加载 skill，返回 (name, content)"""
    return skill_file.stem, skill_file.read_text(encoding="utf-8")


def _load_skill_from_directory(skill_dir: Path) -> tuple[str, str]:
    """
    从目录加载 skill，返回 (name, content)
    优先查找 README.md，其次 index.md
    """
    readme = skill_dir / "README.md"
    index = skill_dir / "index.md"

    if readme.exists():
        content = readme.read_text(encoding="utf-8")
    elif index.exists():
        content = index.read_text(encoding="utf-8")
    else:
        # 如果没有 README.md 或 index.md，合并所有 .md 文件
        md_files = sorted(skill_dir.glob("*.md"))
        content = "\n\n".join(f.read_text(encoding="utf-8") for f in md_files)

    return skill_dir.name, content


def detect_and_load_skills(base_dir: Path) -> None:
    """
    自动检测并加载 skills

    检测规则：
    1. 单个 .md 文件（非 README/EXAMPLES）→ skill
    2. 目录（包含 .md 文件）→ skill
    """
    if not base_dir.exists():
        return

    # 跳过的文件名
    SKIP_FILES = {"README", "EXAMPLES"}

    # 1. 加载单个 .md 文件
    for md_file in base_dir.glob("*.md"):
        if md_file.stem.upper() not in SKIP_FILES:
            name, content = _load_skill_from_file(md_file)
            register_skill(name, content)

    # 2. 加载目录（作为 skill）
    for item in base_dir.iterdir():
        if item.is_dir() and not item.name.startswith((".", "_")):
            # 检查目录是否包含 .md 文件
            if any(item.glob("*.md")):
                name, content = _load_skill_from_directory(item)
                register_skill(name, content)


# 自动加载当前目录下的 skills
_SKILLS_DIR = Path(__file__).parent
detect_and_load_skills(_SKILLS_DIR)


__all__ = [
    "register_skill",
    "get_skill",
    "list_skills",
    "detect_and_load_skills",
]
