#!/usr/bin/env python3
"""
transform.py — 将 MarkdownFiles/ 下的原始篇章转化为 AstroPaper 博客文章。

- Main Parts: 按 #### 标题拆分为独立日记条目 → posts/<系列目录>/
- Attachments: 每文件一篇独立文章 → posts/others/
- 额外文件: Dust.md → posts/others/; Snow/release/export2html.md → posts/snow/

用法:
    cd /mnt/f/QianQiuXingChen/StarProject
    python3 blog/transform.py
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
EXTRA_DUST = MARKDOWN_DIR / "Dust.md"
EXTRA_SNOW = PROJECT_ROOT / "Snow" / "release" / "export2html.md"

# 北京时间 (UTC+8)
CST = timezone(timedelta(hours=8))

# ---------------------------------------------------------------------------
# 元数据配置
# ---------------------------------------------------------------------------
AUTHOR = "千秋星辰"
DEFAULT_TAGS = {
    "part":    ["星辰project", "随笔"],
    "restart": ["星辰project", "restart", "随笔"],
    "fantasy": ["幻想project", "幻想", "随笔"],
}
ATTACHMENT_TAGS = ["others", "文章"]

SERIES_TITLES = {
    "part":    "星辰project",
    "restart": "星辰project",
    "fantasy": "幻想project",
}

# ---------------------------------------------------------------------------
# 正则模式
# ---------------------------------------------------------------------------
RE_DATE_HEADING = re.compile(r"^###\s+(\d{4})\.(\d{1,2})\.(\d{1,2})\s*$")
RE_ENTRY_HEADING = re.compile(r"^####\s+(.+)$")
RE_LATEX = re.compile(r"\$[^$]*\$")
RE_INVALID_FILENAME_CHARS = re.compile(r'[\\/:*?"<>|$#%~{}\[\]\x00-\x1f]')

# 从文本中提取中文日期：2026 年 5 月 25 日
RE_CHINESE_DATE = re.compile(
    r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日"
)
# 从文本中提取年月：2026 年 5 月
RE_CHINESE_DATE_MONTH = re.compile(
    r"(\d{4})\s*年\s*(\d{1,2})\s*月"
)


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------
def parse_filelist_sections(path: Path) -> tuple[list[str], list[str]]:
    """解析 Filelist.txt，返回 (main_parts_files, attachments_files)。"""
    with open(path, encoding="utf-8") as f:
        lines = f.readlines()

    main_parts: list[str] = []
    attachments: list[str] = []
    current: list[str] | None = None

    for line in lines:
        stripped = line.strip()
        if stripped == "### Main Parts":
            current = main_parts
            continue
        if stripped == "### Attachments":
            current = attachments
            continue
        if stripped.startswith("###"):
            current = None
            continue
        if current is not None and stripped.endswith(".md"):
            current.append(stripped)

    return main_parts, attachments


def classify(filename: str) -> str:
    """根据文件名返回类别。"""
    name = filename.replace(".md", "").strip().lower()
    if name.startswith("restart"):
        return "restart"
    if name.startswith("fantasy"):
        return "fantasy"
    if name.startswith("part"):
        return "part"
    return "part"


def generate_slug(filename: str) -> str:
    """根据源文件名生成子目录 slug。"""
    name = filename.replace(".md", "").strip()
    category = classify(name)
    m = re.match(r"(?:Part|Restart|Fantasy)\s+(\d+)", name, re.IGNORECASE)
    num = m[1] if m else "0"

    if category == "part":
        return f"star-project-{num}"
    elif category == "restart":
        return f"star-project-restart-{num}"
    elif category == "fantasy":
        return f"fantasy-world-{num}"
    return re.sub(r"\s+", "-", name.lower())


def sanitize_title_for_filename(title: str) -> str:
    """将条目标题清理为安全的文件名字符串。"""
    cleaned = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", title)
    cleaned = RE_LATEX.sub("", cleaned)
    cleaned = cleaned.replace("“", "").replace("”", "")
    cleaned = cleaned.replace("‘", "").replace("’", "")
    cleaned = cleaned.replace("《", "").replace("》", "")
    cleaned = RE_INVALID_FILENAME_CHARS.sub("", cleaned)
    cleaned = re.sub(r"\s+", "-", cleaned)
    cleaned = cleaned.strip("-（）()")
    cleaned = re.sub(r"-{2,}", "-", cleaned)
    if len(cleaned) > 80:
        cleaned = cleaned[:80].rstrip("-")
    return cleaned


def clean_title(title: str) -> str:
    """清理标题：去除 Markdown 链接和 LaTeX 公式。"""
    cleaned = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", title)
    cleaned = RE_LATEX.sub("", cleaned)
    return cleaned.strip()


def extract_description(text: str) -> str:
    """从正文提取第一句话作为描述。"""
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

    cleaned = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", first_line)
    cleaned = re.sub(r"</?[^>]+>", "", cleaned)
    cleaned = RE_LATEX.sub("", cleaned)
    cleaned = re.sub(r"^>\s*", "", cleaned)
    cleaned = cleaned.strip()

    m = re.match(r"(.*?[。！？…\.\!\?])", cleaned)
    if m:
        sentence = m[1]
    else:
        sentence = cleaned[:200]

    if len(sentence) > 200:
        sentence = sentence[:197] + "..."
    return sentence


def extract_chinese_date(text: str) -> datetime | None:
    """从文本中提取中文日期（2026 年 5 月 25 日 → datetime），返回最后一个。"""
    matches = list(RE_CHINESE_DATE.finditer(text))
    if not matches:
        # 尝试只匹配年月，默认日 = 1
        matches_month = list(RE_CHINESE_DATE_MONTH.finditer(text))
        if matches_month:
            m = matches_month[-1]
            return datetime(int(m[1]), int(m[2]), 1, tzinfo=CST)
        return None
    m = matches[-1]
    return datetime(int(m[1]), int(m[2]), int(m[3]), tzinfo=CST)


def yaml_single_quote(s: str) -> str:
    """将字符串转为 YAML 单引号字面量。"""
    return f"'{s.replace("'", "''")}'"


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
# 核心 1：日记条目拆分（Main Parts）
# ---------------------------------------------------------------------------
def split_into_entries(raw: str) -> list[dict]:
    """将原始文本按 #### 标题拆分为独立日记条目列表。"""
    lines = raw.split("\n")
    entries: list[dict] = []
    current_date: datetime | None = None
    current_buf: list[str] = []
    current_title: str | None = None

    def flush_entry():
        nonlocal current_title, current_buf
        if current_title is not None:
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
        m_date = RE_DATE_HEADING.match(line)
        if m_date:
            flush_entry()
            y, mo, d = int(m_date[1]), int(m_date[2]), int(m_date[3])
            current_date = datetime(y, mo, d, tzinfo=CST)
            continue

        if line.startswith("### "):
            flush_entry()
            continue

        m_entry = RE_ENTRY_HEADING.match(line)
        if m_entry:
            flush_entry()
            current_title = m_entry[1].strip()
            current_buf = []
            continue

        if current_title is not None:
            current_buf.append(line)

    flush_entry()
    return entries


