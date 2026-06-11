"""End-to-end smoke tests: run the real Streamlit script in all modes."""
import pytest
from streamlit.testing.v1 import AppTest

APP = "app.py"
TIMEOUT = 15


def run_app(**session):
    at = AppTest.from_file(APP, default_timeout=TIMEOUT)
    for key, val in session.items():
        at.session_state[key] = val
    at.run()
    assert not at.exception, at.exception
    return at


def one_group(leistung="Heizung", members=("Nutzeinheit 1",)):
    return dict(
        ng_group_ids=[1],
        ng_1_leistung=leistung,
        ng_1_members=list(members),
    )


def test_base_mode():
    run_app()


def test_base_mode_with_co2():
    run_app(co2_aktiv=True)


@pytest.mark.parametrize("ng_type", ["Abrechnungsart 1", "Kreuzberg"])
@pytest.mark.parametrize("leistung", ["Heizung", "Warmwasser", "Beide"])
def test_group_modes(ng_type, leistung):
    run_app(ng_type=ng_type, co2_aktiv=True, **one_group(leistung))


def test_three_explicit_groups():
    at = run_app(
        ng_group_ids=[1, 2, 3],
        ng_1_leistung="Beide", ng_1_members=["Nutzeinheit 1"],
        ng_2_leistung="Beide", ng_2_members=["Nutzeinheit 2"],
        ng_3_leistung="Beide", ng_3_members=[],
        ng_1_hz_kwh=10000.0, ng_1_ww_kwh=2000.0,
        ng_2_hz_kwh=14000.0, ng_2_ww_kwh=3000.0,
    )
    assert at.session_state["ng_group_ids"] == [1, 2, 3]


@pytest.mark.parametrize("ww_modus", ["Manuell", "Formel (§9 Abs. 2)", "Pauschale (32 kWh/m²)"])
def test_ww_energie_modes(ww_modus):
    run_app(ww_modus=ww_modus)


def test_co2_stufenmodell():
    at = run_app(co2_aktiv=True, co2_modus="Stufenmodell", co2_emission=4000.0)
    assert any("Stufe" in m.value for m in at.markdown)


def test_paragraph12_info_shown():
    at = run_app(vhz=100)
    assert any("§12" in str(i.value) for i in at.info)


def test_mixed_messtechnik_shows_error_and_derive_button():
    at = run_app(ne_1_messtechnik="WMZ", ne_1_hz_wert=12000.0)
    assert any("Messtechnik" in str(e.value) for e in at.error)
    # auto-derive: one explicit Hz group with the WMZ NEs; HKV NEs form the rest
    button = next(b for b in at.button if b.key == "btn_derive_groups")
    at = button.click().run()
    assert not at.exception
    assert at.session_state["ng_group_ids"] == [1]
    assert at.session_state["ng_1_leistung"] == "Heizung"
    assert at.session_state["ng_1_members"] == ["Nutzeinheit 1"]
    assert not at.error


def test_wmz_group_without_slider():
    """An all-WMZ group derives its kWh from the meters — app must still run."""
    at = run_app(
        ne_1_messtechnik="WMZ",
        ne_1_hz_wert=12000.0,
        **one_group("Heizung"),
    )
    assert not at.error


def test_overlapping_groups_same_leistung():
    """Groups are non-exclusive: NE 1 in two Heizung groups renders cleanly
    with an info hinweis about the multi-pool membership."""
    at = run_app(
        ng_group_ids=[1, 2],
        ng_1_leistung="Heizung", ng_1_members=["Nutzeinheit 1"],
        ng_2_leistung="Heizung", ng_2_members=["Nutzeinheit 1", "Nutzeinheit 2"],
        ng_1_hz_kwh=10000.0,
    )
    assert not at.error
    assert "Nutzeinheit 1" in at.session_state["ng_1_members"]
    assert "Nutzeinheit 1" in at.session_state["ng_2_members"]
    assert any("mehreren Pools" in str(i.value) for i in at.info)


def test_report_export_present():
    """The report download button exists and per-user billing keys are seeded."""
    at = run_app(ne_1_nutzer_1_vz=1500.0, ne_1_nutzer_1_bez="Whg. 1 links")
    labels = [d.proto.label for d in at.get("download_button")]
    assert any("Bericht" in l for l in labels), labels
    assert at.session_state["ne_1_nutzer_1_vz"] == 1500.0
    assert not at.error


def test_nutzerwechsel_renders():
    """A second user on NE 1 renders cleanly: user keys seeded, no error."""
    from datetime import date

    year = date.today().year - 1
    at = run_app(
        ne_1_nutzer_ids=[1, 2],
        ne_1_nutzer_1_bez="Fam. Alt",
        ne_1_nutzer_2_bez="Fam. Neu",
        ne_1_nutzer_2_von=date(year, 7, 1),
        ne_1_nutzer_2_vz=600.0,
    )
    assert at.session_state["ne_1_nutzer_ids"] == [1, 2]
    assert not at.error


def test_ng_bezeichnung_renders():
    at = run_app(ng_1_bezeichnung="Vorderhaus", **one_group())
    assert at.session_state["ng_1_bezeichnung"] == "Vorderhaus"
    assert not at.error


def test_builtin_preset_loads():
    at = run_app()
    at.session_state["preset_choice"] = "Kreuzberg gemischt WMZ/HKV"
    button = next(b for b in at.button if b.key == "btn_load_preset")
    at = button.click().run()
    assert not at.exception, at.exception
    assert at.session_state["ng_group_ids"] == [1]
    assert at.session_state["ng_1_leistung"] == "Heizung"
    assert at.session_state["ng_type"] == "Kreuzberg"
    assert len(at.session_state["ne_list"]) == 4
    assert at.session_state["ne_1_messtechnik"] == "WMZ"
    assert not at.error
