"""
tests/test_export_static_dashboard.py
정적 대시보드 export 스모크 테스트.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import export_static_dashboard as ex


def test_fallback_payload_shape():
    p = ex._fallback_payload()
    assert "summary" in p
    assert "recommendations" in p and len(p["recommendations"]) >= 5
    assert "action_items" in p and len(p["action_items"]) >= 1
    assert "items" in p and len(p["items"]) >= 20
    assert "agent_status" in p and len(p["agent_status"]) >= 10
    rs = p["risk_summary"]
    assert {"low", "medium", "high"}.issubset(rs.keys())


def test_export_writes_json(tmp_path, monkeypatch):
    # OUT_PATH 를 tmp 로 돌려 실제 파일을 덮어쓰지 않게 한다.
    target = tmp_path / "mock_dashboard.json"
    monkeypatch.setattr(ex, "OUT_PATH", target)
    out = ex.export()
    assert out == target
    assert target.exists()
    data = json.loads(target.read_text(encoding="utf-8"))
    assert "summary" in data
    assert "recommendations" in data
    assert isinstance(data["recommendations"], list)
    assert "items" in data
    assert "agent_status" in data
    # 최소 추천 1건 (DB 기반이든 fallback 이든)
    assert len(data["recommendations"]) >= 1


def test_repo_dashboard_json_exists():
    """repo 에 체크인된 정적 JSON 도 항상 valid 해야 한다."""
    p = Path(__file__).resolve().parent.parent / "docs" / "data" / "mock_dashboard.json"
    if not p.exists():
        pytest.skip("docs/data/mock_dashboard.json not generated yet")
    data = json.loads(p.read_text(encoding="utf-8"))
    assert "summary" in data
    assert "agent_status" in data
