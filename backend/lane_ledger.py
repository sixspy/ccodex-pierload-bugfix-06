"""停用命运册：停用车道被拒过磅的当日锁死记录。

一次拒写即当日锁死：该车道当日正式票增量恒为 0、对账流量不累计。
停用禁磅后同一日即使车道被重新置开放，仍按命运册锁死，写入记「停用修复偏航」拒写。
"""
from __future__ import annotations

from db import now_iso, write_audit

VERDICT_DISABLED = "停用禁磅"
VERDICT_DEVIATION = "停用修复偏航"

ACTION_REJECTED = "ticket_weigh_rejected"
ACTION_DEVIATION = "ticket_weigh_deviation"


def _today() -> str:
    return now_iso()[:10]


def record_disabled_weigh_rejection(
    conn, *, lane: dict, lane_id: int, actor: str, ticket_code: str | None,
    reason: str = VERDICT_DISABLED,
) -> dict:
    """拒写：当日命运册锁死，正式零增、对账零累计。"""
    day = _today()
    lane_code = lane.get("lane_code") or f"LN-{lane_id}"
    action = ACTION_DEVIATION if reason == VERDICT_DEVIATION else ACTION_REJECTED
    payload = {
        "day": day,
        "lane_id": lane_id,
        "lane_code": lane_code,
        "lane_status": lane.get("status"),
        "actor": actor,
        "requested_ticket_code": ticket_code,
        "formal_ticket_delta": 0,
        "reconcile_traffic_delta": 0,
        "verdict": reason,
    }
    write_audit(conn, actor, action, lane_code, payload)
    conn.execute(
        """INSERT OR IGNORE INTO lane_disable_ledger(ledger_day,lane_id,lane_code,
           lane_status,actor,requested_ticket_code,formal_ticket_delta,
           reconcile_traffic_delta,verdict,created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (
            day,
            lane_id,
            lane_code,
            lane.get("status") or "",
            actor,
            ticket_code or "",
            0,
            0,
            reason,
            now_iso(),
        ),
    )
    conn.commit()
    return payload


def lane_locked_today(conn, lane_id: int) -> bool:
    row = conn.execute(
        """SELECT id FROM lane_disable_ledger WHERE ledger_day=? AND lane_id=?
           LIMIT 1""",
        (_today(), lane_id),
    ).fetchone()
    return row is not None


def ledger_for_day(conn, day: str | None = None) -> list[dict]:
    rows = conn.execute(
        """SELECT * FROM lane_disable_ledger WHERE ledger_day=?
           ORDER BY id DESC""",
        (day or _today(),),
    ).fetchall()
    return [dict(r) for r in rows]


def locked_lane_ids(conn, day: str | None = None) -> set[int]:
    rows = conn.execute(
        "SELECT lane_id FROM lane_disable_ledger WHERE ledger_day=?",
        (day or _today(),),
    ).fetchall()
    return {int(r["lane_id"]) for r in rows}


def locked_lane_since(conn, day: str | None = None) -> dict[int, str]:
    """当日锁死车道 -> 首次锁死时刻；锁死前的既成票不回溯抹除。"""
    rows = conn.execute(
        """SELECT lane_id, created_at FROM lane_disable_ledger
           WHERE ledger_day=? ORDER BY id""",
        (day or _today(),),
    ).fetchall()
    since: dict[int, str] = {}
    for r in rows:
        since.setdefault(int(r["lane_id"]), r["created_at"])
    return since
