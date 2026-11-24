"""停用修复第21号：停用车道禁磅三红夹具。

口径（甲路径）：停用标志已置 → 过磅正式票零增、拒写；对账当日流量不累计；
两路同车道抢建只认车道锁，败方仅留争用痕。本文件先见红，才允许改业务。
"""
from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

import tickets_svc
from app import app
from db import connect, init_db

BL_REF = "BL-2026-0101"
AXLES = [{"axle": 1, "w": 10.0}, {"axle": 2, "w": 12.0}]


@pytest.fixture(autouse=True)
def _db(tmp_path, monkeypatch):
    monkeypatch.setattr("db.DB_PATH", tmp_path / "t.db")
    init_db()
    yield


def _auth(c: TestClient, user="admin", password="admin123") -> dict:
    tok = c.post(
        "/api/login", json={"username": user, "password": password}
    ).json()["token"]
    return {"Authorization": "Bearer " + tok}


def _make_lane(c: TestClient, h: dict, code: str) -> dict:
    r = c.post(
        "/api/lanes",
        headers=h,
        json={
            "lane_code": code,
            "bridge_id": 1,
            "direction": "进闸",
            "overload_threshold_t": 40,
            "side_lane_ref": "停用旁路",
            "status": "停用",
        },
    )
    assert r.status_code == 200, r.text
    created = r.json()
    created["bridge_id"] = 1
    return created


def _payload(lane_id: int, ticket_code: str) -> dict:
    return {
        "lane_id": lane_id,
        "bl_ref": BL_REF,
        "vehicle_plate": "测停·21",
        "axle_weights": AXLES,
        "ticket_code": ticket_code,
    }


def test_21a_disabled_lane_weigh_keeps_formal_ledger_untouched():
    """失败测甲：停用车道过磅仍写入正式票。"""
    c = TestClient(app)
    h = _auth(c)
    lane = _make_lane(c, h, "LN-OFF-21-A")
    with connect() as conn:
        before = conn.execute("SELECT COUNT(*) c FROM weigh_tickets").fetchone()["c"]
    dash_before = c.get("/api/dashboard", headers=h).json()["tickets"]

    r = c.post("/api/tickets", headers=h, json=_payload(lane["id"], "WT-OFF-21-A"))

    with connect() as conn:
        after = conn.execute("SELECT COUNT(*) c FROM weigh_tickets").fetchone()["c"]
        written = conn.execute(
            "SELECT id FROM weigh_tickets WHERE ticket_code=?", ("WT-OFF-21-A",)
        ).fetchone()
        rejection = conn.execute(
            """SELECT payload FROM audit_trail WHERE action='ticket_weigh_rejected'
               ORDER BY id DESC LIMIT 1"""
        ).fetchone()
    assert after == before, f"停用车道仍写入正式票：{before} -> {after}"
    assert written is None
    assert r.status_code in (409, 422), r.text
    assert dash_before == c.get("/api/dashboard", headers=h).json()["tickets"]
    # 命运册：拒写必留痕，且当日正式票零增
    assert rejection is not None, "拒写未记命运册"
    payload = json.loads(rejection["payload"])
    assert payload["lane_id"] == lane["id"]
    assert payload["formal_ticket_delta"] == 0
    # 五页同态：车道页、地磅页同标不可过磅
    lanes = c.get("/api/lanes", headers=h).json()["items"]
    got = next(x for x in lanes if x["id"] == lane["id"])
    assert got["weighable"] is False and got["blocked_reason"]
    detail = c.get(f"/api/lanes/{lane['id']}", headers=h).json()
    assert detail["lane"]["weighable"] is False
    assert detail["recent_tickets"] == []
    bridge = c.get(f"/api/bridges/{lane['bridge_id']}", headers=h).json()
    bridge_lane = next(x for x in bridge["lanes"] if x["id"] == lane["id"])
    assert bridge_lane["weighable"] is False
    assert bridge["closed_lanes"] >= 1


def test_21b_disabled_lane_weigh_does_not_accumulate_reconcile_traffic():
    """失败测乙：停用车道试磅仍累计对账流量。"""
    c = TestClient(app)
    h = _auth(c)
    lane = _make_lane(c, h, "LN-OFF-21-B")
    before = c.get(f"/api/reconcile/{BL_REF}", headers=h).json()
    pending_before = c.get("/api/dashboard", headers=h).json()["side_pending"]

    r = c.post("/api/tickets", headers=h, json=_payload(lane["id"], "WT-OFF-21-B"))
    after = c.get(f"/api/reconcile/{BL_REF}", headers=h).json()

    assert after["ticket_sum_t"] == before["ticket_sum_t"], (
        f"停用车道试磅仍累计对账流量：{before['ticket_sum_t']} -> {after['ticket_sum_t']}"
    )
    assert len(after["tickets"]) == len(before["tickets"])
    assert not any(t["ticket_code"] == "WT-OFF-21-B" for t in after["tickets"])
    assert c.get("/api/dashboard", headers=h).json()["side_pending"] == pending_before
    assert r.status_code in (409, 422), r.text


