from app.agents.prompt_assembler import PromptAssembler, PromptContext


def test_assemble_with_full_context():
    assembler = PromptAssembler()
    ctx = PromptContext(
        persona="你是小红书创作助手",
        mode="agent",
        user_memory={"writing_style": "活泼少女", "recent_topics": ["穿搭"]},
        session_context={"current_topic": "AI 教育"},
        skills=[{"name": "xhs_search", "description": "搜索小红书热门内容"}],
    )
    prompt = assembler.assemble(ctx)

    assert "小红书创作助手" in prompt
    assert "自主 Agent" in prompt
    assert "[用户记忆]" in prompt
    assert "[会话上下文]" in prompt
    assert "[可用工具]" in prompt
    assert "xhs_search" in prompt


def test_assemble_returns_minimal_prompt_for_empty_context():
    assembler = PromptAssembler()
    prompt = assembler.assemble(PromptContext())
    assert "乐于助人的助手" in prompt


def test_assemble_skips_empty_sections():
    assembler = PromptAssembler()
    prompt = assembler.assemble(PromptContext(persona="test", mode="chat"))
    assert "[用户记忆]" not in prompt
    assert "[会话上下文]" not in prompt
    assert "[可用工具]" not in prompt
