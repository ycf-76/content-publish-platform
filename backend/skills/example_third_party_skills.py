"""第三方 Skill 示例：诗意文案风格。

这是一个示范插件，展示如何在 backend/skills/ 目录下新增自己的 Skill，
无需修改 app/ 内任何代码，重启后端即可生效。

开发步骤：
1. 在 backend/skills/ 下新建 .py 文件（本文件即为示例）
2. import Skill 基类和 register 装饰器 
3. 定义 Skill 子类，声明 node_type + name + display_name 等元数据
4. 用 @register 装饰器注册到全局 SkillRegistry
5. 重启后端，前端 GET /api/skills 即可看到新 Skill

前端右侧工作区会自动渲染这个 Skill，用户选择后，
工作流运行到 copywrite 节点时会加载并执行这个 Skill。
"""

from app.agents.skills.copywrite_builder import CopywriteSkillBase
from app.agents.skills.registry import register


@register
class PoeticCopywriteSkill(CopywriteSkillBase):
    """诗意文案风格：文艺、含蓄、有画面感。

    适合：文学、旅行、摄影、生活方式类内容。
    """

    name = "poetic"
    display_name = "诗意文艺风"
    description = "语气含蓄有画面感，少 emoji，适合文艺类内容"

    # 注入到 LLM prompt 的调性指令
    style_instruction = (
        "诗意文艺风：语气含蓄克制，多用意象和比喻，"
        "有画面感和留白，少用 emoji，像散文诗"
    )

    # LLM 不可用时的降级模板（含 {topic}/{direction} 占位符）
    fallback_template = (
        "{topic}，是时间的注脚。\n\n"
        "关于{direction}，想说的话不多。\n\n"
        "1. 有些事，慢一点更清楚\n"
        "2. 有些路，独自行走才看见风景\n"
        "3. 有些答案，时间会给\n\n"
        "愿你与美好不期而遇。\n"
        "（注：LLM 不可用，降级模板生成）"
    )
