"""
初始化内置插件数据到数据库（简化版）

使用SQLite存储，方便测试
"""

import json
import sqlite3
import os
from pathlib import Path
from datetime import datetime


# 内置插件列表
BUILTIN_PLUGINS = [
    "hello-world",
    "text-translator",
    "sentiment-analyzer",
    "rss-monitor",
    "weibo-publisher",
    "notification-bot"
]


def get_db_path():
    """获取SQLite数据库路径"""
    backend_dir = Path(__file__).parent.parent
    db_path = backend_dir / "plugins.db"
    return str(db_path)


def init_db():
    """初始化数据库表结构"""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 创建plugins表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS plugins (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            version TEXT NOT NULL DEFAULT '0.0.1',
            description TEXT,
            category TEXT NOT NULL DEFAULT 'workflow_node',
            status TEXT NOT NULL DEFAULT 'active',
            author_name TEXT NOT NULL DEFAULT '',
            author_email TEXT,
            entry_point TEXT NOT NULL DEFAULT 'main.py',
            manifest_json TEXT,
            capabilities TEXT,
            permissions TEXT,
            config_schema TEXT,
            display_icon TEXT NOT NULL DEFAULT '📦',
            display_color TEXT NOT NULL DEFAULT '#6366f1',
            pricing_model TEXT NOT NULL DEFAULT 'free',
            price_monthly REAL NOT NULL DEFAULT 0.0,
            events_publishes TEXT,
            events_subscribes TEXT,
            dependencies TEXT,
            is_builtin INTEGER NOT NULL DEFAULT 0,
            created_at TEXT,
            updated_at TEXT
        )
    """)

    # 创建plugin_stats表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS plugin_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plugin_id TEXT UNIQUE NOT NULL,
            total_executions INTEGER DEFAULT 0,
            successful_executions INTEGER DEFAULT 0,
            failed_executions INTEGER DEFAULT 0,
            avg_execution_time_ms REAL DEFAULT 0.0,
            last_error TEXT,
            snapshot_at TEXT
        )
    """)

    conn.commit()
    conn.close()

    print(f"✅ 数据库已初始化: {db_path}")


def load_plugin_json(plugin_name: str) -> dict:
    """加载插件的plugin.json文件"""
    backend_dir = Path(__file__).parent.parent
    plugin_dir = backend_dir.parent / "examples" / plugin_name
    plugin_file = plugin_dir / "plugin.json"

    if not plugin_file.exists():
        print(f"❌ Plugin file not found: {plugin_file}")
        return None

    with open(plugin_file, 'r', encoding='utf-8') as f:
        return json.load(f)


def insert_plugin(cursor, plugin_data: dict) -> bool:
    """将插件数据插入数据库"""
    try:
        # 提取作者信息
        author = plugin_data.get("author", {})
        author_name = author.get("name", "Platform Team") if isinstance(author, dict) else str(author)
        author_email = author.get("email", "") if isinstance(author, dict) else ""

        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

        # 插入或更新
        cursor.execute("""
            INSERT OR REPLACE INTO plugins (
                id, name, version, description, category, status,
                author_name, author_email, entry_point, manifest_json,
                capabilities, permissions, config_schema, display_icon,
                display_color, pricing_model, price_monthly,
                events_publishes, events_subscribes, dependencies,
                is_builtin, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            plugin_data['id'],
            plugin_data['name'],
            plugin_data['version'],
            plugin_data.get('description', ''),
            plugin_data.get('category', 'workflow_node'),
            'active',  # status
            author_name,
            author_email,
            plugin_data.get('entry_point', 'main.py'),
            json.dumps(plugin_data, ensure_ascii=False),  # manifest_json
            json.dumps(plugin_data.get('capabilities', [])),  # capabilities
            json.dumps(plugin_data.get('permissions_required', [])),  # permissions
            json.dumps(plugin_data.get('config_schema', {})),  # config_schema
            plugin_data.get('display_icon', '📦'),  # display_icon
            '#6366f1',  # display_color (默认紫色)
            plugin_data.get('pricing_model', 'free'),  # pricing_model
            0.0,  # price_monthly
            json.dumps(plugin_data.get('events_emits', [])),  # events_publishes
            json.dumps(plugin_data.get('events_subscribes', [])),  # events_subscribes
            json.dumps(plugin_data.get('dependencies', [])),  # dependencies
            1,  # is_builtin = True
            now,  # created_at
            now   # updated_at
        ))

        # 初始化统计记录
        cursor.execute("""
            INSERT OR IGNORE INTO plugin_stats (plugin_id, snapshot_at)
            VALUES (?, ?)
        """, (plugin_data['id'], now))

        return True

    except Exception as e:
        print(f"❌ Error inserting plugin {plugin_data.get('id')}: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """主函数：初始化所有内置插件"""
    print("=" * 70)
    print("  初始化内置插件数据到数据库（简化版）")
    print("=" * 70)

    # 初始化数据库
    init_db()

    # 连接数据库
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    success_count = 0
    fail_count = 0

    try:
        for plugin_name in BUILTIN_PLUGINS:
            print(f"\n📦 处理插件: {plugin_name}")

            # 加载plugin.json
            plugin_data = load_plugin_json(plugin_name)
            if not plugin_data:
                fail_count += 1
                continue

            # 显示基本信息
            print(f"   名称: {plugin_data.get('name')}")
            print(f"   类型: {plugin_data.get('category')}")
            print(f"   版本: {plugin_data.get('version')}")

            # 插入到数据库
            if insert_plugin(cursor, plugin_data):
                success_count += 1
                print(f"   ✅ 成功导入")
            else:
                fail_count += 1
                print(f"   ❌ 导入失败")

        # 提交事务
        conn.commit()
        print("\n" + "=" * 70)

    except Exception as e:
        # 回滚
        conn.rollback()
        print(f"\n❌ 发生错误，已回滚: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        conn.close()

    # 输出统计
    print(f"\n✨ 初始化完成!")
    print(f"   成功: {success_count}/{len(BUILTIN_PLUGINS)} 个插件")
    print(f"   失败: {fail_count} 个插件")

    if success_count == len(BUILTIN_PLUGINS):
        print("\n🎉 所有内置插件已成功导入数据库！")
        print(f"\n📊 查看数据库: {db_path}")
        print("   可用命令: sqlite3 plugins.db \"SELECT * FROM plugins;\"")
        return True
    else:
        print("\n⚠️ 部分插件导入失败，请检查日志")
        return False


if __name__ == "__main__":
    import sys
    success = main()
    sys.exit(0 if success else 1)