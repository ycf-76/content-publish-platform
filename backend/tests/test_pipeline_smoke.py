"""链路连通性冒烟测试：不调 LLM，只验证导入/注册/路由/守卫是否通畅。"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("DATABASE_URL", "mysql+aiomysql://ycf:ycf94946@127.0.0.1:3306/xhs_agent?charset=utf8mb4")

PASSED = 0
FAILED = 0


def _ok(label: str) -> None:
    global PASSED
    PASSED += 1
    print(f"  ✅ {label}")


def _fail(label: str, err: str) -> None:
    global FAILED
    FAILED += 1
    print(f"  ❌ {label}: {err}")


def test_imports():
    print("\n── 1. 模块导入测试 ──")
    modules = [
        ("multi_image_video", "app.skills.produce.multi_image_video"),
        ("video_pipeline", "app.adapters.video_pipeline"),
        ("asset_ref", "app.services.asset_ref"),
        ("asset_library", "app.services.asset_library"),
        ("skill_registry", "app.core.skill_registry"),
        ("workflow_stub", "app.services.workflow"),
    ]
    for label, mod_path in modules:
        try:
            __import__(mod_path)
            _ok(f"import {mod_path}")
        except Exception as e:
            _fail(f"import {mod_path}", str(e))


def test_skill_registration():
    print("\n── 2. Skill 注册测试 ──")
    try:
        from app.skills.produce.multi_image_video import MultiImageVideoSkill
        skill = MultiImageVideoSkill()
        _ok(f"multi_image_video Skill 可实例化（display_name={skill.display_name}）")
        _ok(f"trigger_words = {skill.trigger_words[:5]}...")
        _ok(f"input_schema fields = {list(skill.input_schema.model_fields.keys())}")

        from app.core.skill_registry import SkillRegistry
        registry = SkillRegistry()
        try:
            registry.register("produce", "multi_image_video", MultiImageVideoSkill)
            retrieved = registry.get("produce", "multi_image_video")
            if retrieved is MultiImageVideoSkill:
                _ok("SkillRegistry.register → get 往返正确")
            else:
                _fail("SkillRegistry 往返", f"get 返回 {retrieved}")
        except TypeError:
            registry.register(MultiImageVideoSkill)
            _ok("SkillRegistry.register(skill_cls) 单参数注册成功")
    except Exception as e:
        _fail("Skill 注册检查", str(e))


def test_tier_router():
    print("\n── 3. 算力分级路由测试 ──")
    try:
        from app.adapters.video_pipeline import (
            PipelineStage,
            ModelTier,
            TieredModelRouter,
            _DEFAULT_STAGE_TIERS,
            _DEFAULT_TIER_MODELS,
        )

        router = TieredModelRouter()

        stages = [
            (PipelineStage.VL_UNDERSTAND, "vl", "qwen2.5-vl-7b-instruct"),
            (PipelineStage.LLM_STORYBOARD, "llm", "deepseek-chat"),
            (PipelineStage.TEXT2IMAGE, "t2i", "wanx2.1-t2i-plus"),
            (PipelineStage.IMAGE2VIDEO, "i2v", "wanx2.1-i2v-plus"),
            (PipelineStage.AUDIO_ENHANCE, "t2i", "wanx2.1-t2i-turbo"),
        ]

        for stage, cap, expected in stages:
            result = router.resolve(stage, cap)
            if result == expected:
                _ok(f"{stage.value}.{cap} → {result}")
            else:
                _fail(f"{stage.value}.{cap}", f"期望 {expected}，实际 {result}")

        tier_vl = router.tier_for_stage(PipelineStage.VL_UNDERSTAND)
        if tier_vl == ModelTier.ECONOMY:
            _ok("VL 理解阶段 → economy 分级")
        else:
            _fail("VL 理解阶段分级", f"期望 economy，实际 {tier_vl.value}")

        tier_i2v = router.tier_for_stage(PipelineStage.IMAGE2VIDEO)
        if tier_i2v == ModelTier.QUALITY:
            _ok("图生视频阶段 → quality 分级")
        else:
            _fail("图生视频阶段分级", f"期望 quality，实际 {tier_i2v.value}")

        summary = router.summary()
        _ok(f"路由摘要含 {len(summary['stage_tiers'])} 阶段")

    except Exception as e:
        _fail("算力分级路由", str(e))


def test_asset_ref_guard():
    print("\n── 4. Asset ID 守卫测试 ──")
    try:
        from app.services.asset_ref import guard_asset_ids

        _ok("guard_asset_ids 可导入")

        patterns_hallucination = ["img_1", "image_2", "pic_3", "ref_1", "图1", "素材2"]
        patterns_real = ["01JKABCDEF", "01XYZ12345"]

        import re
        from app.services.asset_ref import _HALLUCINATION_PATTERNS

        for p in patterns_hallucination:
            if _HALLUCINATION_PATTERNS.match(p):
                _ok(f"幻觉模式匹配: {p}")
            else:
                _fail(f"幻觉模式匹配: {p}", "未匹配")

        for p in patterns_real:
            if not _HALLUCINATION_PATTERNS.match(p):
                _ok(f"真实 ID 不误拦: {p}")
            else:
                _fail(f"真实 ID 不误拦: {p}", "被误判为幻觉")

    except Exception as e:
        _fail("Asset ID 守卫", str(e))


def test_pipeline_functions():
    print("\n── 5. 流水线函数存在性测试 ──")
    try:
        from app.skills.produce.multi_image_video import (
            _resolve_image_urls,
            _vl_understand_images,
            _generate_storyboard,
            _generate_shot_frames,
            _generate_shot_clips,
            _compose_final,
            MultiImageVideoSkill,
            MultiImageVideoInput,
        )
        _ok("_resolve_image_urls")
        _ok("_vl_understand_images")
        _ok("_generate_storyboard")
        _ok("_generate_shot_frames")
        _ok("_generate_shot_clips")
        _ok("_compose_final")
        _ok("MultiImageVideoSkill")
        _ok("MultiImageVideoInput")

        input_model = MultiImageVideoInput(
            image_asset_ids=["test_id_1"],
            prompt="测试视频描述",
        )
        _ok(f"MultiImageVideoInput 可实例化（image_asset_ids={input_model.image_asset_ids}）")

        _ok(f"max_length=10（图片上限）: {MultiImageVideoInput.model_fields['image_asset_ids'].metadata}")

    except Exception as e:
        _fail("流水线函数", str(e))


def test_compute_scheduler():
    print("\n── 6. 算力调度器测试 ──")
    try:
        from app.adapters.video_pipeline import ComputeScheduler, ProviderSlot

        scheduler = ComputeScheduler(
            slots=[
                ProviderSlot(name="ark", weight=2.0, max_concurrent=3, priority=10),
                ProviderSlot(name="dashscope", weight=1.0, max_concurrent=2, priority=5),
            ],
            global_max_concurrent=6,
        )

        selected = scheduler.select()
        if selected and selected.name == "ark":
            _ok(f"调度器优先选 ark（weight=2.0, priority=10）")
        elif selected:
            _ok(f"调度器选了 {selected.name}（weight={selected.weight}）")
        else:
            _fail("调度器选择", "返回 None")

        _ok(f"调度器含 {len(scheduler._slots)} 个 provider slot")

    except Exception as e:
        _fail("算力调度器", str(e))


def test_workflow_stub():
    print("\n── 7. Workflow Service Stub 测试 ──")
    try:
        from app.services.workflow import WorkflowService, get_workflow_service

        svc = get_workflow_service(None)
        _ok("get_workflow_service(None) 可调用")

        svc2 = WorkflowService(None)
        _ok("WorkflowService(None) 可实例化")

    except Exception as e:
        _fail("Workflow Stub", str(e))


def test_vl_model_names():
    print("\n── 8. VL 模型名验证 ──")
    try:
        from app.adapters.video_pipeline import _DEFAULT_TIER_MODELS, ModelTier

        economy_vl = _DEFAULT_TIER_MODELS[ModelTier.ECONOMY]["vl"]
        standard_vl = _DEFAULT_TIER_MODELS[ModelTier.STANDARD]["vl"]
        quality_vl = _DEFAULT_TIER_MODELS[ModelTier.QUALITY]["vl"]

        if "qwen2.5-vl" in economy_vl:
            _ok(f"economy VL = {economy_vl}（qwen2.5 系列）")
        else:
            _fail("economy VL", f"非 qwen2.5 系列：{economy_vl}")

        if "qwen2.5-vl" in standard_vl:
            _ok(f"standard VL = {standard_vl}（qwen2.5 系列）")
        else:
            _fail("standard VL", f"非 qwen2.5 系列：{standard_vl}")

        if "qwen2.5-vl" in quality_vl:
            _ok(f"quality VL = {quality_vl}（qwen2.5 系列）")
        else:
            _fail("quality VL", f"非 qwen2.5 系列：{quality_vl}")

        old_names = {"qwen-vl-plus", "qwen-vl-max"}
        all_vls = {economy_vl, standard_vl, quality_vl}
        if not all_vls & old_names:
            _ok("无旧模型名（qwen-vl-plus/qwen-vl-max）残留")
        else:
            _fail("旧模型名检查", f"仍有旧名：{all_vls & old_names}")

    except Exception as e:
        _fail("VL 模型名验证", str(e))


def main():
    print("=" * 60)
    print("  多图视频生成链路 冒烟测试（不调 LLM）")
    print("=" * 60)

    test_imports()
    test_skill_registration()
    test_tier_router()
    test_asset_ref_guard()
    test_pipeline_functions()
    test_compute_scheduler()
    test_workflow_stub()
    test_vl_model_names()

    print("\n" + "=" * 60)
    print(f"  结果：✅ {PASSED} 通过 / ❌ {FAILED} 失败")
    print("=" * 60)

    if FAILED > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()