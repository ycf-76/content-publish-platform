"""Tests for Quality Gate — BLCaptain style validation (R1-R9).

Covers:
1. R2 Type Caps: text field character limits (title, subtitle, content, etc.)
2. R4 Band Density: array field length limits (listItems, steps, etc.)
3. R3 Footer Collision: footer text overlapping with body
4. Content hole: missing content on content page
5. R7/R8/R9: full-bleed image page checks
6. QualityReport aggregation: passed/blocking/warn/info counts
7. check_draft: cross-page diversity, page count, adjacent page dedup
8. Edge cases: empty page, None values, boundary values
"""

import pytest

from app.services.quality_gate import (
    FIELD_CAPS,
    ARRAY_CAPS,
    MIN_QUIET_ZONE_RATIO,
    MAX_TITLE_CANVAS_RATIO,
    MAX_OVERLAY_PEAK_ALPHA,
    QualityIssue,
    QualityReport,
    PageQuality,
    check_page,
    check_draft,
)


class TestFieldCaps:
    def test_title_caps_exist(self):
        assert "title" in FIELD_CAPS
        assert FIELD_CAPS["title"]["block_max"] == 52

    def test_content_caps_exist(self):
        assert "content" in FIELD_CAPS
        assert FIELD_CAPS["content"]["block_max"] == 300

    def test_all_fields_have_block_max(self):
        for field, caps in FIELD_CAPS.items():
            assert "block_max" in caps, f"{field} missing block_max"


class TestArrayCaps:
    def test_list_items_caps_exist(self):
        assert "listItems" in ARRAY_CAPS
        assert ARRAY_CAPS["listItems"]["min"] == 2
        assert ARRAY_CAPS["listItems"]["block_max"] == 12

    def test_steps_caps_exist(self):
        assert "steps" in ARRAY_CAPS


class TestCheckPageR2TypeCaps:
    def test_title_within_limits(self):
        page = {"type": "content", "title": "短标题", "content": "正文内容"}
        result = check_page(0, page)
        blocking = [i for i in result.issues if i.rule == "R2" and i.severity == "blocking"]
        assert len(blocking) == 0

    def test_title_exceeds_block_max(self):
        page = {"type": "content", "title": "字" * 60, "content": "正文"}
        result = check_page(0, page)
        blocking = [i for i in result.issues if i.rule == "R2" and i.field == "title" and i.severity == "blocking"]
        assert len(blocking) == 1

    def test_title_in_warn_zone(self):
        page = {"type": "content", "title": "字" * 45, "content": "正文"}
        result = check_page(0, page)
        warns = [i for i in result.issues if i.rule == "R2" and i.field == "title" and i.severity == "warn"]
        assert len(warns) == 1

    def test_content_exceeds_block_max(self):
        page = {"type": "content", "content": "字" * 350}
        result = check_page(0, page)
        blocking = [i for i in result.issues if i.rule == "R2" and i.field == "content" and i.severity == "blocking"]
        assert len(blocking) == 1

    def test_subtitle_exceeds_block_max(self):
        page = {"type": "content", "subtitle": "字" * 45, "content": "正文"}
        result = check_page(0, page)
        blocking = [i for i in result.issues if i.rule == "R2" and i.field == "subtitle" and i.severity == "blocking"]
        assert len(blocking) == 1

    def test_empty_field_not_flagged(self):
        page = {"type": "content", "content": "正文"}
        result = check_page(0, page)
        title_issues = [i for i in result.issues if i.field == "title"]
        assert len(title_issues) == 0


class TestCheckPageR4BandDensity:
    def test_list_items_within_limits(self):
        page = {"type": "content", "content": "正文", "listItems": ["a", "b", "c"]}
        result = check_page(0, page)
        blocking = [i for i in result.issues if i.rule == "R4" and i.severity == "blocking"]
        assert len(blocking) == 0

    def test_list_items_too_few(self):
        page = {"type": "content", "content": "正文", "listItems": ["a"]}
        result = check_page(0, page)
        warns = [i for i in result.issues if i.rule == "R4" and i.field == "listItems"]
        assert len(warns) >= 1

    def test_list_items_exceeds_block_max(self):
        page = {"type": "content", "content": "正文", "listItems": [f"item{i}" for i in range(15)]}
        result = check_page(0, page)
        blocking = [i for i in result.issues if i.rule == "R4" and i.field == "listItems" and i.severity == "blocking"]
        assert len(blocking) == 1

    def test_steps_too_few(self):
        page = {"type": "content", "content": "正文", "steps": ["step1"]}
        result = check_page(0, page)
        warns = [i for i in result.issues if i.rule == "R4" and i.field == "steps"]
        assert len(warns) >= 1