def clean_entry_body(body: str) -> str:
    """清理单条目正文。"""
    body = re.sub(
        r"\n*---\n\n\[.*?返回.*?\]\(https://www\.luogu\.com\.cn/blog/guan-xing-ge/.*?\)\s*$",
        "",
        body,
    )
    body = re.sub(r"\n*---\s*$", "", body)
    return body


# ---------------------------------------------------------------------------
# 核心 2：独立文章处理（Attachments + Dust + Snow）
# ---------------------------------------------------------------------------
def transform_standalone(src_path: Path, tags: list[str],
                         default_date: datetime | None = None
                         ) -> tuple[str, str, datetime] | None:
    """将单篇独立文章转化为一个 .md 文件。

    返回 (文件名, 内容, 日期)，或 None。
    """
    if not src_path.exists():
        print(f"  ⚠ 文件不存在: {src_path}")
        return None

    with open(src_path, encoding="utf-8") as f:
        raw = f.read()

    # 检查是否已有 YAML frontmatter
    existing_title = None
    body = raw
    if raw.startswith("---"):
        parts = raw.split("---", 2)
        if len(parts) >= 3:
            # 解析已有 frontmatter 中的 title
            fm_text = parts[1]
            m = re.search(r'^title:\s*(.+)$', fm_text, re.MULTILINE)
            if m:
                existing_title = m[1].strip().strip('"').strip("'")
            body = parts[2].strip() + "\n"

    # 提取标题
    if existing_title:
        title = clean_title(existing_title)
    else:
        # 从第一个 ### 标题提取
        m = re.search(r"^###\s+(.+)$", body, re.MULTILINE)
        title = clean_title(m[1].strip()) if m else src_path.stem

    # 提取日期：优先中文日期，其次文本末尾日期，再次默认值
    date = extract_chinese_date(body) or extract_chinese_date(raw)
    description = extract_description(body)

    # 文件名（others 目录下不含日期前缀）
    title_slug = sanitize_title_for_filename(title)
    if not title_slug:
        title_slug = re.sub(r"\s+", "-", src_path.stem.lower())
    file_name = f"{title_slug}.md"

    fm = build_frontmatter(title, date, description, tags, featured=True)
    output_content = fm + body

    return file_name, output_content, date


