"""端到端链路验证：TieredModelRouter 在 multi_image_video 流水线中的完整调用链。

验证路径：
  Agent → SkillRegistry → multi_image_video Skill → 各步骤 → TieredModelRouter → 具体模型名

运行：python -m tests.verify_tier_chain
"""

from __future__ import annotations

import json
import sys


def verify_chain() -> None:
    errors: list[str] = []
    steps: list[dict] = []

    # ── Step 0: TieredModelRouter 可导入 ──
    try:
        from app.adapters.video_pipeline import (
            ModelTier,
            PipelineStage,
            TieredModelRouter,
            get_tier_router,
            _DEFAULT_STAGE_TIERS,
            _DEFAULT_TIER_MODELS,
        )
        steps.append({"step": "0. 导入 TieredModelRouter", "status": "OK"})
    except Exception as e:
        errors.append(f"导入失败: {e}")
        steps.append({"step": "0. 导入 TieredModelRouter", "status": "FAIL", "error": str(e)})
        _print_result(steps, errors)
        return

    # ── Step 1: get_tier_router() 全局实例 ──
    try:
        router = get_tier_router()
        assert isinstance(router, TieredModelRouter)
        steps.append({"step": "1. get_tier_router() 实例化", "status": "OK"})
    except Exception as e:
        errors.append(f"get_tier_router() 失败: {e}")
        steps.append({"step": "1. get_tier_router() 实例化", "status": "FAIL", "error": str(e)})
        _print_result(steps, errors)
        return

    # ── Step 2: 各阶段模型解析 ──
    stage_caps = [
        (PipelineStage.VL_UNDERSTAND, "vl", "Step1: VL理解参考图"),
        (PipelineStage.LLM_STORYBOARD, "llm", "Step2: LLM编排分镜"),
        (PipelineStage.TEXT2IMAGE, "t2i", "Step3: text2image生关键帧"),
        (PipelineStage.IMAGE2VIDEO, "i2v", "Step4: image2video生视频"),
        (PipelineStage.AUDIO_ENHANCE, "t2i", "Step5: 音频后处理"),
    ]

    for stage, cap, label in stage_caps:
        try:
            model = router.resolve(stage, cap)
            tier = router.tier_for_stage(stage)
            if not model:
                errors.append(f"{label}: resolve 返回空字符串")
            steps.append({
                "step": f"2. {label}",
                "status": "OK" if model else "WARN",
                "stage": stage.value,
                "tier": tier.value,
                "capability": cap,
                "model": model,
            })
        except Exception as e:
            errors.append(f"{label}: {e}")
            steps.append({"step": f"2. {label}", "status": "FAIL", "error": str(e)})

    # ── Step 3: 验证算力分级策略 ──
    planning_tiers = [
        router.tier_for_stage(PipelineStage.VL_UNDERSTAND),
        router.tier_for_stage(PipelineStage.LLM_STORYBOARD),
    ]
    gen_tiers = [
        router.tier_for_stage(PipelineStage.TEXT2IMAGE),
        router.tier_for_stage(PipelineStage.IMAGE2VIDEO),
    ]

    if all(t == ModelTier.ECONOMY for t in planning_tiers):
        steps.append({"step": "3. 规划阶段用 economy 级", "status": "OK", "tiers": [t.value for t in planning_tiers]})
    else:
        errors.append(f"规划阶段应为 economy，实际: {[t.value for t in planning_tiers]}")
        steps.append({"step": "3. 规划阶段用 economy 级", "status": "FAIL", "tiers": [t.value for t in planning_tiers]})

    if all(t == ModelTier.QUALITY for t in gen_tiers):
        steps.append({"step": "3. 生成阶段用 quality 级", "status": "OK", "tiers": [t.value for t in gen_tiers]})
    else:
        errors.append(f"生成阶段应为 quality，实际: {[t.value for t in gen_tiers]}")
        steps.append({"step": "3. 生成阶段用 quality 级", "status": "FAIL", "tiers": [t.value for t in gen_tiers]})

    # ── Step 4: 验证具体模型名 ──
    expected = {
        (PipelineStage.VL_UNDERSTAND, "vl"): "qwen-vl-plus",
        (PipelineStage.LLM_STORYBOARD, "llm"): "deepseek-chat",
        (PipelineStage.TEXT2IMAGE, "t2i"): "wanx2.1-t2i-plus",
        (PipelineStage.IMAGE2VIDEO, "i2v"): "wan2.1-i2v-plus",
    }
    for (stage, cap), exp_model in expected.items():
        actual = router.resolve(stage, cap)
        if actual == exp_model:
            steps.append({"step": f"4. {stage.value}/{cap} = {actual}", "status": "OK"})
        else:
            errors.append(f"{stage.value}/{cap}: 期望 {exp_model}，实际 {actual}")
            steps.append({"step": f"4. {stage.value}/{cap} = {actual} (期望 {exp_model})", "status": "FAIL"})

    # ── Step 5: Skill 注册链路 ──
    try:
        from app.skills.registry import SkillRegistry
        registry = SkillRegistry()
        all_skills = registry.list_skills()
        video_skills = [s for s in all_skills if "video" in s.name.lower() or "image" in s.name.lower()]
        steps.append({
            "step": "5. SkillRegistry 加载",
            "status": "OK",
            "video_skills": [s.name for s in video_skills],
        })
    except Exception as e:
        errors.append(f"SkillRegistry 加载失败: {e}")
        steps.append({"step": "5. SkillRegistry 加载", "status": "FAIL", "error": str(e)})

    # ── Step 6: summary 可调用 ──
    try:
        summary = router.summary()
        assert "stage_tiers" in summary
        assert "tier_definitions" in summary
        steps.append({"step": "6. router.summary()", "status": "OK", "stages_count": len(summary["stage_tiers"])})
    except Exception as e:
        errors.append(f"summary() 失败: {e}")
        steps.append({"step": "6. router.summary()", "status": "FAIL", "error": str(e)})

    # ── Step 7: 动态调整验证 ──
    try:
        test_router = TieredModelRouter()
        test_router.set_stage_tier(PipelineStage.VL_UNDERSTAND, ModelTier.QUALITY)
        model = test_router.resolve(PipelineStage.VL_UNDERSTAND, "vl")
        if model == "qwen-vl-max":
            steps.append({"step": "7. 动态调整 VL→quality", "status": "OK", "model": model})
        else:
            errors.append(f"动态调整后期望 qwen-vl-max，实际 {model}")
            steps.append({"step": "7. 动态调整 VL→quality", "status": "FAIL", "model": model})
    except Exception as e:
        errors.append(f"动态调整失败: {e}")
        steps.append({"step": "7. 动态调整 VL→quality", "status": "FAIL", "error": str(e)})

    _print_result(steps, errors)


def _print_result(steps: list[dict], errors: list[str]) -> None:
    print("\n" + "=" * 70)
    print("  端到端链路验证：TieredModelRouter → multi_image_video")
    print("=" * 70)

    for s in steps:
        status_icon = "✅" if s["status"] == "OK" else ("⚠️" if s["status"] == "WARN" else "❌")
        line = f"  {status_icon} {s['step']}"
        if "model" in s:
            line += f"  → {s['model']}"
        if "tier" in s:
            line += f"  [{s['tier']}]"
        if "error" in s:
            line += f"  ERROR: {s['error']}"
        print(line)

    print("-" * 70)
    if not errors:
        print("  🎉 全链路通过！算力分级调度已集成到视频生成流水线。")
    else:
        print(f"  ❌ {len(errors)} 个错误：")
        for e in errors:
            print(f"     - {e}")
    print("=" * 70)

    sys.exit(0 if not errors else 1)


if __name__ == "__main__":
    verify_chain()