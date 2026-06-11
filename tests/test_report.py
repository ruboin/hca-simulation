"""Report builder: section completeness, golden numbers, saldo math, static SVG."""
from datetime import date

import pytest

import sankey.heizkosten as hk
from sankey import build_graph, layout_graph, render_static_svg
from sankey.heizkosten import build_report_html
from sankey.heizkosten.topology import build_topology
from test_unified_compute import make_scenario, std_groups


def report_for(scenario, svg=None):
    results = hk.compute_all(scenario)
    hinweise = hk.validate_scenario(scenario, results)
    return build_report_html(scenario, results, hinweise, sankey_svg=svg)


def full_scenario(**over):
    s = make_scenario(**over)
    s.objekt = "MFH Beispielstraße 12"
    s.zeitraum_von = date(2025, 1, 1)
    s.zeitraum_bis = date(2025, 12, 31)
    s.nutzeinheiten[0].nutzer = [
        hk.NutzerConfig("Whg. 1 links", vorauszahlung_eur=3200.0)]   # > total → Guthaben
    s.nutzeinheiten[1].nutzer = [
        hk.NutzerConfig(vorauszahlung_eur=1000.0)]                   # < total → Nachzahlung
    return s


class TestSections:
    def test_all_sections_and_citations_present(self):
        html = report_for(full_scenario())
        for fragment in [
            "A · Gesamtkosten der Abrechnungseinheit",
            "B · CO2-Kostenaufteilung",
            "C · Trennung Warmwasser / Heizung",
            "D · Verteilschlüssel",
            "E · Einzelabrechnungen der Nutzeinheiten",
            "F · Gesamtübersicht &amp; Kontrollsummen",
            "G · Hinweise &amp; Plausibilität",
            "§7 Abs. 2, §8 Abs. 2 HeizkostenV",
            "CO2KostAufG",
            "§9 HeizkostenV",
            "§7 Abs. 1, §8 Abs. 1, §5 Abs. 2 HeizkostenV",
        ]:
            assert fragment in html, fragment

    def test_kopf_carries_objekt_and_zeitraum(self):
        html = report_for(full_scenario())
        assert "MFH Beispielstraße 12" in html
        assert "01.01.2025 – 31.12.2025" in html

    def test_bezeichnung_used_in_einzelabrechnung(self):
        html = report_for(full_scenario())
        assert "Nutzeinheit 1 — Whg. 1 links" in html


class TestNumbers:
    def test_golden_values_german_format(self):
        html = report_for(full_scenario())
        assert "6.132,00 €" in html      # Gesamt nach CO2-Abzug
        assert "1.694,04 €" in html      # Kosten Warmwasser
        assert "5.047,96 €" in html      # Kosten Heizung
        assert "9.680 kWh" in html       # WW-Energieanteil

    def test_kontrollsumme_ok(self):
        html = report_for(full_scenario())
        assert "vollständig verteilt" in html
        assert 'class="kontroll-fail"' not in html

    def test_saldo_directions(self):
        html = report_for(full_scenario())
        assert "Guthaben" in html        # NE 1: 3.200 € Vorauszahlung > 2.905,15 €
        assert "Nachzahlung" in html     # NE 2: 1.000 € Vorauszahlung < 3.836,85 €
        # NE 1 Guthaben amount: 3200 − 2905.1531… = 294.85
        assert "294,85 €" in html

    def test_formula_rows_spell_out_shares(self):
        html = report_for(full_scenario())
        # Base mode WW GK of NE 1: 68 m² / 158 m² × 508,21 €
        assert "68,0 m² / 158,0 m²" in html
        assert "508,21 €" in html


class TestGroupedModes:
    def test_art1_pool_table(self):
        html = report_for(full_scenario(ng_art="art1", groups=std_groups()))
        assert "Rest (NG 2)" in html
        assert "Verbrauchsanteil" in html

    def test_kreuzberg_vorverteilung(self):
        html = report_for(full_scenario(ng_art="kreuzberg", groups=std_groups()))
        assert "Kreuzberger Schlüssel" in html
        assert "aus GK-Anteil" in html

    @pytest.mark.parametrize("ng_art", ["art1", "kreuzberg"])
    def test_kontrollsumme_grouped(self, ng_art):
        html = report_for(full_scenario(ng_art=ng_art, groups=std_groups()))
        assert "vollständig verteilt" in html


class TestNutzerwechsel:
    def wechsel_scenario(self):
        s = full_scenario()
        s.nutzeinheiten[0].nutzer = [
            hk.NutzerConfig("Fam. Alt", vorauszahlung_eur=2000.0),
            hk.NutzerConfig("Fam. Neumann", von=date(2025, 7, 1),
                            vorauszahlung_eur=500.0),
        ]
        return s

    def test_split_table_and_user_blocks(self):
        html = report_for(self.wechsel_scenario())
        assert "Aufteilung bei Nutzerwechsel (§9b Abs. 2 HeizkostenV)" in html
        assert "Fam. Alt" in html and "Fam. Neumann" in html
        assert "Gradtag-Anteil" in html and "Tage-Anteil" in html
        assert "01.01.2025 – 30.06.2025" in html
        assert "01.07.2025 – 31.12.2025" in html

    def test_per_user_saldo(self):
        html = report_for(self.wechsel_scenario())
        # both directions appear (Alt overpaid, Neumann underpaid)
        assert "Guthaben" in html and "Nachzahlung" in html

    def test_kontrollsumme_with_wechsel(self):
        html = report_for(self.wechsel_scenario())
        assert "vollständig verteilt" in html
        assert 'class="kontroll-fail"' not in html

    def test_uebersicht_lists_users(self):
        html = report_for(self.wechsel_scenario())
        assert "Nutzeinheit 1 · Fam. Alt" in html
        assert "Nutzeinheit 1 · Fam. Neumann" in html


class TestNgBezeichnung:
    def test_appears_in_verteilung(self):
        s = full_scenario(ng_art="art1", groups=std_groups())
        s.groups[0].bezeichnung = "Vorderhaus"
        html = report_for(s)
        assert "NG 1 „Vorderhaus“" in html


class TestHinweise:
    def test_zeitraum_missing_hinweis_in_report(self):
        s = make_scenario()   # no zeitraum set
        html = report_for(s)
        assert "Kein Abrechnungszeitraum" in html

    def test_simulation_disclaimer(self):
        html = report_for(full_scenario())
        assert "Simulation" in html
        assert "keine rechtsverbindliche" in html


class TestStaticSvg:
    def graph(self, scenario):
        results = hk.compute_all(scenario)
        topo = build_topology(scenario, results,
                              [ne.id for ne in scenario.nutzeinheiten])
        graph = build_graph(topo.flows, node_styles=topo.node_styles, default_padding=10)
        layout_graph(graph, node_sort_key=topo.sort_key, **hk.LAYOUT)
        return graph

    def test_svg_wellformed_and_complete(self):
        graph = self.graph(full_scenario())
        svg = render_static_svg(graph, value_unit="€", locale="de")
        assert svg.startswith("<svg") and svg.endswith("</svg>")
        assert svg.count("<rect ") == len(graph["nodes"])
        assert svg.count("<path ") == len(graph["links"])
        assert "<script" not in svg

    def test_svg_embedded_in_report(self):
        scenario = full_scenario()
        svg = render_static_svg(self.graph(scenario), value_unit="€", locale="de")
        html = report_for(scenario, svg=svg)
        assert "H · Kostenfluss-Diagramm" in html
        assert "<svg" in html