def transform_standalone_article(src_path: Path, tags: list[str],
                                 default_date: datetime | None = None
                                 ) -> tuple[str, str, datetime] | None:
    """处理 MarkdownFiles/ 下的附件文章：无 frontmatter，以 ### 标题开头。

    去掉开头的 ### 标题行（已写入 frontmatter title）。
    """
    if not src_path.exists():
        print(f"  ⚠ 文件不存在: {src_path}")
        return None

    with open(src_path, encoding="utf-8") as f:
        raw = f.read()

    # 提取第一个 ### 标题
    m = re.search(r"^###\s+(.+)$", raw, re.MULTILINE)
    title = clean_title(m[1].strip()) if m else src_path.stem

    # 去掉第一个 ### 标题行及其前面的空行
    if m:
        body = raw[:m.start()] + raw[m.end():]
        body = body.strip() + "\n"
    else:
        body = raw

    # 提取日期
    date = extract_chinese_date(body) or extract_chinese_date(raw)
    if date is None:
        date = default_date
    if date is None:
        # fallback: 文件修改时间
        mtime = os.path.getmtime(src_path)
        date = datetime.fromtimestamp(mtime, tz=CST)

    description = extract_description(body)

    # 文件名（others 目录下不含日期前缀）
    title_slug = sanitize_title_for_filename(title)
    if not title_slug:
        title_slug = re.sub(r"\s+", "-", src_path.stem.lower())
    file_name = f"{title_slug}.md"

    fm = build_frontmatter(title, date, description, tags)
    output_content = fm + body

    return file_name, output_content, date


