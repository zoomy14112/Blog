#!/usr/bin/env python3
"""
transform.py — 将 MarkdownFiles/ 下的原始篇章转化为 AstroPaper 博客文章。

读取 export/Filelist.txt 中 "Main Parts" 部分列出的文件，
将每个文件按 #### 级标题拆分为独立日记条目，
每个条目生成一个符合 AstroPaper 主题格式的 .md 文件，
放入 blog/src/content/posts/<系列目录>/ 中。

"""

import os
import re
import shutil
from pathlib import Path
from datetime import datetime, timezone, timedelta

# ---------------------------------------------------------------------------
# 路径配置
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent  # StarProject/
MARKDOWN_DIR = PROJECT_ROOT / "MarkdownFiles"
FILELIST_PATH = PROJECT_ROOT / "export" / "Filelist.txt"
POSTS_DIR = PROJECT_ROOT / "blog" / "src" / "content" / "posts"

# 北京时间 (UTC+8)
CST = timezone(timedelta(hours=8))

# ---------------------------------------------------------------------------
# 元数据配置 — 按需修改
# ---------------------------------------------------------------------------
AUTHOR = "千秋星辰"
DEFAULT_TAGS = {
    "part":    ["星辰project", "随笔"],
    "restart": ["星辰project", "restart", "随笔"],
    "fantasy": ["幻想project", "幻想", "随笔"],
}

SERIES_TITLES = {
    "part":    "星辰project",
    "restart": "星辰project·restart",
    "fantasy": "幻想project",
}

# ---------------------------------------------------------------------------
# 正则模式
# ---------------------------------------------------------------------------
RE_DATE_HEADING = re.compile(
    r"^###\s+(\d{4})\.(\d{1,2})\.(\d{1,2})\s*$"
)
RE_ENTRY_HEADING = re.compile(r"^####\s+(.+)$")
RE_LATEX = re.compile(r"\$[^$]*\$")
RE_INVALID_FILENAME_CHARS = re.compile(r'[\\/:*?"<>|$#%~{}\[\]\x00-\x1f]')


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------
def parse_filelist(path: Path) -> list[str]:
    """从 Filelist.txt 中解析 Main Parts 下所列的文件名列表。"""
    with open(path, encoding="utf-8") as f:
        lines = f.readlines()

    in_main = False
    files = []
    for line in lines:
        stripped = line.strip()
        if stripped == "### Main Parts":
            in_main = True
            continue
        if in_main:
            if stripped.startswith("###"):
                break
            if stripped.endswith(".md"):
                files.append(stripped)
    return files


def classify(filename: str) -> str:
    """根据文件名返回类别: 'part' | 'restart' | 'fantasy'。"""
    name = filename.replace(".md", "").strip().lower()
    if name.startswith("restart"):
        return "restart"
    if name.startswith("fantasy"):
        return "fantasy"
    if name.startswith("part"):
        return "part"
    return "part"


def generate_slug(filename: str) -> str:
    """根据源文件名生成子目录 slug（用作 URL 路径前缀）。"""
    name = filename.replace(".md", "").strip()
    category = classify(name)
    m = re.match(r"(?:Part|Restart|Fantasy)\s+(\d+)", name, re.IGNORECASE)
    num = m[1] if m else "0"

    if category == "part":
        return f"stars-during-lifetime-{num}"
    elif category == "restart":
        return f"stars-during-lifetime-restart-{num}"
    elif category == "fantasy":
        return f"fantasy-world-{num}"
    return re.sub(r"\s+", "-", name.lower())


def sanitize_title_for_filename(title: str) -> str:
    """将条目标题清理为安全的文件名字符串。"""
    # 1. 先将 markdown 链接 [text](url) 替换为 text
    cleaned = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", title)
    # 2. 去掉 LaTeX 公式 $...$
    cleaned = RE_LATEX.sub("", cleaned)
    # 3. 去掉智能引号及其他特殊 Unicode 标点
    cleaned = cleaned.replace("“", "").replace("”", "")  # ""
    cleaned = cleaned.replace("‘", "").replace("’", "")  # ''
    cleaned = cleaned.replace("《", "").replace("》", "")  # 《》
    # 4. 去掉非法文件名字符
    cleaned = RE_INVALID_FILENAME_CHARS.sub("", cleaned)
    # 5. 替换空白字符为连字符
    cleaned = re.sub(r"\s+", "-", cleaned)
    # 6. 去掉首尾连字符和括号
    cleaned = cleaned.strip("-（）()")
    # 7. 合并多余连字符
    cleaned = re.sub(r"-{2,}", "-", cleaned)
    # 8. 限制长度（日期前缀是 11 字符 YYYY-MM-DD-）
    if len(cleaned) > 80:
        cleaned = cleaned[:80].rstrip("-")
    return cleaned


