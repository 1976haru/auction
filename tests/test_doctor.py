"""
tests/test_doctor.py
환경 진단 스크립트 - 호출 가능 + 모든 키 OK 반환.
"""


def test_run_diagnostics_returns_checks_list():
    from scripts.doctor import run_diagnostics
    res = run_diagnostics()
    assert "checks" in res
    assert isinstance(res["checks"], list)
    assert len(res["checks"]) >= 10  # 최소 10개 항목
    for c in res["checks"]:
        assert "name" in c
        assert "ok" in c
        assert "value" in c


def test_doctor_all_required_packages_present():
    """test 환경에서 필수 패키지가 모두 설치되어 있어야 통과."""
    from scripts.doctor import REQUIRED_PACKAGES, check_package
    fails = []
    for pkg in REQUIRED_PACKAGES:
        c = check_package(pkg, required=True)
        if not c["ok"]:
            fails.append(pkg)
    assert not fails, f"missing required: {fails}"


def test_doctor_db_init_succeeds():
    from scripts.doctor import check_db_init
    res = check_db_init()
    assert res["ok"] is True


def test_doctor_ci_yaml_validates():
    from scripts.doctor import check_ci_yaml
    res = check_ci_yaml()
    # ci.yml 이 존재하고 핵심 step 다 들어있으면 OK
    assert res["ok"] is True