class TestCheckPageR3FooterCollision:
    def test_footer_same_as_body_content(self):
        page = {"type": "content", "content": "这是正文内容", "footer": "这是正文内容"}
        result = check_page(0, page)
        footer_issues = [i for i in result.issues if i.rule == "R3"]
        assert len(footer_issues) >= 1

    def test_footer_different_from_body(self):
        page = {"type": "content", "content": "这是正文内容", "footer": "@作者署名"}
        result = check_page(0, page)
        footer_issues = [i for i in result.issues if i.rule == "R3"]
        assert len(footer_issues) == 0


class TestCheckPageContentHole:
    def test_content_page_missing_content(self):
        page = {"type": "content"}
        result = check_page(0, page)
        blocking = [i for i in result.issues if i.severity == "blocking" and i.field == "content"]
        assert len(blocking) >= 1

    def test_content_page_has_content(self):
        page = {"type": "content", "content": "有实质文案"}
        result = check_page(0, page)
        blocking = [i for i in result.issues if i.severity == "blocking" and i.field == "content" and "缺少" in i.message]
        assert len(blocking) == 0


class TestCheckPageFullBleed:
    def test_fullbleed_missing_image_source(self):
        page = {"type": "image_page", "imageRole": "full-bleed"}
        result = check_page(0, page)
        r7_issues = [i for i in result.issues if i.rule == "R7"]
        assert len(r7_issues) >= 1

    def test_fullbleed_with_image_source(self):
        page = {"type": "image_page", "imageRole": "full-bleed", "source": "wanx-v1"}
        result = check_page(0, page)
        r7_issues = [i for i in result.issues if i.rule == "R7"]
        assert len(r7_issues) == 0

    def test_fullbleed_missing_object_position(self):
        page = {"type": "image_page", "imageRole": "full-bleed", "source": "wanx-v1"}
        result = check_page(0, page)
        r8_issues = [i for i in result.issues if i.rule == "R8"]
        assert len(r8_issues) >= 1

    def test_fullbleed_with_all_position_fields(self):
        page = {
            "type": "image_page",
            "imageRole": "full-bleed",
            "source": "wanx-v1",
            "objectPosition": "center center",
            "subjectMap": {"subject": "person"},
            "safeTextZones": [{"x": 0, "y": 0, "w": 100, "h": 30}],
            "avoidZones": [{"x": 0, "y": 70, "w": 100, "h": 30}],
        }
        result = check_page(0, page)
        r8_issues = [i for i in result.issues if i.rule == "R8"]
        assert len(r8_issues) == 0

    def test_fullbleed_quiet_zone_ratio_too_small(self):
        page = {
            "type": "image_page",
            "imageRole": "full-bleed",
            "source": "wanx-v1",
            "objectPosition": "center",
            "safeTextZones": [],
            "quietZoneRatio": 0.1,
        }
        result = check_page(0, page)
        r9_issues = [i for i in result.issues if i.rule == "R9" and i.field == "quietZoneRatio"]
        assert len(r9_issues) >= 1

    def test_fullbleed_title_canvas_ratio_too_large(self):
        page = {
            "type": "image_page",
            "imageRole": "full-bleed",
            "source": "wanx-v1",
            "objectPosition": "center",
            "safeTextZones": [],
            "titleCanvasRatio": 0.6,
        }
        result = check_page(0, page)
        r9_issues = [i for i in result.issues if i.rule == "R9" and i.field == "titleCanvasRatio"]
        assert len(r9_issues) >= 1

    def test_fullbleed_overlay_peak_alpha_too_high(self):
        page = {
            "type": "image_page",
            "imageRole": "full-bleed",
            "source": "wanx-v1",
            "objectPosition": "center",
            "safeTextZones": [],
            "overlayPeakAlpha": 0.5,
        }
        result = check_page(0, page)
        r9_issues = [i for i in result.issues if i.rule == "R9" and i.field == "overlayPeakAlpha"]
        assert len(r9_issues) >= 1