def clean_title(title: str) -> str:
    """清理标题：去除 Markdown 链接和 LaTeX 公式，只保留纯文本。"""
    # 去除 Markdown 链接 [text](url) → text
    cleaned = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", title)
    # 去除 LaTeX 公式 $...$
    cleaned = RE_LATEX.sub("", cleaned)
    # 去除首尾空格
    cleaned = cleaned.strip()
    return cleaned


def extract_description(text: str) -> str:
    """从条目正文提取第一句话作为描述。

    以中文句号/问号/感叹号/省略号或英文句号/问号/感叹号为句子分隔符，
    取第一个完整句子；若超长则截断。
    """
    # 先取正文的第一行非空、非标题内容
    lines = text.split("\n")
    first_line = ""
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("![") or stripped.startswith("> ["):
            continue
        if stripped.startswith("#"):
            continue
        first_line = stripped
        break

    if not first_line:
        return ""

    # 去除 markdown 链接 URL、HTML 标签、LaTeX 公式、blockquote 标记
    cleaned = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", first_line)
    cleaned = re.sub(r"</?[^>]+>", "", cleaned)
    cleaned = RE_LATEX.sub("", cleaned)
    cleaned = re.sub(r"^>\s*", "", cleaned)  # 去掉 blockquote 前缀
    cleaned = cleaned.strip()

    # 按句子分隔符取第一句话
    m = re.match(r"(.*?[。！？…\.\!\?])", cleaned)
    if m:
        sentence = m[1]
    else:
        # 没有句末标点，取前 200 字符作为一句
        sentence = cleaned[:200]

    # 长度限制
    if len(sentence) > 200:
        sentence = sentence[:197] + "..."

    return sentence


def yaml_single_quote(s: str) -> str:
    """将字符串转为 YAML 单引号字面量，避免反斜杠被解释为转义序列。"""
    escaped = s.replace("'", "''")
    return f"'{escaped}'"


def build_frontmatter(title: str, pub_datetime: datetime,
                      description: str, tags: list[str],
                      featured: bool = False, draft: bool = False) -> str:
    """构造 YAML frontmatter 字符串。"""
    iso = pub_datetime.strftime("%Y-%m-%dT%H:%M:%S+08:00")
    tag_lines = "\n".join(f"  - {t}" for t in tags)
    desc = description or title

    return f"""---
author: {AUTHOR}
pubDatetime: {iso}
title: {yaml_single_quote(title)}
featured: {"true" if featured else "false"}
draft: {"true" if draft else "false"}
tags:
{tag_lines}
description: {yaml_single_quote(desc)}
---

"""


# ---------------------------------------------------------------------------
# 核心：将单个源文件拆分为日记条目
# ---------------------------------------------------------------------------
def split_into_entries(raw: str) -> list[dict]:
    """将原始文本按 #### 标题拆分为独立日记条目列表。

    每条目 dict 包含:
        date:       datetime  — 所属日期（从最近一个 ### 日期标题继承）
        title:      str       — 条目标题（#### 后的文本）
        body:       str       — 条目正文（含 #### 标题行，不含 ### 日期行）
        first_line: int      — 在原文中的起始行号（用于诊断）
    """
    lines = raw.split("\n")
    entries: list[dict] = []
    current_date: datetime | None = None
    current_buf: list[str] = []
    current_title: str | None = None

    def flush_entry():
        nonlocal current_title, current_buf
        if current_title is not None:
            # 去掉首尾空行
            while current_buf and current_buf[0].strip() == "":
                current_buf.pop(0)
            while current_buf and current_buf[-1].strip() == "":
                current_buf.pop()
            body = "\n".join(current_buf) + "\n"
            entries.append({
                "date": current_date,
                "title": current_title,
                "body": body,
            })
        current_title = None
        current_buf = []

    for line in lines:
        # 检测日期行（匹配 ### YYYY.M.D）
        m_date = RE_DATE_HEADING.match(line)
        if m_date:
            flush_entry()
            y, mo, d = int(m_date[1]), int(m_date[2]), int(m_date[3])
            current_date = datetime(y, mo, d, tzinfo=CST)
            continue

        # 检测条目分隔行（所有 ### 开头的行，包括非标准日期如 ### ？）
        # 均视为节分隔：不更新日期，但刷新当前条目，避免分隔符混入正文
        if line.startswith("### "):
            flush_entry()
            continue

        # 检测条目标题行
        m_entry = RE_ENTRY_HEADING.match(line)
        if m_entry:
            flush_entry()
            current_title = m_entry[1].strip()
            current_buf = []  # 标题已写入 frontmatter，正文不再保留
            continue

        # 普通行：追加到当前条目缓冲区
        if current_title is not None:
            current_buf.append(line)

    flush_entry()
    return entries


def clean_entry_body(body: str) -> str:
    """清理单条目正文：移除末尾的 --- 分隔线和洛谷返回链接。"""
    body = re.sub(
        r"\n*---\n\n\[.*?返回.*?\]\(https://www\.luogu\.com\.cn/blog/guan-xing-ge/.*?\)\s*$",
        "",
        body,
    )
    body = re.sub(r"\n*---\s*$", "", body)
    return body


