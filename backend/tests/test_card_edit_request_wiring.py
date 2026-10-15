"""HTTP 层编辑契约回归：CardEditRequest -> CardEdit 必须透传 P0/P1/P2 的新字段。

历史坑：operations.CardEdit 早已支持 note/tag/kicker/unit/source，
但 API 的 CardEditRequest 与 _to_card_edit 最初没有这些字段，
FastAPI 会静默丢弃它们，导致前端的副行/标签/矩阵五层/金句锚点编辑全部 no-op。
这里守住「请求体 -> 内部编辑指令」这一段，确保前端发来的字段真的能落到 CardEdit。
"""

import pytest

from app.api.routers.creative_artifact import CardEditRequest, _to_card_edit


def test_timeline_request_forwards_date_text_note():
    req = CardEditRequest(
        expected_version=1, op="set_timeline_item", index=0,
        value="2024-Q1", note="里程碑", tag="副行说明",
    )
    edit = _to_card_edit(req)
    assert edit.value == "2024-Q1"      # date
    assert edit.note == "里程碑"           # text
    assert edit.tag == "副行说明"          # note


def test_bento_cell_request_forwards_five_layers():
    req = CardEditRequest(
        expected_version=1, op="set_bento_cell", index=1,
        value="62", kicker="市占率", unit="%", note="同比+8pt", source="官方报告",
    )
    edit = _to_card_edit(req)
    assert edit.value == "62" and edit.kicker == "市占率"
    assert edit.unit == "%" and edit.note == "同比+8pt" and edit.source == "官方报告"


def test_stat_value_request_forwards_five_layers():
    req = CardEditRequest(
        expected_version=1, op="set_stat_value",
        value="3.2x", kicker="留存倍率", unit="", note="30 日", source="内部数据",
    )
    edit = _to_card_edit(req)
    assert edit.value == "3.2x" and edit.kicker == "留存倍率"
    assert edit.note == "30 日" and edit.source == "内部数据"


def test_quote_request_forwards_text_author_kicker():
    req = CardEditRequest(
        expected_version=1, op="set_quote",
        value="知行合一", note="王阳明", tag="明",
    )
    edit = _to_card_edit(req)
    assert edit.value == "知行合一"       # text
    assert edit.note == "王阳明"           # author
    assert edit.tag == "明"                # kicker


def test_item_request_forwards_text_note_tag():
    req = CardEditRequest(
        expected_version=1, op="set_item", index=0,
        value="要点", note="副行", tag="标签",
    )
    edit = _to_card_edit(req)
    assert edit.value == "要点" and edit.note == "副行" and edit.tag == "标签"


def test_unknown_op_rejected():
    req = CardEditRequest(expected_version=1, op="not_a_real_op", value="x")
    with pytest.raises(Exception):
        _to_card_edit(req)