class TestQualityReport:
    def test_empty_report_passes(self):
        report = QualityReport(passed=True)
        assert report.passed is True
        assert report.blocking == 0

    def test_all_issues_aggregates_page_and_draft(self):
        report = QualityReport(
            passed=False,
            blocking=2,
            warn=1,
            page_reports=[
                PageQuality(page_index=0, page_type="content", issues=[
                    QualityIssue(rule="R2", severity="blocking", message="test1"),
                ]),
            ],
            draft_issues=[
                QualityIssue(rule="R4", severity="blocking", message="test2"),
            ],
        )
        all_issues = report.all_issues()
        assert len(all_issues) == 2


class TestCheckDraft:
    def test_empty_draft_passes(self):
        report = check_draft({"pages": []})
        assert report.passed is True

    def test_draft_with_blocking_issue_fails(self):
        report = check_draft({"pages": [{"type": "content"}]})
        assert report.passed is False
        assert report.blocking >= 1

    def test_draft_with_valid_pages(self):
        draft = {"pages": [{"type": "content", "content": "正常文案", "title": "正常标题"}]}
        report = check_draft(draft)
        assert report.blocking == 0

    def test_draft_invalid_structure(self):
        report = check_draft({})
        assert report.passed is False

    def test_draft_pages_not_list(self):
        report = check_draft({"pages": "not a list"})
        assert report.passed is False

    def test_first_page_should_be_cover(self):
        draft = {"pages": [
            {"type": "content", "content": "正文"},
        ]}
        report = check_draft(draft)
        diversity_warns = [i for i in report.draft_issues if i.rule == "DIVERSITY" and "封面" in i.message]
        assert len(diversity_warns) >= 1

    def test_last_page_should_be_end_page(self):
        draft = {"pages": [
            {"type": "cover", "content": "封面"},
            {"type": "content", "content": "正文"},
        ]}
        report = check_draft(draft)
        diversity_warns = [i for i in report.draft_issues if i.rule == "DIVERSITY" and "尾页" in i.message]
        assert len(diversity_warns) >= 1

    def test_adjacent_same_type_is_blocking(self):
        draft = {"pages": [
            {"type": "content", "content": "第一页"},
            {"type": "content", "content": "第二页"},
        ]}
        report = check_draft(draft)
        blocking = [i for i in report.draft_issues if i.rule == "DIVERSITY" and i.severity == "blocking"]
        assert len(blocking) >= 1

    def test_diverse_pages_pass(self):
        draft = {"pages": [
            {"type": "cover", "content": "封面"},
            {"type": "content", "content": "正文"},
            {"type": "end_page", "content": "收尾"},
        ]}
        report = check_draft(draft)
        diversity_blocking = [i for i in report.draft_issues if i.rule == "DIVERSITY" and i.severity == "blocking"]
        assert len(diversity_blocking) == 0

    def test_expected_count_mismatch(self):
        draft = {"pages": [
            {"type": "cover", "content": "封面"},
            {"type": "content", "content": "正文"},
        ]}
        report = check_draft(draft, expected_count=5)
        count_issues = [i for i in report.draft_issues if i.rule == "COUNT"]
        assert len(count_issues) >= 1

    def test_expected_count_match(self):
        draft = {"pages": [
            {"type": "cover", "content": "封面"},
            {"type": "content", "content": "正文"},
        ]}
        report = check_draft(draft, expected_count=2)
        count_issues = [i for i in report.draft_issues if i.rule == "COUNT"]
        assert len(count_issues) == 0

    def test_realistic_xiaohongshu_card(self):
        draft = {"pages": [
            {
                "type": "cover",
                "title": "5个护肤小技巧让你皮肤变好",
                "subtitle": "新手必看",
                "content": "想要皮肤变好，其实不需要昂贵的护肤品，掌握这几个小技巧就够了。",
                "footer": "@小红薯分享",
            },
            {
                "type": "content",
                "title": "技巧一：早睡早起",
                "content": "充足的睡眠是皮肤修复的黄金时间，每天保证7-8小时睡眠，皮肤状态会明显改善。",
                "listItems": ["晚上11点前入睡", "睡前远离手机", "保持规律作息"],
            },
            {
                "type": "end_page",
                "title": "坚持就是胜利",
                "content": "护肤不是一朝一夕的事，坚持这些小习惯，你会发现皮肤越来越好。",
                "footer": "@小红薯分享",
            },
        ]}
        report = check_draft(draft)
        assert report.blocking == 0
        assert report.passed is True