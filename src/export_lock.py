"""输出（导出）+ 锁定。

把某个 trips/ 子文件夹（行程 / 孤儿单据 / 市内交通 / 普通打车）输出到
桌面「公司待报销发票」目录，并把该文件夹「锁定」——后续重新生成行程时
不再变动/处理它（其发票从重新分组中排除，物理文件夹保留）。

状态持久化在 data/exported.json。
"""
from __future__ import annotations

import json
import logging
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)

DATA_DIR = Path("data")
EXPORTED_FILE = DATA_DIR / "exported.json"

# 输出目标目录：默认 桌面/待报销发票，可用环境变量覆盖
EXPORT_DEST = Path(os.environ.get("TRAVEL_EXPORT_DIR") or (Path.home() / "Desktop" / "待报销发票"))


def _ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def load_exported() -> List[Dict]:
    """读取已输出记录。文件不存在或损坏则返回空列表。"""
    if not EXPORTED_FILE.exists():
        return []
    try:
        with open(EXPORTED_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        items = data.get("exported", []) if isinstance(data, dict) else data
        return items if isinstance(items, list) else []
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"Failed to read {EXPORTED_FILE}: {e}")
        return []


def _save_exported(items: List[Dict]) -> None:
    _ensure_data_dir()
    tmp = EXPORTED_FILE.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"exported": items}, f, ensure_ascii=False, indent=2)
    tmp.replace(EXPORTED_FILE)


def is_exported(key: str) -> bool:
    return any(item.get("key") == key for item in load_exported())


def exported_keys() -> Set[str]:
    return {item.get("key") for item in load_exported() if item.get("key")}


def exported_basenames() -> Set[str]:
    """所有已输出文件夹内发票文件名集合——用于在重新分组时排除这些发票。"""
    names: Set[str] = set()
    for item in load_exported():
        for n in item.get("basenames", []):
            names.add(n)
    return names


def _kind_from_folder(folder: Path) -> str:
    if folder.name == "市内交通":
        return "市内交通"
    if folder.name == "孤儿单据":
        return "孤儿单据"
    if folder.name == "普通打车":
        return "普通打车"
    return "trip"


def _folder_totals(folder: Path) -> Dict:
    """统计文件夹内发票数量与金额（从文件名解析）。"""
    from src.trip_grouper import Invoice  # 延迟导入
    count = 0
    total = 0.0
    basenames: List[str] = []
    for pdf in sorted(folder.glob("*.pdf")):
        count += 1
        basenames.append(pdf.name)
        inv = Invoice.from_filename(pdf)
        if inv:
            total += getattr(inv, "amount", 0.0) or 0.0
    return {"count": count, "total": round(total, 2), "basenames": basenames}


def export_folder(trips_root: Path, key: str) -> Dict:
    """输出 trips_root/key 文件夹到桌面目录并锁定。

    - 确保 统计单.docx 存在（缺失则生成）。
    - 复制文件夹内全部文件（PDF + 统计单）到 EXPORT_DEST/<key>（保留层级）。
    - 写入 data/exported.json（已存在则更新）。
    """
    from src.summary_sheet import generate_for_folder, SUMMARY_FILENAME

    trips_root = Path(trips_root)
    src = trips_root.joinpath(*key.split("/"))
    if not src.is_dir():
        raise FileNotFoundError(f"文件夹不存在: {src}")

    kind = _kind_from_folder(src)

    # 确保 统计单 存在（缺失才生成；已存在则保留——锁定语义下不覆盖已有内容）
    summary_path = src / SUMMARY_FILENAME
    if not summary_path.exists():
        try:
            generate_for_folder(src, kind)
        except Exception as e:
            logger.warning(f"生成统计单失败（继续输出）: {e}")

    dest = EXPORT_DEST.joinpath(*key.split("/"))
    dest.mkdir(parents=True, exist_ok=True)

    copied = 0
    for item in src.iterdir():
        if not item.is_file():
            continue
        try:
            shutil.copy2(item, dest / item.name)
            copied += 1
        except Exception as e:
            logger.error(f"复制失败 {item.name}: {e}")

    totals = _folder_totals(src)

    entry = {
        "key": key,
        "kind": kind,
        "dest": str(dest),
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "invoice_count": totals["count"],
        "total": totals["total"],
        "basenames": totals["basenames"],
        "files_copied": copied,
    }

    items = load_exported()
    items = [it for it in items if it.get("key") != key]  # 去重
    items.append(entry)
    _save_exported(items)

    logger.info(f"Exported & locked: {key} -> {dest} ({copied} files)")
    return entry
