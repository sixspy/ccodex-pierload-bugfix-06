"""车道可用状态：五页（车道/过磅/地磅/对账/总览）唯一口径。

停用禁磅：车道状态不在开放集合内即禁止过磅，正式票零增、对账零累计。
"""
from __future__ import annotations

LANE_OPEN_STATUSES = frozenset({"开放", "启用", "正常"})


def lane_is_open(status: str | None) -> bool:
    return (status or "").strip() in LANE_OPEN_STATUSES


def lane_block_reason(status: str | None) -> str:
    if lane_is_open(status):
        return ""
    label = (status or "").strip() or "未设置"
    return f"车道状态「{label}」非开放，禁止过磅"


def annotate_lane(row) -> dict:
    data = dict(row)
    data["weighable"] = lane_is_open(data.get("status"))
    data["blocked_reason"] = lane_block_reason(data.get("status"))
    return data
