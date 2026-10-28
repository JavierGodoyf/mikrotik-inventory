from app.evaluate import (
    STATUS_AHEAD,
    STATUS_MANUAL,
    STATUS_OK,
    STATUS_OUTDATED,
    STATUS_UNKNOWN,
    STATUS_V6_FINAL,
    evaluate,
    target_line,
)

LATEST = {"stable": "7.25", "long-term": "7.23.8"}


def make(**kwargs):
    base = dict(
        installed_version="7.24.1",
        architecture="arm",
        free_hdd_kb=100_000,
        preferred_channel="stable",
        latest=LATEST,
    )
    base.update(kwargs)
    return evaluate(**base)


def test_outdated_v7():
    result = make()
    assert result.status == STATUS_OUTDATED
    assert result.target_version == "7.25"


def test_up_to_date_v7():
    result = make(installed_version="7.25")
    assert result.status == STATUS_OK


def test_long_term_channel():
    result = make(preferred_channel="long-term")
    assert result.target_version == "7.23.8"


def test_channel_missing_falls_back_to_stable():
    result = make(preferred_channel="testing")
    assert result.target_version == "7.25"


def test_ahead_of_published():
    result = make(installed_version="7.26beta4")
    assert result.status == STATUS_AHEAD


def test_v6_to_v7_is_manual():
    result = make(installed_version="6.49.23", architecture="mipsbe")
    assert result.status == STATUS_MANUAL
    assert "v6 a 7.25" in result.message


def test_v6_to_v7_tight_flash_mentions_netinstall():
    result = make(installed_version="6.49.23", architecture="smips", free_hdd_kb=8_000)
    assert result.status == STATUS_MANUAL
    assert "netinstall" in result.message


def test_v6_without_v7_route_and_old():
    result = make(installed_version="6.49.10", architecture="mipsle", latest={"stable": "6.49.23"})
    assert result.status == STATUS_V6_FINAL
    assert "no hay ruta a v7" in result.message


def test_v6_final_up_to_date():
    result = make(
        installed_version="6.49.23",
        architecture="mipsle",
        latest={"stable": "6.49.23", "long-term": "6.49.23"},
    )
    assert result.status == STATUS_OK
    assert "no tiene ruta a v7" in result.message


def test_router_reported_version_wins():
    result = make(installed_version="7.20", reported_latest="7.26")
    assert result.target_version == "7.26"
    assert result.target_source == "router"


def test_routerboot_flag():
    result = make(routerboot_current="6.49.12", routerboot_upgrade="7.2")
    assert result.routerboot_outdated is True
    assert "RouterBOOT" in result.message


def test_no_target_available():
    result = make(latest={})
    assert result.status == STATUS_UNKNOWN


def test_target_line():
    assert target_line("7.16.2", "arm") == "7"
    assert target_line("6.49.23", "arm") == "7"
    assert target_line("6.49.23", "mipsle") == "6"