def test_21c_two_sessions_same_disabled_lane_only_contend(monkeypatch):
    """争用第21路：双会话并发打同车道建票，败方只留争用痕。"""
    c0 = TestClient(app)
    h0 = _auth(c0, "admin", "admin123")
    lane = _make_lane(c0, h0, "LN-OFF-21-C")

    # 仅测试用：拉宽持锁窗口，确保两路请求在同一把车道锁上真并发相遇。
    real_validate = tickets_svc.validate_lane_open

    def slow_validate(lane_dict):
        time.sleep(0.25)
        return real_validate(lane_dict)

    monkeypatch.setattr(tickets_svc, "validate_lane_open", slow_validate)

    barrier = threading.Barrier(2)

    def worker(user: str, password: str, ticket_code: str):
        client = TestClient(app)
        headers = _auth(client, user, password)
        barrier.wait(timeout=10)
        resp = client.post(
            "/api/tickets", headers=headers, json=_payload(lane["id"], ticket_code)
        )
        return resp.status_code, resp.text

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(worker, "admin", "admin123", "WT-OFF-21-C1"),
            pool.submit(worker, "writer", "writer123", "WT-OFF-21-C2"),
        ]
        results = [f.result(timeout=30) for f in futures]

    with connect() as conn:
        tickets = conn.execute(
            "SELECT ticket_code FROM weigh_tickets WHERE lane_id=?", (lane["id"],)
        ).fetchall()
        contentions = conn.execute(
            "SELECT actor, action FROM contention_log WHERE lock_key=?",
            (f"lane:{lane['id']}",),
        ).fetchall()

    assert not tickets, f"停用车道抢建出正式票：{[t['ticket_code'] for t in tickets]}"
    assert results and all(code in (409, 422) for code, _ in results), results
    assert contentions, "败方未留争用痕"
    assert any("争用" in (row["action"] or "") for row in contentions)


def test_21d_five_pages_share_one_disabled_verdict():
    """第21序：车道/总览/地磅/对账/过磅五页同态，停用即禁磅。"""
    c = TestClient(app)
    h = _auth(c)
    lane = _make_lane(c, h, "LN-OFF-21-D")
    c.post("/api/tickets", headers=h, json=_payload(lane["id"], "WT-OFF-21-D"))

    # 1 车道页
    lanes = c.get("/api/lanes", headers=h).json()["items"]
    lane_row = next(x for x in lanes if x["id"] == lane["id"])
    assert lane_row["weighable"] is False
    lane_detail = c.get(f"/api/lanes/{lane['id']}", headers=h).json()
    assert lane_detail["lane"]["weighable"] is False
    assert lane_detail["disabled_locked_today"] is True
    # 2 总览页
    dash = c.get("/api/dashboard", headers=h).json()
    assert dash["closed_lanes"] >= 1
    assert dash["disabled_locks_today"] >= 1
    # 3 地磅页
    bridge = c.get(f"/api/bridges/{lane['bridge_id']}", headers=h).json()
    b_lane = next(x for x in bridge["lanes"] if x["id"] == lane["id"])
    assert b_lane["weighable"] is False
    assert bridge["closed_lanes"] >= 1
    # 4 对账页
    recon = c.get(f"/api/reconcile/{BL_REF}", headers=h).json()
    assert recon["counted_tickets"] == len(
        [t for t in c.get("/api/tickets", headers=h).json()["items"]
         if t["bl_ref"] == BL_REF and t["lane_code"] != lane["lane_code"]
         and t["status"] != "作废"]
    )
    assert recon["disabled_locks"], "对账页未带停用命运册"
    # 5 过磅页（后端唯一写口）
    again = c.post(
        "/api/tickets", headers=h, json=_payload(lane["id"], "WT-OFF-21-D2")
    )
    assert again.status_code == 422


def test_21e_same_day_ledger_lock_survives_lane_reopen():
    """命运册当日锁死：停用车道当日改回开放，仍拒写并记偏航。"""
    c = TestClient(app)
    h = _auth(c)
    lane = _make_lane(c, h, "LN-OFF-21-E")
    assert c.post(
        "/api/tickets", headers=h, json=_payload(lane["id"], "WT-OFF-21-E1")
    ).status_code == 422

    with connect() as conn:
        conn.execute(
            "UPDATE weigh_lanes SET status='开放' WHERE id=?", (lane["id"],)
        )
        conn.commit()
    baseline = c.get("/api/dashboard", headers=h).json()["tickets"]

    resp = c.post(
        "/api/tickets", headers=h, json=_payload(lane["id"], "WT-OFF-21-E2")
    )

    with connect() as conn:
        written = conn.execute(
            "SELECT id FROM weigh_tickets WHERE ticket_code=?", ("WT-OFF-21-E2",)
        ).fetchone()
        deviation = conn.execute(
            """SELECT payload FROM audit_trail WHERE action='ticket_weigh_deviation'
               ORDER BY id DESC LIMIT 1"""
        ).fetchone()
    assert resp.status_code == 409
    assert written is None
    assert c.get("/api/dashboard", headers=h).json()["tickets"] == baseline
    assert deviation is not None
    assert json.loads(deviation["payload"])["verdict"] == "停用修复偏航"
