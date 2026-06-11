# Heizkostenabrechnung — Sankey Dashboard

Streamlit dashboard that simulates German heat-cost allocation per **HeizkostenV** and **CO2KostAufG**, rendered as a vertical Sankey diagram. The Sankey engine is dependency-free Python (layout ported from [d3-sankey](https://github.com/d3/d3-sankey)) and produces standalone interactive HTML.

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Features

- **Kostenverteilung** Brennstoff → Warmwasser/Heizung → Grund-/Verbrauchskosten → Nutzeinheiten (up to 10), with Gerätemieten and Weitere Kosten.
- **Abrechnungsbericht (HTML)** — complete printable Heizkostenabrechnung (A4, print-to-PDF): Gesamtkosten (§7/§8), CO2-Aufteilung, §9-Trennung, Verteilschlüssel per Pool, Einzelabrechnung je Nutzeinheit with every share spelled out as a formula, Vorauszahlung → Nachzahlung/Guthaben, Kontrollsummen, Hinweise, embedded static Sankey-SVG. Preview in the **Bericht** tab, export via download button.
- **Abrechnungs-Stammdaten** — Objekt, Abrechnungszeitraum (validated: jährlich, max. 12 Monate); Bezeichnungen for Nutzergruppen and per Nutzer.
- **Nutzerwechsel (§9b HeizkostenV)** — up to 4 users per Nutzeinheit with Wechsel-Datum and per-user Vorauszahlung. Costs are split per user: Grundkosten and WW-Verbrauchskosten zeitanteilig (days), Hz-Verbrauchskosten by the **Gradtagszahlen** table (1000 ‰/Jahr, Jun–Aug = 40 ‰ combined). The report shows the §9b split table and one Einzelabrechnung block per user with own Nachzahlung/Guthaben; in the Sankey, users appear as sub-nodes flush below their Nutzeinheit (same color, no gap).
- **Warmwasser-Energie nach §9 Abs. 2 HeizkostenV** — manual kWh, the formula `Q = 2,5 × V × (t_w − 10 °C)`, or the 32 kWh/m² Pauschale (Satz 4).
- **CO2-Kostenaufteilung (CO2KostAufG)** — 10-Stufen-Modell from building emissions and area, or a manual landlord share.
- **Nutzergruppen (§5 Abs. 2 Vorerfassung)** — add up to 3 groups like Nutzeinheiten, each with its own **Leistung** (Heizung, Warmwasser, or Beide), members, consumption, and Verteilschlüssel. Nutzeinheiten not assigned to a group automatically form a **rest pool per Gewerk** (consumption = remainder, own Verteilschlüssel). Abrechnungsart global: "Abrechnungsart 1" (consumption pre-split) or "Kreuzberg" (GK/VK Vorverteilung, GK by area / VK by consumption).
- **Messtechnik per Nutzeinheit** — HKV (Verbrauchseinheiten) or WMZ (kWh). Mixed buildings require homogeneous Heizung pools (validated, with one-click auto-grouping); all-WMZ pools derive their consumption from the meter sums.
- **Validation** — plausibility warnings (pool sums, CO2 caps, empty groups, Zeitraum) and a §12 HeizkostenV info badge when the configuration implies the tenant's 15 % Kürzungsrecht.
- **Presets & exports** — save/load scenarios as versioned JSON (old files upgrade automatically), built-in examples, CSV breakdown export (German Excel), standalone Sankey HTML export.

## Code layout

```
app.py                   orchestrator (state → sidebar → compute → validate →
                         tabs: Diagramm | Bericht, exports)
ui/                      Streamlit layer: state.py (all widget defaults),
                         sidebar.py, results.py, sankey_view.py, presets.py, styles.py
sankey/heizkosten/       domain: model.py (dataclasses), compute.py (compute_all,
                         assemble_pools), nutzerwechsel.py (§9b Gradtage/Tage),
                         topology.py (unified Sankey topology), report.py
                         (printable Abrechnung HTML), validate.py,
                         fmt.py (German number formatting), constants.py
sankey/                  generic engine: graph.py, layout.py (d3-sankey port),
                         render.py (interactive HTML + static SVG), orient.py
tests/                   pytest suite incl. Streamlit AppTest end-to-end smoke tests
```

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest tests/
```

## Interaction (dashboard & exported HTML)

- **Hover a node** — dims unrelated flows; highlights all incoming/outgoing flows; tooltip lists flows with labels and values.
- **Hover a flow** — highlights that ribbon only; tooltip shows source → target, label, and weight.
