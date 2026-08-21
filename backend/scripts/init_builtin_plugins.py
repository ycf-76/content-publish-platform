"""
初始化内置插件数据到数据库

将examples/目录下的6个示例插件导入到plugins表中
"""

import json
import os
import sys
from pathlib import Path
from datetime import datetime

# 添加项目根目录到路径
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# 读取.env文件获取数据库URL
from dotenv import load_dotenv
load_dotenv(backend_dir / '.env')

import os
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./test.db")

if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL)


# 内置插件列表
BUILTIN_PLUGINS = [
    "hello-world",
    "text-translator",
    "sentiment-analyzer",
    "rss-monitor",
    "weibo-publisher",
    "notification-bot"
]


def load_plugin_json(plugin_name: str) -> dict:
    """加载插件的plugin.json文件"""
    plugin_dir = backend_dir.parent / "examples" / plugin_name
    plugin_file = plugin_dir / "plugin.json"

    if not plugin_file.exists():
        print(f"❌ Plugin file not found: {plugin_file}")
        return None

    with open(plugin_file, 'r', encoding='utf-8') as f:
        return json.load(f)


def insert_plugin_to_db(session, plugin_data: dict) -> bool:
    """
    将插件数据插入数据库

    Args:
        session: SQLAlchemy session
        plugin_data: 从plugin.json加载的数据

    Returns:
        bool: 是否成功插入
    """
    try:
        from sqlalchemy import text

        # 构建SQL插入语句
        sql = text("""
            INSERT INTO plugins (
                id, name, version, description, category, status,
                author_name, author_email, entry_point, manifest_json,
                capabilities, permissions, config_schema, display_icon,
                display_color, pricing_model, price_monthly,
                events_publishes, events_subscribes, dependencies,
                is_builtin, created_at, updated_at
            ) VALUES (
                :id, :name, :version, :description, :category, :status,
                :author_name, :author_email, :entry_point, :manifest_json,
                :capabilities, :permissions, :config_schema, :display_icon,
                :display_color, :pricing_model, :price_monthly,
                :events_publishes, :events_subscribes, :dependencies,
                :is_builtin, NOW(), NOW()
            )
            ON DUPLICATE KEY UPDATE
                name = VALUES(name),
                version = VALUES(version),
                description = VALUES(description),
                manifest_json = VALUES(manifest_json),
                updated_at = NOW()
        """)

        # 提取作者信息
        author = plugin_data.get("author", {})
        author_name = author.get("name", "Platform Team") if isinstance(author, dict) else str(author)
        author_email = author.get("email", "") if isinstance(author, dict) else ""

        # 执行插入
        params = {
            'id': plugin_data['id'],
            'name': plugin_data['name'],
            'version': plugin_data['version'],
            'description': plugin_data.get('description', ''),
            'category': plugin_data.get('category', 'workflow_node'),
            'status': 'active',
            'author_name': author_name,
            'author_email': author_email,
            'entry_point': plugin_data.get('entry_point', 'main.py'),
            'manifest_json': json.dumps(plugin_data, ensure_ascii=False),
            'capabilities': json.dumps(plugin_data.get('capabilities', [])),
            'permissions': json.dumps(plugin_data.get('permissions_required', [])),
            'config_schema': json.dumps(plugin_data.get('config_schema', {})),
            'display_icon': plugin_data.get('display_icon', '📦'),
            'display_color': '#6366f1',  # 默认紫色
            'pricing_model': plugin_data.get('pricing_model', 'free'),
            'price_monthly': 0.0,
            'events_publishes': json.dumps(plugin_data.get('events_emits', [])),
            'events_subscribes': json.dumps(plugin_data.get('events_subscribes', [])),
            'dependencies': json.dumps(plugin_data.get('dependencies', [])),
            'is_builtin': True
        }

        session.execute(sql, params)
        return True

    except Exception as e:
        print(f"❌ Error inserting plugin {plugin_data.get('id')}: {e}")
        import traceback
        traceback.print_exc()
        return False


def init_plugin_stats(session, plugin_id: str):
    """初始化插件统计记录"""
    try:
        from sqlalchemy import text

        sql = text("""
            INSERT IGNORE INTO plugin_stats (plugin_id)
            VALUES (:plugin_id)
        """)
        session.execute(sql, {'plugin_id': plugin_id})

    except Exception as e:
        print(f"⚠️ Warning: Could not init stats for {plugin_id}: {e}")


def main():
    """主函数：初始化所有内置插件"""
    print("=" * 70)
    print("  初始化内置插件数据到数据库")
    print("=" * 70)

    success_count = 0
    fail_count = 0

    with engine.connect() as connection:
        # 开始事务
        trans = connection.begin()

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

                # 创建Session对象（使用连接）
                from sqlalchemy.orm import sessionmaker
                SessionLocal = sessionmaker(bind=connection)
                session = SessionLocal()

                # 插入到plugins表
                if insert_plugin_to_db(session, plugin_data):
                    # 初始化统计记录
                    init_plugin_stats(session, plugin_data['id'])

                    success_count += 1
                    print(f"   ✅ 成功导入")
                else:
                    fail_count += 1
                    print(f"   ❌ 导入失败")

                session.close()

            # 提交事务
            trans.commit()
            print("\n" + "=" * 70)

        except Exception as e:
            # 回滚事务
            trans.rollback()
            print(f"\n❌ 发生错误，已回滚所有更改: {e}")
            import traceback
            traceback.print_exc()
            return False

    # 输出统计
    print(f"\n✨ 初始化完成!")
    print(f"   成功: {success_count}/{len(BUILTIN_PLUGINS)} 个插件")
    print(f"   失败: {fail_count} 个插件")

    if success_count == len(BUILTIN_PLUGINS):
        print("\n🎉 所有内置插件已成功导入数据库！")
        return True
    else:
        print("\n⚠️ 部分插件导入失败，请检查日志")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)