# ---------------------------------------------------------------------------
# Main Parts 转化（拆分版）
# ---------------------------------------------------------------------------
def transform_diary_file(filename: str) -> tuple[str, list[tuple[str, str, datetime]]] | None:
    """处理 Main Parts 中的日记文件。"""
    src_path = MARKDOWN_DIR / filename
    if not src_path.exists():
        print(f"  ⚠ 跳过: {src_path}")
        return None

    with open(src_path, encoding="utf-8") as f:
        raw = f.read()

    dir_slug = generate_slug(filename)
    category = classify(filename)
    tags = DEFAULT_TAGS.get(category, ["others"])

    entries = split_into_entries(raw)
    if not entries:
        print(f"  ⚠ 未找到条目: {filename}")
        return None

    files: list[tuple[str, str, datetime]] = []
    used_names: dict[str, int] = {}

    for i, entry in enumerate(entries):
        date = entry["date"]
        title = entry["title"]
        body = clean_entry_body(entry["body"])

        if date is None:
            if files:
                date = files[-1][2]
            else:
                mtime = os.path.getmtime(src_path)
                date = datetime.fromtimestamp(mtime, tz=CST)

        description = extract_description(body)
        clean = clean_title(title)

        title_slug = sanitize_title_for_filename(clean)
        if not title_slug:
            title_slug = f"entry-{i + 1:03d}"
        date_prefix = date.strftime("%Y-%m-%d")
        base_name = f"{date_prefix}-{title_slug}"

        if base_name in used_names:
            used_names[base_name] += 1
            file_name = f"{base_name}-{used_names[base_name]}"
        else:
            used_names[base_name] = 0
            file_name = base_name
        file_name += ".md"

        fm = build_frontmatter(clean, date, description, tags)
        output_content = fm + body
        files.append((file_name, output_content, date))

    return dir_slug, files


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def main():
    print("=" * 60)
    print("  AstroPaper 博客文章转化脚本")
    print("=" * 60)
    print()

    if not FILELIST_PATH.exists():
        print(f"❌ Filelist 不存在: {FILELIST_PATH}")
        return 1

    main_files, attachment_files = parse_filelist_sections(FILELIST_PATH)
    print(f"📄 Main Parts: {len(main_files)} 个文件")
    for f in main_files:
        print(f"    - {f}")
    print(f"📄 Attachments: {len(attachment_files)} 个文件")
    for f in attachment_files:
        print(f"    - {f}")
    print(f"📄 额外: Dust.md, Snow/release/export2html.md")
    print()

    # 清理旧目录
    old_dirs = [
        "stars-during-lifetime-1", "stars-during-lifetime-2",
        "stars-during-lifetime-3", "stars-during-lifetime-4",
        "stars-during-lifetime-5", "stars-during-lifetime-6",
        "stars-during-lifetime-7",
        "stars-during-lifetime-restart-1", "stars-during-lifetime-restart-2",
        "stars-during-lifetime-restart-3",
        "star-project-1", "star-project-2", "star-project-3",
        "star-project-4", "star-project-5", "star-project-6",
        "star-project-7",
        "star-project-restart-1", "star-project-restart-2",
        "star-project-restart-3",
        "fantasy-world-1", "fantasy-world-2",
        "others", "snow",
    ]
    cleaned = 0
    for name in old_dirs:
        fp = POSTS_DIR / f"{name}.md"
        if fp.exists():
            fp.unlink()
            cleaned += 1
        dp = POSTS_DIR / name
        if dp.exists() and dp.is_dir():
            shutil.rmtree(dp)
            cleaned += 1
    if cleaned:
        print(f"🧹 清理了 {cleaned} 个旧文件/目录")
        print()

    total_entries = 0
    total_written = 0

    def write_files(dir_path: Path, entry_files: list[tuple[str, str, datetime]]):
        nonlocal total_entries, total_written
        dir_path.mkdir(parents=True, exist_ok=True)
        for fname, content, _date in entry_files:
            output_path = dir_path / fname
            if output_path.exists():
                with open(output_path, encoding="utf-8") as f:
                    if f.read() == content:
                        total_entries += 1
                        continue
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(content)
            total_written += 1
            total_entries += 1

    # ---- Main Parts ----
    print(">>> Main Parts")
    for filename in main_files:
        print(f"  🔄 {filename}", end="")
        result = transform_diary_file(filename)
        if result is None:
            print("  ⚠ 跳过")
            continue
        dir_slug, entry_files = result
        write_files(POSTS_DIR / dir_slug, entry_files)
        print(f" → {dir_slug}/ ({len(entry_files)} entries)")

    # ---- Attachments ----
    print()
    print(">>> Attachments")
    # 这些文件的日期记录在 Overview.md 中，文件本身无时间戳
    ATTACHMENT_DATES = {
        "Thelema 1.md": datetime(2023, 12, 16, tzinfo=CST),
        "Thelema 2.md": datetime(2023,  9, 30, tzinfo=CST),
        "Thelema 3.md": datetime(2024,  4, 27, tzinfo=CST),
        "ForLogic.md":  datetime(2023,  3, 18, tzinfo=CST),
        "Nirvana.md":   datetime(2024,  1,  1, tzinfo=CST),
    }
    others_dir = POSTS_DIR / "others"
    for filename in attachment_files:
        src_path = MARKDOWN_DIR / filename
        default_date = ATTACHMENT_DATES.get(filename)
        print(f"  🔄 {filename}", end="")
        result = transform_standalone_article(src_path, ATTACHMENT_TAGS,
                                              default_date=default_date)
        if result is None:
            print("  ⚠ 跳过")
            continue
        write_files(others_dir, [result])
        print(f" → others/{result[0]}")

    # ---- Dust.md ----
    print()
    print(">>> 额外文件")
    print(f"  🔄 Dust.md", end="")
    result = transform_standalone(EXTRA_DUST, ["小说", "尘"],
                                  default_date=datetime(2026, 5, 25, tzinfo=CST))
    if result:
        write_files(others_dir, [result])
        print(f" → others/{result[0]}")

    # ---- Snow/release/export2html.md ----
    print(f"  🔄 Snow/release/export2html.md", end="")
    result = transform_standalone(EXTRA_SNOW, ["小说", "孤灯夜雪"],
                                  default_date=datetime(2026, 5, 1, tzinfo=CST))
    if result:
        write_files(others_dir, [result])
        print(f" → others/{result[0]}")

    print()
    print(f"✅ 完成！共 {total_entries} 个条目")
    print(f"   新写入: {total_written}")
    print(f"   输出目录: {POSTS_DIR}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
