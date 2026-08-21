from app.templates.registry import BUILTIN_TEMPLATES, TemplateRegistry


def test_builtin_templates_registered():
    registry = TemplateRegistry()
    templates = registry.list()

    assert len(templates) == 6
    ids = {template.id for template in templates}
    assert ids == {
        "minimal_white",
        "warm_card",
        "dark_tech",
        "esther_brand",
        "esther_dark",
        "esther_warm",
    }


def test_list_filters_by_platform_and_category():
    registry = TemplateRegistry()

    xiaohongshu_templates = registry.list(platform="xiaohongshu")
    assert len(xiaohongshu_templates) == len(BUILTIN_TEMPLATES)

    tech_templates = registry.list(category="科技")
    assert {template.id for template in tech_templates} == {"dark_tech", "esther_dark"}


def test_manifest_exposes_render_metadata():
    registry = TemplateRegistry()
    template = registry.get("esther_brand")

    assert template is not None
    assert template.name == "Esther 品牌"
    assert template.renderer == "frontend_builtin"
    assert template.platforms["xiaohongshu"].format == "3:4"
    assert template.platforms["xiaohongshu"].width == 1080
    assert template.platforms["xiaohongshu"].height == 1440
    assert template.theme["accent"] == "#2B7FD8"
    assert template.default_decoration["type"] == "gradient_orbs"
    assert template.fields[0].key == "title"
    assert "highlight" in template.page_type_fields["cover"]
    assert template.category_keywords


def test_registry_field_names_and_default_template():
    registry = TemplateRegistry()

    assert registry.default_template_id() == "minimal_white"
    assert registry.supports_page_type("minimal_white", "cover") is True
    assert registry.supports_page_type("minimal_white", "end_page") is False
    assert registry.supports_page_type("esther_brand", "end_page") is True


def test_platform_profiles():
    registry = TemplateRegistry()

    profiles = registry.list_platform_profiles()
    assert {profile.platform for profile in profiles} == {
        "xiaohongshu",
        "douyin",
        "wechat",
    }

    douyin = registry.get_platform_format("douyin", "9:16")
    assert douyin is not None
    assert douyin.width == 1080
    assert douyin.height == 1920
    assert douyin.safe_area["top"] == 120

    template = registry.get("esther_brand")
    assert template is not None
    assert "douyin" in template.platforms
    assert "wechat" in template.platforms


def test_resolve_platform_format():
    registry = TemplateRegistry()

    douyin = registry.resolve_platform_format("douyin", "9:16")
    assert douyin["platform"] == "douyin"
    assert douyin["height"] == 1920
    assert douyin["safe_area"]["bottom"] == 200

    fallback = registry.resolve_platform_format("unknown", None)
    assert fallback["platform"] == "xiaohongshu"
