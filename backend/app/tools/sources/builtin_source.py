"""内置中文话题数据源（零网络依赖）。

用途：
- 国外 API（Reddit/HackerNews）访问困难或搜不到中文生活方式话题时兜底
- 预设小红书常见类目的热门话题库，按关键词匹配返回
- 每条数据带 platform="builtin" 标注来源

覆盖类目：
- 穿搭（夏日穿搭/秋冬穿搭/通勤/约会/微胖/小个子）
- 美妆（妆容/护肤/口红/底妆/眼妆）
- 美食（早餐/减脂餐/家常菜/烘焙/奶茶）
- 旅行（国内游/周末游/拍照/攻略）
- 健身（减脂/塑形/瑜伽/居家训练）
- 学习（笔记/时间管理/书单/考证）
- 职场（穿搭/沟通/副业/跳槽）
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from app.tools.sources.base import ContentSource, TrendingContent

logger = logging.getLogger(__name__)


@dataclass
class _TopicItem:
    """预设话题条目。"""
    title: str
    summary: str
    content: str
    author: str
    likes: int
    comments: int
    shares: int
    tags: list[str]
    keywords: list[str]  # 用于匹配用户搜索关键词


# 内置话题库（按类目分组，互动量为模拟值，符合小红书真实量级）
_TOPIC_DB: list[_TopicItem] = [
    # ===== 穿搭类 =====
    _TopicItem(
        title="夏日清爽穿搭｜5套通勤look，显瘦又高级",
        summary="分享5套夏日通勤穿搭，棉麻材质+高腰线设计，显瘦显高，适合上班族",
        content="夏天穿搭重点：1. 选透气材质（棉麻/雪纺）2. 高腰线拉比例 3. 莫兰迪色系显高级\n第一套：白色棉麻衬衫+卡其高腰阔腿裤\n第二套：雾霾蓝连衣裙+小白鞋\n第三套：条纹t恤+米色西装裤\n第四套：黑色吊带+牛仔半裙\n第五套：燕麦色短袖+烟管裤",
        author="穿搭小天才",
        likes=28400, comments=892, shares=1456,
        tags=["穿搭", "夏日", "通勤", "显瘦"],
        keywords=["夏日", "穿搭", "女生", "通勤", "显瘦", "清爽"],
    ),
    _TopicItem(
        title="微胖女孩夏日穿搭指南｜遮肉不臃肿",
        summary="120斤微胖女生夏日穿搭分享，A字裙+V领上衣，遮肉显瘦",
        content="微胖女生穿搭要点：\n1. V领拉长颈部线条，显脸小\n2. A字裙遮胯宽大腿粗\n3. 选垂坠感面料，避免贴身\n4. 深色系内搭+亮色外套\n推荐单品：黑色V领t恤+卡其A字半裙+小白鞋",
        author="微胖穿搭日记",
        likes=18600, comments=567, shares=892,
        tags=["穿搭", "微胖", "夏日", "遮肉"],
        keywords=["夏日", "穿搭", "女生", "微胖", "遮肉", "显瘦", "胖"],
    ),
    _TopicItem(
        title="小个子穿搭｜155cm夏日显高10cm技巧",
        summary="155小个子女生夏日穿搭，高腰线+短上衣+同色系，视觉显高10cm",
        content="小个子显高公式：\n1. 高腰线是灵魂（裙子/裤子都要高腰）\n2. 短上衣+高腰下装=三七分比例\n3. 同色系穿搭拉长视觉\n4. 尖头鞋延伸腿部线条\n5. 避免oversize压个子\n推荐：白色短上衣+牛仔高腰短裤+小白鞋",
        author="小个子穿搭馆",
        likes=22300, comments=734, shares=1120,
        tags=["穿搭", "小个子", "夏日", "显高"],
        keywords=["夏日", "穿搭", "女生", "小个子", "显高", "155"],
    ),
    _TopicItem(
        title="约会穿搭｜温柔风连衣裙，男朋友都夸好看",
        summary="夏日约会穿搭分享，碎花连衣裙+针织开衫，温柔又甜美",
        content="约会穿搭关键词：温柔、甜美、不太用力\n1. 碎花连衣裙是夏日约会首选\n2. 配针织开衫增加层次感\n3. 珍珠耳环提升精致度\n4. 裸色高跟鞋延伸腿部\n5. 淡妆+卷发，不要太浓\n单品推荐：杏色碎花连衣裙+米色针织开衫+裸色单鞋",
        author="温柔穿搭",
        likes=15800, comments=445, shares=678,
        tags=["穿搭", "约会", "夏日", "连衣裙"],
        keywords=["夏日", "穿搭", "女生", "约会", "连衣裙", "温柔"],
    ),
    _TopicItem(
        title="秋冬大衣穿搭｜通勤显瘦不臃肿",
        summary="秋冬大衣穿搭技巧，H版型+腰带，显瘦显高适合通勤",
        content="秋冬大衣挑选要点：\n1. H版型最显瘦，A版型挑人\n2. 长度到小腿肚最显高\n3. 腰带款提升腰线\n4. 驼色/黑色/灰色百搭\n5. 内搭选轻薄款避免臃肿\n推荐搭配：驼色大衣+黑色高领毛衣+黑色西装裤+短靴",
        author="秋冬穿搭",
        likes=19800, comments=567, shares=890,
        tags=["穿搭", "秋冬", "大衣", "通勤"],
        keywords=["秋冬", "穿搭", "女生", "大衣", "通勤", "显瘦"],
    ),

    # ===== 美妆类 =====
    _TopicItem(
        title="夏日持妆12小时｜油皮底妆教程",
        summary="油皮夏日底妆教程，控妆前+哑光粉底+定妆喷雾，持妆12小时不脱妆",
        content="油皮夏日底妆步骤：\n1. 妆前控油：紫色隔离修饰暗沉\n2. 选哑光粉底液（避免水光感）\n3. 海绵拍开，少量多次\n4. 遮瑕点涂（眼下/痘印）\n5. 散粉按压T区定妆\n6. 定妆喷雾加固\n推荐：雅诗兰黛DW粉底+NARS遮瑕+Urban Decay定妆喷雾",
        author="美妆教程",
        likes=31200, comments=1234, shares=2340,
        tags=["美妆", "夏日", "底妆", "油皮"],
        keywords=["夏日", "美妆", "底妆", "油皮", "持妆", "女生"],
    ),
    _TopicItem(
        title="新手眼妆教程｜3步画出温柔大地色",
        summary="新手眼妆教程，大地色眼影+棕色眼线+睫毛膏，3步搞定温柔眼妆",
        content="新手眼妆3步法：\n1. 浅棕色打底整个眼窝\n2. 深棕色加深眼尾三角区\n3. 金色提亮眼皮中央\n眼线：棕色眼线笔沿睫毛根部画，眼尾微微上扬\n睫毛：夹翘后刷睫毛膏，Z字手法\n推荐：橘朵大地色盘+熊野职人睫毛膏",
        author="化妆小白",
        likes=25600, comments=890, shares=1567,
        tags=["美妆", "眼妆", "新手", "教程"],
        keywords=["美妆", "眼妆", "新手", "教程", "女生", "化妆"],
    ),
    _TopicItem(
        title="口红试色｜黄皮显白的8支平价口红",
        summary="黄皮女生口红试色，8支平价显白色号推荐，适合学生党",
        content="黄皮显白口红推荐：\n1. 橘调豆沙色（日常通勤）\n2. 枫叶红（秋冬必备）\n3. 砖红色（显白神器）\n4. 番茄红（活力减龄）\n5. 脏橘色（温柔甜美）\n6. 复古红（气场全开）\n7. 干玫瑰（气质优雅）\n8. 蜜桃色（清新自然）\n平价品牌：橘朵/完美日记/卡姿兰/稚优泉",
        author="口红试色",
        likes=28900, comments=1023, shares=1890,
        tags=["美妆", "口红", "试色", "黄皮"],
        keywords=["美妆", "口红", "试色", "黄皮", "女生", "平价"],
    ),
    _TopicItem(
        title="护肤步骤｜干皮秋冬保湿不卡粉",
        summary="干皮秋冬护肤步骤，水+精华+面霜+油，保湿不卡粉",
        content="干皮护肤顺序：\n1. 氨基酸洁面（温和不紧绷）\n2. 保湿化妆水拍3遍\n3. 玻尿酸精华锁水\n4. 神经酰胺面霜修复屏障\n5. 角鲨烷油封层（关键）\n6. 每周2次保湿面膜\n上妆前多涂一遍精华，避免卡粉\n推荐：珂润面霜+The Ordinary玻尿酸+HABA角鲨烷油",
        author="护肤日记",
        likes=16700, comments=456, shares=789,
        tags=["美妆", "护肤", "干皮", "秋冬"],
        keywords=["美妆", "护肤", "干皮", "秋冬", "女生", "保湿"],
    ),

    # ===== 美食类 =====
    _TopicItem(
        title="减脂早餐｜7天不重样，好吃不胖",
        summary="减脂期早餐分享，7天不重样食谱，高蛋白低卡，好吃不胖",
        content="减脂早餐7天食谱：\nDay1：全麦面包+牛油果+水煮蛋\nDay2：燕麦粥+蓝莓+坚果\nDay3：希腊酸奶+格兰诺拉麦片\nDay4：蒸南瓜+鸡蛋+牛奶\nDay5：全麦三明治+生菜+鸡胸肉\nDay6：紫薯+豆浆+苹果\nDay7：杂粮粥+水煮蛋+蔬菜\n每餐控制在300-400卡",
        author="减脂美食",
        likes=22400, comments=678, shares=1234,
        tags=["美食", "减脂", "早餐", "食谱"],
        keywords=["美食", "减脂", "早餐", "食谱", "女生"],
    ),
    _TopicItem(
        title="家常菜教程｜3道快手菜，30分钟搞定",
        summary="家常菜教程，番茄炒蛋+可乐鸡翅+蒜蓉西兰花，30分钟3菜一汤",
        content="30分钟3菜一汤：\n1. 番茄炒蛋（10分钟）：鸡蛋打散炒散盛出，番茄炒出汁加蛋翻炒\n2. 可乐鸡翅（20分钟）：鸡翅划刀焯水，煎至金黄，加可乐酱油收汁\n3. 蒜蓉西兰花（8分钟）：西兰花焯水，蒜末爆香加盐翻炒\n汤：紫菜蛋花汤（5分钟）\n小技巧：同时操作多个灶台，省时一半",
        author="家常菜日记",
        likes=18900, comments=534, shares=890,
        tags=["美食", "家常菜", "教程", "快手"],
        keywords=["美食", "家常菜", "教程", "快手", "食谱"],
    ),
    _TopicItem(
        title="自制奶茶｜3款减脂版，好喝不长胖",
        summary="自制减脂奶茶教程，红茶拿铁+抹茶豆奶+乌龙鲜奶，好喝不长胖",
        content="减脂奶茶3款：\n1. 红茶拿铁：红茶包+脱脂牛奶+赤藓糖醇（80卡）\n2. 抹茶豆奶：抹茶粉+无糖豆奶+代糖（60卡）\n3. 乌龙鲜奶：乌龙茶+低脂牛奶+蜂蜜（100卡）\n小技巧：\n- 用代糖代替白糖\n- 选脱脂/低脂奶\n- 茶底要浓，奶要少\n比外面奶茶少300+卡路里",
        author="减脂美食",
        likes=15600, comments=423, shares=678,
        tags=["美食", "奶茶", "减脂", "自制"],
        keywords=["美食", "奶茶", "减脂", "自制", "女生"],
    ),

    # ===== 旅行类 =====
    _TopicItem(
        title="周末游｜杭州2日游攻略，人均500",
        summary="杭州周末2日游攻略，西湖+灵隐寺+龙井村，人均500含住宿",
        content="杭州2日游行程：\nDay1：\n上午：西湖断桥→白堤→苏堤\n中午：楼外楼吃西湖醋鱼\n下午：雷峰塔→太子湾公园\n晚上：河坊街逛吃\nDay2：\n上午：灵隐寺→飞来峰\n中午：龙井村吃农家菜\n下午：九溪十八涧\n住宿：青旅80/晚或民宿200/晚\n交通：地铁+公交+步行\n总花费：住宿200+吃饭150+门票100+交通50=500",
        author="旅行攻略",
        likes=26700, comments=890, shares=1567,
        tags=["旅行", "杭州", "周末游", "攻略"],
        keywords=["旅行", "杭州", "周末游", "攻略", "女生"],
    ),
    _TopicItem(
        title="拍照姿势｜旅行拍照不再尴尬，9个pose学起来",
        summary="旅行拍照姿势教程，9个自然不做作的pose，拍出大片感",
        content="旅行拍照9个pose：\n1. 背影杀：背对镜头看风景\n2. 侧身回眸：侧身站立回头笑\n3. 走路抓拍：自然走动连拍\n4. 托腮看远方：手托腮帮看风景\n5. 坐台阶：坐在台阶上腿伸长\n6. 撑伞：撑伞遮阳超有氛围\n7. 举饮料：举着奶茶或咖啡\n8. 依靠：靠墙靠栏杆\n9. 蹲下拍：蹲下看镜头显脸小\n小技巧：连拍模式抓表情，自然笑最好看",
        author="拍照教程",
        likes=19800, comments=567, shares=1234,
        tags=["旅行", "拍照", "姿势", "教程"],
        keywords=["旅行", "拍照", "姿势", "教程", "女生"],
    ),

    # ===== 健身类 =====
    _TopicItem(
        title="居家减脂｜15分钟hiit，不用器械",
        summary="居家hiit减脂训练，15分钟7个动作，不用器械燃烧脂肪",
        content="15分钟hiit训练（每个动作45秒+休息15秒，循环2次）：\n1. 开合跳热身\n2. 高抬腿\n3. 深蹲跳\n4. 登山跑\n5. 波比跳\n6. 俄罗斯转体\n7. 平板支撑\n注意事项：\n- 训练前热身5分钟\n- 训练后拉伸10分钟\n- 每周3-4次，配合饮食\n- 心率保持140-160最佳燃脂",
        author="健身教练",
        likes=23400, comments=678, shares=1890,
        tags=["健身", "减脂", "hiit", "居家"],
        keywords=["健身", "减脂", "hiit", "居家", "女生", "运动"],
    ),
    _TopicItem(
        title="瘦腿教程｜21天腿围瘦3cm",
        summary="瘦腿训练教程，21天腿围瘦3cm，拉伸+力量训练结合",
        content="瘦腿21天计划：\n每日训练（20分钟）：\n1. 蚌式开合 3组x20次（改善假胯宽）\n2. 侧抬腿 3组x20次（瘦大腿外侧）\n3. 后踢腿 3组x20次（提臀瘦腿后侧）\n4. 腿部拉伸 10分钟（关键）\n每周3次有氧（跑步/跳绳30分钟）\n注意事项：\n- 避免深蹲等粗腿动作\n- 每天拉伸不能少\n- 饮食控制热量\n- 睡前抬腿15分钟消水肿",
        author="瘦腿日记",
        likes=20100, comments=789, shares=1345,
        tags=["健身", "瘦腿", "教程", "拉伸"],
        keywords=["健身", "瘦腿", "教程", "女生", "运动", "拉伸"],
    ),

    # ===== 学习类 =====
    _TopicItem(
        title="时间管理｜3个方法让你效率翻倍",
        summary="时间管理方法分享，番茄工作法+四象限+批处理，效率翻倍",
        content="3个时间管理方法：\n1. 番茄工作法：25分钟专注+5分钟休息，4个番茄后休息20分钟\n2. 四象限法则：\n   重要紧急→立即做\n   重要不紧急→计划做\n   紧急不重要→委托做\n   不重要不紧急→不做\n3. 批处理：\n   同类任务集中做（回消息/写文档/开会）\n   减少任务切换损耗\n工具推荐：Forest专注森林+滴答清单+Notion",
        author="学习方法",
        likes=17800, comments=456, shares=890,
        tags=["学习", "时间管理", "效率", "方法"],
        keywords=["学习", "时间管理", "效率", "方法", "女生"],
    ),
    _TopicItem(
        title="读书笔记｜5本提升气质的女生必读",
        summary="女生提升气质书单推荐，5本必读书籍+读书笔记分享",
        content="女生提升气质5本书：\n1. 《简爱》— 独立与尊严\n2. 《傲慢与偏见》— 理性与爱情\n3. 《人间失格》— 认识人性\n4. 《百年孤独》— 理解孤独\n5. 《活着》— 珍惜生命\n读书方法：\n- 每天睡前读30分钟\n- 做摘抄笔记\n- 写读后感\n- 与朋友讨论\n坚持半年，气质明显提升，谈吐更有深度",
        author="读书笔记",
        likes=15600, comments=423, shares=678,
        tags=["学习", "读书", "书单", "气质"],
        keywords=["学习", "读书", "书单", "女生", "气质"],
    ),

    # ===== 职场类 =====
    _TopicItem(
        title="职场穿搭｜30岁女性的5套通勤look",
        summary="30岁职场女性穿搭，5套干练又不失女人味的通勤搭配",
        content="30岁职场穿搭5套：\n1. 白衬衫+黑西裤+尖头鞋（经典干练）\n2. 藏青西装裙+裸色高跟鞋（知性优雅）\n3. 米色针织衫+卡其阔腿裤+乐福鞋（温柔大气）\n4. 黑色西装外套+白t+牛仔裤+短靴（时尚休闲）\n5. 灰色西装套装+白衬衫+牛津鞋（气场全开）\n穿衣原则：\n- 质感>款式>颜色\n- 基础色为主（黑白灰驼）\n- 配饰提升精致度\n- 鞋包要质感好",
        author="职场穿搭",
        likes=18900, comments=567, shares=890,
        tags=["职场", "穿搭", "通勤", "30岁"],
        keywords=["职场", "穿搭", "通勤", "女生", "30岁"],
    ),
    _TopicItem(
        title="副业分享｜上班族每月多赚5000的方法",
        summary="上班族副业分享，3个适合打工人的副业，每月多赚5000",
        content="适合上班族的3个副业：\n1. 自媒体（小红书/公众号）\n   - 写擅长领域的内容\n   - 3个月起号变现\n   - 月入2000-10000\n2. 技能变现\n   - 设计/写作/翻译/编程\n   - 接单平台：猪八戒/Upwork\n   - 月入3000-8000\n3. 知识付费\n   - 做课程/咨询\n   - 平台：知识星球/小鹅通\n   - 月入1000-5000\n注意：先专注一个，别贪多",
        author="副业日记",
        likes=24500, comments=890, shares=1567,
        tags=["职场", "副业", "赚钱", "上班族"],
        keywords=["职场", "副业", "赚钱", "上班族", "女生"],
    ),

    # ===== AI/科技/教育类 =====
    _TopicItem(
        title="AI工具推荐｜5个提升效率的AI神器，打工人必看",
        summary="5个超好用的AI工具推荐，ChatGPT/Midjourney/Notion AI等，工作效率翻倍",
        content="5个AI效率工具：\n1. ChatGPT — 写文案/改邮件/做方案，万能助手\n2. Midjourney — AI绘图，做封面/配图超方便\n3. Notion AI — 笔记+AI写作，知识管理利器\n4. Gamma — AI做PPT，3分钟生成专业演示\n5. Perplexity — AI搜索引擎，比百度好用10倍\n使用技巧：\n- 提示词越具体，效果越好\n- 先让AI出草稿，再人工精修\n- 多工具组合使用效果更佳\n- 注意数据隐私，敏感内容别上传",
        author="AI工具箱",
        likes=35600, comments=1234, shares=2890,
        tags=["AI", "工具", "效率", "科技"],
        keywords=["AI", "人工智能", "工具", "效率", "科技", "ChatGPT", "教程"],
    ),
    _TopicItem(
        title="AI教育｜用ChatGPT学英语，3个月从哑巴英语到流利对话",
        summary="用AI学英语的方法分享，ChatGPT当外教，3个月口语突飞猛进",
        content="AI学英语3个月计划：\n第1个月：基础对话\n- 每天和ChatGPT对话30分钟\n- 让它纠正语法和用词\n- 积累日常表达100句\n第2个月：场景练习\n- 模拟面试/点餐/旅行场景\n- 录音回放找发音问题\n- 背单词用AI造句记忆\n第3个月：深度交流\n- 讨论新闻/电影/书籍\n- 写英文日记让AI批改\n- 尝试用英语思考\n推荐提示词：'Act as my English teacher, correct my mistakes and explain why'",
        author="AI学习法",
        likes=28900, comments=987, shares=2134,
        tags=["AI", "教育", "英语", "学习"],
        keywords=["AI", "教育", "英语", "学习", "人工智能", "ChatGPT", "语言"],
    ),
    _TopicItem(
        title="AI绘画教程｜零基础用Midjourney画出小红书爆款封面",
        summary="AI绘画教程，Midjourney从入门到出图，5步画出小红书风格封面",
        content="Midjourney小红书封面5步法：\n1. 确定风格：ins风/日系/国潮/极简\n2. 写提示词：主体+风格+色调+构图\n3. 生成4张选最佳\n4. Upscale放大+Variation微调\n5. 加文字排版完成\n提示词模板：\n'aesthetic [subject], [style] style, soft lighting, pastel colors, minimalist composition, 8k --ar 3:4'\n注意事项：\n- 人物图用 --v 5.2 更自然\n- 风景图用 --v 6 更细腻\n- 多试几次选最满意的\n- 加上品牌水印防搬运",
        author="AI绘画师",
        likes=31200, comments=1100, shares=2567,
        tags=["AI", "绘画", "教程", "封面"],
        keywords=["AI", "绘画", "教程", "封面", "Midjourney", "设计", "图片"],
    ),
    _TopicItem(
        title="AI写作｜用AI写小红书文案，10分钟搞定一篇爆款",
        summary="AI写作技巧分享，用ChatGPT写小红书文案的完整流程，10分钟出稿",
        content="AI写小红书文案流程：\n1. 给AI设定角色：'你是小红书爆款文案写手'\n2. 提供关键信息：主题/风格/目标人群\n3. 让AI出3个标题选最佳\n4. 生成正文+标签\n5. 人工微调语气和细节\n提示词模板：\n'写一篇小红书笔记，主题是[xxx]，风格活泼可爱，目标受众是20-30岁女生，包含标题、正文、标签'\n注意：\n- AI写的需要人工润色，不能直接发\n- 加入个人经历和真实感受\n- 标题要有钩子（数字/疑问/对比）\n- 开头3行决定点击率",
        author="AI写作",
        likes=26700, comments=890, shares=1980,
        tags=["AI", "写作", "文案", "教程"],
        keywords=["AI", "写作", "文案", "教程", "ChatGPT", "小红书", "创作"],
    ),
    _TopicItem(
        title="人工智能入门｜非技术人员也能懂的AI科普",
        summary="AI科普入门，用大白话解释ChatGPT/AIGC/大模型，非技术人员也能懂",
        content="AI核心概念大白话：\n1. 大模型=超级学霸：读了全网内容，什么都能聊两句\n2. ChatGPT=对话机器人：你问它答，像聪明助手\n3. AIGC=AI创作：写文/画图/做视频都行\n4. 提示词=遥控器：你怎么说，AI就怎么做\n5. 微调=专业培训：让通用AI变成领域专家\n对普通人的影响：\n- 重复性工作会被替代\n- 创意+AI=超级个体\n- 学会用AI比学编程更重要\n- AI是工具不是对手，会用的人赢",
        author="AI科普",
        likes=22300, comments=756, shares=1678,
        tags=["AI", "科普", "入门", "科技"],
        keywords=["AI", "人工智能", "科普", "入门", "科技", "教育", "ChatGPT"],
    ),
    _TopicItem(
        title="在线教育｜5个免费学习平台，比报班还管用",
        summary="免费在线学习平台推荐，B站/Coursera/中国大学MOOC等，自学也能逆袭",
        content="5个免费学习平台：\n1. B站 — 最强免费大学，编程/设计/考研全有\n2. 中国大学MOOC — 名校课程免费上，有证书\n3. Coursera — 全球顶尖大学课，可旁听\n4. Khan Academy — 数学/科学从零开始\n5. LeetCode — 编程刷题，面试必备\n学习方法：\n- 每天固定1小时学习\n- 做笔记+实践项目\n- 加入学习社群互相监督\n- 学完做输出（写文/做视频）\n- 3个月专注一个方向，别贪多",
        author="学习达人",
        likes=19800, comments=678, shares=1345,
        tags=["教育", "学习", "在线", "免费"],
        keywords=["教育", "学习", "在线", "免费", "课程", "自学", "平台"],
    ),
    _TopicItem(
        title="ChatGPT高级用法｜10个提示词技巧，让AI输出质量翻倍",
        summary="ChatGPT提示词技巧，10个高级用法，让AI回答更精准更有深度",
        content="10个提示词技巧：\n1. 角色设定：'你是XX领域的专家'\n2. 格式指定：'用表格/列表/步骤输出'\n3. 示例引导：给1-2个期望输出的例子\n4. 分步执行：复杂任务拆成多轮对话\n5. 约束条件：'不超过200字/只用小学词汇'\n6. 思维链：'请一步步思考'\n7. 自我检查：'请检查你的回答是否有错误'\n8. 对比分析：'对比A和B的优缺点'\n9. 迭代优化：'请改进上一版，使其更XX'\n10. 组合使用：角色+格式+约束+示例\n记住：提示词越具体，AI输出越精准",
        author="AI提示词",
        likes=29800, comments=1023, shares=2345,
        tags=["AI", "ChatGPT", "提示词", "技巧"],
        keywords=["AI", "ChatGPT", "提示词", "技巧", "教程", "人工智能"],
    ),
    _TopicItem(
        title="科技趋势2025｜这5个方向值得关注",
        summary="2025科技趋势预测，AI Agent/具身智能/AI教育/空间计算/绿色科技",
        content="2025年5大科技趋势：\n1. AI Agent — 从聊天到做事，AI开始自主执行任务\n2. 具身智能 — AI+机器人，从虚拟走向物理世界\n3. AI教育 — 个性化学习，每个学生都有AI导师\n4. 空间计算 — Apple Vision Pro引领，虚实融合新交互\n5. 绿色科技 — 碳中和驱动，新能源+AI优化\n对普通人的机会：\n- 学AI工具使用，提升竞争力\n- 关注AI+垂直领域创业机会\n- 投资相关方向基金\n- 培养AI无法替代的能力（创造力/共情力）",
        author="科技前沿",
        likes=18400, comments=567, shares=1234,
        tags=["科技", "趋势", "AI", "2025"],
        keywords=["科技", "趋势", "AI", "人工智能", "教育", "2025", "未来"],
    ),
]


def _match_score(item: _TopicItem, keyword: str) -> int:
    """计算关键词与话题的匹配分数。

    匹配规则（精确子串匹配，不做单字符模糊匹配避免误匹配）：
    - 标题完全包含关键词：+100
    - 标签包含关键词：+50
    - keywords 列表包含关键词：+30
    - 摘要包含关键词：+20
    """
    score = 0
    kw_lower = keyword.lower().strip()

    # 标题包含关键词（子串匹配）
    if kw_lower in item.title.lower():
        score += 100

    # 标签匹配（双向子串匹配）
    for tag in item.tags:
        if kw_lower in tag.lower() or tag.lower() in kw_lower:
            score += 50

    # keywords 列表匹配（双向子串匹配）
    for kw in item.keywords:
        if kw_lower in kw.lower() or kw.lower() in kw_lower:
            score += 30

    # 摘要包含关键词（子串匹配）
    if kw_lower in item.summary.lower():
        score += 20

    return score


def _to_trending_content(item: _TopicItem) -> TrendingContent:
    """把 _TopicItem 转成 TrendingContent。"""
    # 内置话题库无真实发布时间，用当前时间（视为刚发布）
    # 保证监控抓取时能通过当日窗口过滤
    now = datetime.now(timezone.utc)
    published_at = now.isoformat()

    return TrendingContent(
        platform="builtin",
        content_id=f"builtin_{abs(hash(item.title)) % 100000}",
        title=item.title,
        summary=item.summary,
        content=item.content,
        author=item.author,
        url="",
        likes=item.likes,
        comments=item.comments,
        shares=item.shares,
        views=item.likes * 8,  # 估算浏览量
        cover_img=f"https://picsum.photos/seed/{abs(hash(item.title)) % 10000}/400/300",
        published_at=published_at,
        tags=item.tags,
        title_original=item.title,
        summary_original=item.summary,
        content_original=item.content,
        raw={"source": "builtin_db"},
    )


class BuiltinSource(ContentSource):
    """内置中文话题数据源（零网络依赖）。

    - search_trending：按关键词匹配内置话题库，返回相关内容
    - get_trending：返回所有话题（按互动量排序）
    - 适合小红书常见类目（穿搭/美妆/美食/旅行/健身/学习/职场）
    """

    @property
    def name(self) -> str:
        return "builtin"

    def __init__(self) -> None:
        self._topics: list[_TopicItem] = list(_TOPIC_DB)

    async def search_trending(
        self,
        keyword: str,
        limit: int = 20,
        time_range: str = "week",
    ) -> list[TrendingContent]:
        """按关键词匹配内置话题库。

        匹配逻辑：
        1. 计算每个话题的匹配分数
        2. 过滤 score > 0 的
        3. 按 score 降序排序（同分按互动量）
        4. 截断到 limit
        """
        if not keyword.strip():
            return await self.get_trending(limit=limit)

        scored: list[tuple[int, _TopicItem]] = []
        for item in self._topics:
            score = _match_score(item, keyword)
            if score > 0:
                scored.append((score, item))

        # 按 score 降序，同分按互动量降序
        scored.sort(key=lambda x: (x[0], x[1].likes + x[1].comments), reverse=True)

        results = [_to_trending_content(item) for _, item in scored[:limit]]

        logger.info(
            f"[builtin] search '{keyword}': "
            f"matched {len(scored)} topics, returning {len(results)}"
        )
        return results

    async def get_trending(
        self,
        category: str = "",
        limit: int = 20,
    ) -> list[TrendingContent]:
        """返回内置话题库热门内容（按互动量排序）。"""
        items = list(self._topics)

        # 按 category 过滤（category 匹配 tags）
        if category:
            items = [it for it in items if any(category in tag for tag in it.tags)]

        # 按互动量降序
        items.sort(key=lambda x: x.likes + x.comments + x.shares, reverse=True)

        results = [_to_trending_content(item) for item in items[:limit]]

        logger.info(
            f"[builtin] get_trending category='{category}': "
            f"returning {len(results)} topics"
        )
        return results

    async def close(self) -> None:
        # 无资源需释放
        logger.info("[builtin] closed")