#!/usr/bin/env python3
"""
Skill 安装工具

从 ClawHub 安装 skills 到 OpsClaw 的 skills/ 目录。

用法:
    python scripts/install_skill.py <skill-name>
    python scripts/install_skill.py ddg-web-search
    python scripts/install_skill.py --list
    python scripts/install_skill.py --uninstall <skill-name>
"""

import os
import sys
import shutil
import subprocess
import argparse

# 项目根目录
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS_DIR = os.path.join(PROJECT_ROOT, "workspace", "skills")


def get_skill_dir(skill_name: str) -> str:
    """获取 skill 的本地目录路径"""
    return os.path.join(SKILLS_DIR, skill_name)


def install_from_clawhub(skill_name: str):
    """从 ClawHub 安装 skill"""
    skill_dir = get_skill_dir(skill_name)
    temp_dir = os.path.join(PROJECT_ROOT, ".tmp_skill_install")

    try:
        # 1. 用 clawhub 下载到临时目录
        os.makedirs(temp_dir, exist_ok=True)
        print(f"📦 从 ClawHub 下载 {skill_name}...")

        result = subprocess.run(
            ["clawhub", "install", skill_name, "--dir", temp_dir],
            capture_output=True, text=True, timeout=60,
        )

        if result.returncode != 0:
            # clawhub 可能没安装，尝试用 pip 安装
            print(f"⚠️ clawhub 未安装，尝试 pip install clawhub...")
            subprocess.run(["pip", "install", "clawhub"], capture_output=True, timeout=120)
            result = subprocess.run(
                ["clawhub", "install", skill_name, "--dir", temp_dir],
                capture_output=True, text=True, timeout=60,
            )

        if result.returncode != 0:
            print(f"❌ 下载失败: {result.stderr}")
            return False

        # 2. 查找下载的 SKILL.md
        # clawhub 安装到 --dir 目录下的 skills/<name>/SKILL.md
        possible_paths = [
            os.path.join(temp_dir, "skills", skill_name),
            os.path.join(temp_dir, skill_name),
            temp_dir,
        ]

        source_dir = None
        for p in possible_paths:
            if os.path.isdir(p) and os.path.exists(os.path.join(p, "SKILL.md")):
                source_dir = p
                break

        if not source_dir:
            # 搜索整个 temp_dir
            for root, dirs, files in os.walk(temp_dir):
                if "SKILL.md" in files:
                    source_dir = root
                    break

        if not source_dir:
            print(f"❌ 未找到 SKILL.md 文件")
            return False

        # 3. 复制到 skills 目录
        if os.path.exists(skill_dir):
            shutil.rmtree(skill_dir)
        shutil.copytree(source_dir, skill_dir)

        print(f"✅ 安装成功: {skill_name} -> {skill_dir}")

        # 4. 显示 skill 信息
        skill_md = os.path.join(skill_dir, "SKILL.md")
        if os.path.exists(skill_md):
            with open(skill_md, "r") as f:
                for line in f:
                    if line.startswith("name:") or line.startswith("description:"):
                        print(f"  {line.strip()}")
                    if line.startswith("---") and "name" in open(skill_md).read()[:50]:
                        continue

        return True

    except subprocess.TimeoutExpired:
        print("❌ 下载超时")
        return False
    except Exception as e:
        print(f"❌ 安装失败: {e}")
        return False
    finally:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)


def uninstall_skill(skill_name: str):
    """卸载 skill"""
    skill_dir = get_skill_dir(skill_name)

    if not os.path.exists(skill_dir):
        print(f"❌ Skill 不存在: {skill_name}")
        return False

    shutil.rmtree(skill_dir)
    print(f"✅ 已卸载: {skill_name}")
    return True


def list_skills():
    """列出已安装的 skills"""
    if not os.path.isdir(SKILLS_DIR):
        print("📁 Skills 目录不存在")
        return

    skills = []
    for item in sorted(os.listdir(SKILLS_DIR)):
        skill_path = os.path.join(SKILLS_DIR, item)
        if os.path.isdir(skill_path) and os.path.exists(os.path.join(skill_path, "SKILL.md")):
            skills.append(item)

    if not skills:
        print("📁 没有已安装的 skills")
        return

    print(f"📁 已安装的 Skills ({len(skills)} 个):\n")
    for skill in skills:
        skill_md = os.path.join(SKILLS_DIR, skill, "SKILL.md")
        print(f"  📄 {skill}/")

        # 解析 YAML frontmatter
        try:
            with open(skill_md, "r") as f:
                content = f.read()
            in_frontmatter = False
            for line in content.split("\n"):
                if line.strip() == "---":
                    if in_frontmatter:
                        break
                    in_frontmatter = True
                    continue
                if in_frontmatter and (line.startswith("name:") or line.startswith("description:")):
                    print(f"    {line.strip()}")
        except Exception:
            pass
        print()


def create_manual_skill(skill_name: str):
    """手动创建 skill 骨架"""
    skill_dir = get_skill_dir(skill_name)

    if os.path.exists(skill_dir):
        print(f"❌ Skill 已存在: {skill_name}")
        return False

    os.makedirs(skill_dir, exist_ok=True)

    skill_md = f"""---
name: {skill_name}
description: TODO: 描述这个 skill 的功能
license: MIT
---

# {skill_name.replace('-', ' ').title()}

## When to Use

- TODO: 描述什么时候使用这个 skill

## How to Use

TODO: 描述使用方法
"""

    with open(os.path.join(skill_dir, "SKILL.md"), "w") as f:
        f.write(skill_md)

    print(f"✅ Skill 骨架已创建: {skill_dir}/SKILL.md")
    print(f"   请编辑 SKILL.md 填写具体内容")
    return True


def main():
    parser = argparse.ArgumentParser(description="OpsClaw Skill 管理工具")
    subparsers = parser.add_subparsers(dest="command")

    # install
    install_parser = subparsers.add_parser("install", help="从 ClawHub 安装 skill")
    install_parser.add_argument("name", help="Skill 名称")

    # uninstall
    uninstall_parser = subparsers.add_parser("uninstall", help="卸载 skill")
    uninstall_parser.add_argument("name", help="Skill 名称")

    # list
    subparsers.add_parser("list", help="列出已安装的 skills")

    # create
    create_parser = subparsers.add_parser("create", help="创建 skill 骨架")
    create_parser.add_argument("name", help="Skill 名称")

    args = parser.parse_args()

    if args.command == "install":
        install_from_clawhub(args.name)
    elif args.command == "uninstall":
        uninstall_skill(args.name)
    elif args.command == "list":
        list_skills()
    elif args.command == "create":
        create_manual_skill(args.name)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