# ---------------------------------------------------------------------------
# 单文件转化（拆分版本）
# ---------------------------------------------------------------------------
def transform_file(filename: str) -> tuple[str, list[tuple[str, str, datetime]]] | None:
    """将单个源文件拆分为多条目，返回 (子目录名, [(文件名, 内容, 日期), ...])。"""
    src_path = MARKDOWN_DIR / filename
    if not src_path.exists():
        print(f"  ⚠ 跳过不存在的文件: {src_path}")
        return None

    with open(src_path, encoding="utf-8") as f:
        raw = f.read()

    dir_slug = generate_slug(filename)
    category = classify(filename)
    tags = DEFAULT_TAGS.get(category, ["others"])

    entries = split_into_entries(raw)
    if not entries:
        print(f"  ⚠ 未找到任何日记条目: {filename}")
        return None

    files: list[tuple[str, str, datetime]] = []
    used_names: dict[str, int] = {}  # 用于处理同名文件

    for i, entry in enumerate(entries):
        date = entry["date"]
        title = entry["title"]
        body = clean_entry_body(entry["body"])

        # 时间戳
        if date is None:
            # 如果没有日期（全部源文件第一个 ### 前无内容的情况），
            # 使用上一个条目的日期；若为首个则回退到文件修改时间
            if files:
                date = files[-1][2]
            else:
                mtime = os.path.getmtime(src_path)
                date = datetime.fromtimestamp(mtime, tz=CST)
                print(f"  ⚠ 首个条目无日期，使用文件修改时间: {title}")

        # 描述
        description = extract_description(body)

        # 清理标题中的 Markdown/LateX 格式（frontmatter 中无法渲染）
        clean = clean_title(title)

        # 文件名：日期-标题
        title_slug = sanitize_title_for_filename(clean)
        if not title_slug:
            title_slug = f"entry-{i + 1:03d}"
        date_prefix = date.strftime("%Y-%m-%d")
        base_name = f"{date_prefix}-{title_slug}"

        # 处理同名冲突
        if base_name in used_names:
            used_names[base_name] += 1
            file_name = f"{base_name}-{used_names[base_name]}"
        else:
            used_names[base_name] = 0
            file_name = base_name

        file_name += ".md"

        # 构建输出内容
        fm = build_frontmatter(clean, date, description, tags)
        output_content = fm + body

        files.append((file_name, output_content, date))

    return dir_slug, files


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def main():
    print("=" * 60)
    print("  AstroPaper 博客文章转化脚本（拆分版）")
    print("=" * 60)
    print()

    # 1. 解析文件列表
    if not FILELIST_PATH.exists():
        print(f" Filelist 不存在: {FILELIST_PATH}")
        return 1

    files = parse_filelist(FILELIST_PATH)
    print(f" 从 Filelist.txt 读取到 {len(files)} 个文件")
    print()

    # 2. 清理旧的平铺文件和子目录（上次运行可能生成的）
    old_dirs = [
        "stars-during-lifetime-1", "stars-during-lifetime-2",
        "stars-during-lifetime-3", "stars-during-lifetime-4",
        "stars-during-lifetime-5", "stars-during-lifetime-6",
        "stars-during-lifetime-7",
        "stars-during-lifetime-restart-1", "stars-during-lifetime-restart-2",
        "stars-during-lifetime-restart-3",
        "fantasy-world-1", "fantasy-world-2",
    ]
    cleaned = 0
    for name in old_dirs:
        # 清理平铺文件
        fp = POSTS_DIR / f"{name}.md"
        if fp.exists():
            fp.unlink()
            cleaned += 1
        # 清理子目录
        dp = POSTS_DIR / name
        if dp.exists() and dp.is_dir():
            shutil.rmtree(dp)
            cleaned += 1
    if cleaned:
        print(f"🧹 清理了 {cleaned} 个旧文件/目录")
        print()

    # 3. 逐个源文件转化
    total_entries = 0
    total_written = 0
    total_skipped = 0

    for filename in files:
        print(f"🔄 处理: {filename}")
        result = transform_file(filename)
        if result is None:
            continue

        dir_slug, entry_files = result
        dir_path = POSTS_DIR / dir_slug
        dir_path.mkdir(parents=True, exist_ok=True)

        for fname, content, _date in entry_files:
            output_path = dir_path / fname

            if output_path.exists():
                with open(output_path, encoding="utf-8") as f:
                    old = f.read()
                if old == content:
                    total_skipped += 1
                    total_entries += 1
                    continue

            with open(output_path, "w", encoding="utf-8") as f:
                f.write(content)
            total_written += 1
            total_entries += 1

        print(f"  ✓ → {dir_slug}/  ({len(entry_files)} 个条目)")

    print()
    print(f"✅ 完成！共 {total_entries} 个日记条目")
    print(f"   新写入: {total_written}  跳过(未变): {total_skipped}")
    print(f"   输出目录: {POSTS_DIR}/<系列目录>/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
