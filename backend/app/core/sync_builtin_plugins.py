"""
Sync Plugins to Database
扫描 plugins/builtin/*/plugin.json 和 plugins/third_party/*/plugin.json，
将插件元数据 upsert 到数据库

每次应用启动时调用，确保 DB 中的插件与文件系统保持同步
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.db.plugin_models import Plugin as PluginModel, PluginCategory, PluginStatus

logger = logging.getLogger(__name__)

BUILTIN_DIR = Path(__file__).parent.parent.parent / "plugins" / "builtin"
THIRD_PARTY_DIR = Path(__file__).parent.parent.parent / "plugins" / "third_party"


def _load_plugin_json(plugin_dir: Path) -> Dict[str, Any] | None:
    json_path = plugin_dir / "plugin.json"
    if not json_path.exists():
        return None
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _parse_manifest(data: Dict[str, Any], is_builtin: bool = True) -> Dict[str, Any]:
    author = data.get("author", {})
    if isinstance(author, str):
        author = {"name": author}

    return {
        "id": data["id"],
        "name": data["name"],
        "version": data.get("version", "0.0.1"),
        "description": data.get("description", ""),
        "category": data.get("category", "utility").upper(),
        "status": PluginStatus.ACTIVE.value,
        "author_name": author.get("name", "Platform Team"),
        "author_email": author.get("email"),
        "entry_point": data.get("entry_point", ""),
        "manifest_json": data,
        "capabilities": data.get("capabilities", []),
        "permissions": data.get("permissions_required", []),
        "config_schema": data.get("config_schema"),
        "display_icon": data.get("display_icon", "📦"),
        "display_color": "#6366f1",
        "pricing_model": data.get("pricing_model", "free").upper(),
        "price_monthly": 0.0,
        "events_publishes": data.get("events_emits", []),
        "events_subscribes": data.get("events_subscribes", []),
        "dependencies": data.get("dependencies") or None,
        "is_builtin": is_builtin,
    }


async def _sync_plugin_dir(
    plugin_dir: Path,
    is_builtin: bool,
    session: AsyncSession,
) -> Dict[str, int]:
    scanned = 0
    synced = 0
    skipped = 0

    data = _load_plugin_json(plugin_dir)
    if not data:
        return {"scanned": 0, "synced": 0, "skipped": 0}

    scanned += 1
    plugin_id = data.get("id", "")
    if not plugin_id:
        logger.warning(f"Skipping {plugin_dir.name}: no id in plugin.json")
        return {"scanned": 1, "synced": 0, "skipped": 0}

    fields = _parse_manifest(data, is_builtin=is_builtin)

    result = await session.execute(
        select(PluginModel).where(PluginModel.id == plugin_id)
    )
    existing = result.scalar_one_or_none()

    if existing:
        needs_update = (
            existing.version != fields["version"]
            or existing.name != fields["name"]
            or existing.description != fields["description"]
        )
        if needs_update:
            for key, value in fields.items():
                if key == "id":
                    continue
                setattr(existing, key, value)
            synced += 1
            source = "builtin" if is_builtin else "third_party"
            logger.debug(f"Updated {source} plugin: {plugin_id}")
        else:
            skipped += 1
    else:
        new_plugin = PluginModel(**fields)
        session.add(new_plugin)
        synced += 1
        source = "builtin" if is_builtin else "third_party"
        logger.debug(f"Inserted {source} plugin: {plugin_id}")

    return {"scanned": scanned, "synced": synced, "skipped": skipped}


async def sync_builtin_plugins_to_db() -> Dict[str, int]:
    """
    扫描所有内置插件的 plugin.json，upsert 到数据库

    Returns:
        {"scanned": int, "synced": int, "skipped": int}
    """
    total = {"scanned": 0, "synced": 0, "skipped": 0}

    if not BUILTIN_DIR.exists():
        logger.warning(f"Builtin plugins dir not found: {BUILTIN_DIR}")
    else:
        plugin_dirs = [d for d in BUILTIN_DIR.iterdir() if d.is_dir() and (d / "plugin.json").exists()]
        async with AsyncSessionLocal() as session:
            for plugin_dir in plugin_dirs:
                result = await _sync_plugin_dir(plugin_dir, is_builtin=True, session=session)
                for k in total:
                    total[k] += result[k]
            await session.commit()

    return total


async def sync_all_plugins_to_db() -> Dict[str, int]:
    """
    扫描内置 + 第三方插件的 plugin.json，upsert 到数据库

    Returns:
        {"scanned": int, "synced": int, "skipped": int}
    """
    total = {"scanned": 0, "synced": 0, "skipped": 0}

    async with AsyncSessionLocal() as session:
        for plugin_dir, is_builtin in _iter_plugin_dirs():
            result = await _sync_plugin_dir(plugin_dir, is_builtin=is_builtin, session=session)
            for k in total:
                total[k] += result[k]

        await session.commit()

    return total


def _iter_plugin_dirs():
    """迭代所有插件目录 (builtin + third_party)，yield (Path, is_builtin)"""
    for label, base_dir, is_builtin in [
        ("builtin", BUILTIN_DIR, True),
        ("third_party", THIRD_PARTY_DIR, False),
    ]:
        if not base_dir.exists():
            logger.debug(f"{label} plugins dir not found: {base_dir}")
            continue
        for d in base_dir.iterdir():
            if d.is_dir() and (d / "plugin.json").exists():
                yield d, is_builtin


async def sync_single_third_party_plugin(plugin_id: str) -> Dict[str, int]:
    """
    同步单个第三方插件到数据库（上传安装后调用）

    Args:
        plugin_id: 插件ID

    Returns:
        {"scanned": int, "synced": int, "skipped": int}
    """
    plugin_dir = THIRD_PARTY_DIR / plugin_id
    if not plugin_dir.exists() or not (plugin_dir / "plugin.json").exists():
        logger.warning(f"Third-party plugin dir not found: {plugin_dir}")
        return {"scanned": 0, "synced": 0, "skipped": 0}

    async with AsyncSessionLocal() as session:
        result = await _sync_plugin_dir(plugin_dir, is_builtin=False, session=session)
        await session.commit()

    return result