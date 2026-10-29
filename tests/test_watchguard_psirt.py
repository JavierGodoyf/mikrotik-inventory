import pytest

from app.watchguard import psirt

# Fragmento con la misma estructura que la tabla de https://psirt.watchguard.com/.
ROW = (
    '<tr><td><span class="rec-id">{id}</span></td>'
    '<td><a href="{href}"><span class="sevchip" title="{sev}"></span>{summary}</a></td>'
    '<td><time datetime="2026-01-01">2026-01-01</time></td>'
    '<td class="affcell"><div class="prod">Fireware OS {plats}</div>'
    '<div class="prod">WatchGuard Cloud <span class="aff">&gt;= 1.0</span></div></td></tr>'
)


def plat(name, aff, naff):
    head = f'<span class="plat"><span class="platchip">{name}</span></span>' if name else ""
    return f'{head}<span class="aff">{aff}</span><span class="naff">{naff}</span>'


HTML = (
    "<table><thead></thead><tbody>"
    + ROW.format(
        id="WGSA-2026-00001",
        href="/WGSA-2026-00001/",
        sev="Critical (CVSS 9.8)",
        summary="Fallo en IKEv2 &amp; VPN",
        plats=plat("", "&gt;= 2025.1, &lt; 2026.4, &gt;= 12.0, &lt;= 12.12.3", "&gt;= 2026.4, &gt;= 12.12.4")
        + plat("T15/T35", "&gt;= 12.5, &lt;= 12.5.21", "&gt;= 12.5.22"),
    )
    + ROW.format(
        id="WGSA-2026-00002",
        href="javascript:alert(1)",
        sev="High (CVSS 7.5)",
        summary="Abierto",
        plats=plat("", "&gt;= 2025.1", "—"),
    )
    # Aviso sin Fireware OS: se ignora.
    + '<tr><td><span class="rec-id">WGSA-2026-00003</span></td>'
    '<td><a href="/x/"><span class="sevchip" title="Low"></span>x</a></td>'
    '<td class="affcell"><div class="prod">AuthPoint <span class="aff">&gt;= 1.0</span></div></td></tr>'
    "</tbody></table>"
)


@pytest.fixture(scope="module")
def advisories():
    return psirt.parse_advisories(HTML)


@pytest.mark.parametrize(
    "a, b, expected",
    [
        ("12.5.22", "12.12.4", -1),
        ("2026.4", "12.12.4", 1),
        ("11.12.4+541730", "11.12.4", 0),
        ("12.10.4-b701004", "12.10.4", 0),
        ("12.12.2.B745592", "12.12.2", 0),
        ("2026.4", "2026.4.0", 0),
    ],
)
def test_compare_versions(a, b, expected):
    result = psirt.compare_versions(a, b)
    assert (result > 0) - (result < 0) == expected


def test_branch_of():
    assert psirt.branch_of("M290", "2026.4") == "actual"
    assert psirt.branch_of("T35", "12.5.22") == "T15/T35"
    assert psirt.branch_of("T45", "12.9.2") == "12.x"


def test_open_range_2025_has_no_upper_bound():
    ranges = psirt.parse_ranges(">= 2025.1")
    assert psirt.in_ranges("2025.1.1", ranges)
    assert psirt.in_ranges("2026.4", ranges)
    assert not psirt.in_ranges("12.12.4", ranges)


def test_open_range_12x_limited_to_branch():
    ranges = psirt.parse_ranges(">= 11.10.2")
    assert psirt.in_ranges("11.12.4", ranges)
    assert not psirt.in_ranges("12.0", ranges)


def test_multiple_ranges():
    ranges = psirt.parse_ranges(">= 2025.1, < 2026.4, >= 12.0, <= 12.12.3, = 11.9")
    assert psirt.in_ranges("2026.3.1", ranges)
    assert not psirt.in_ranges("2026.4", ranges)
    assert psirt.in_ranges("12.12.3", ranges)
    assert not psirt.in_ranges("12.12.4", ranges)
    assert psirt.in_ranges("11.9", ranges)
    assert not psirt.in_ranges("11.8", ranges)


def test_parse_advisories(advisories):
    assert [a["id"] for a in advisories] == ["WGSA-2026-00001", "WGSA-2026-00002"]
    first = advisories[0]
    assert (first["severity"], first["score"]) == ("critical", "9.8")
    assert first["summary"] == "Fallo en IKEv2 & VPN"
    assert first["url"] == "https://psirt.watchguard.com/WGSA-2026-00001/"
    assert first["platforms"]["Default"]["not_affected"] == ["2026.4", "12.12.4"]
    assert first["platforms"]["T15/T35"]["not_affected"] == ["12.5.22"]


def test_non_https_links_are_replaced(advisories):
    assert advisories[1]["url"] == "https://psirt.watchguard.com/WGSA-2026-00002/"


def test_latest_by_branch(advisories):
    assert psirt.latest_by_branch(advisories) == {"actual": "2026.4", "12.x": "12.12.4", "T15/T35": "12.5.22"}


def test_latest_t15_from_default_platform():
    adv = [{"platforms": {"Default": {"affected": [], "not_affected": ["12.5.23", "12.12.5"]}}}]
    assert psirt.latest_by_branch(adv)["T15/T35"] == "12.5.23"


def test_advisories_for(advisories):
    found = psirt.advisories_for(advisories, "M290", "2026.3.1")
    assert [(a["id"], a["fix"]) for a in found] == [("WGSA-2026-00001", "2026.4"), ("WGSA-2026-00002", None)]
    # El aviso abierto ">= 2025.1" también afecta a 2026.4.
    assert [a["id"] for a in psirt.advisories_for(advisories, "M290", "2026.4")] == ["WGSA-2026-00002"]
    assert [a["fix"] for a in psirt.advisories_for(advisories, "M470", "12.12.3")] == ["12.12.4"]
    assert psirt.advisories_for(advisories, "M470", "12.12.4") == []
    assert [a["fix"] for a in psirt.advisories_for(advisories, "T15", "12.5.10")] == ["12.5.22"]
    assert psirt.advisories_for(advisories, "T35", "12.5.22") == []
