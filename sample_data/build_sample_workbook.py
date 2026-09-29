"""
Build an anonymised sample Costplan-style tender workbook for tests and demos.

Matches real template shape:
- Project Information - 1 / 2 / 3 aliases
- SUMMARY: first Rate/Total pair is Costplan, then each tenderer
- Variance from Costplan = Final Adjusted − Costplan budget (workbook header;
  engine also accepts "Variance to Budget"; staged as VarianceToBudget)
- Level 3 sheets carry Costplan + all contractor Qty/Unit/Rate/Total blocks

Output: sample_data/DEMO_Tender_Comparison_Workbook.xlsx
"""

from pathlib import Path

from openpyxl import Workbook

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "sample_data" / "DEMO_Tender_Comparison_Workbook.xlsx"

COSTPLAN = "Costplan"
SELECTED = "Apex Build Ltd"
TENDERERS = [
    SELECTED,
    "Horizon Construction PLC",
    "Meridian Works Ltd",
]
CONTRACTOR_LABELS = [
    ("Contractor 1 (SELECTED CONTRACTOR) *", SELECTED),
    ("Contractor 2", "Horizon Construction PLC"),
    ("Contractor 3", "Meridian Works Ltd"),
]

# Per L2 element: (ref, name, is_l1,
#   costplan_rate, costplan_total,
#   apex_rate, apex_total,
#   horizon_rate, horizon_total,
#   meridian_rate, meridian_total)
SUMMARY_ROWS = [
    (1, "Substructure", True, None, None, None, None, None, None, None, None),
    (1.1, "Foundations", False, 440, 528000, 450, 540000, 470, 564000, 460, 552000),
    (1.2, "Basement Excavation", False, 0, 0, 0, 0, 0, 0, 0, 0),
    (2, "Superstructure", True, None, None, None, None, None, None, None, None),
    (2.1, "Frame", False, 310, 1317500, 320, 1360000, 340, 1445000, 330, 1402500),
    (2.2, "Upper Floors", False, 180, 504000, 185, 518000, 190, 532000, 188, 526400),
    (3, "Internal Finishes", True, None, None, None, None, None, None, None, None),
    (3.1, "External Walls", False, 205, 430500, 210, 441000, 220, 462000, 215, 451500),
    (4, "Roof", True, None, None, None, None, None, None, None, None),
    (4.1, "Roof Coverings", False, 270, 391500, 275, 398750, 280, 406000, 278, 403100),
]


def _party_l2_total(party_index: int) -> int:
    """
    party_index: 0=Costplan, 1=Apex, 2=Horizon, 3=Meridian
    """
    total = 0
    for row in SUMMARY_ROWS:
        if row[2]:
            continue
        value = row[4 + party_index * 2]
        total += int(value or 0)
    return total


def _write_project_information(wb: Workbook) -> None:
    ws = wb.create_sheet("Project Information - 1", 0)
    ws.append(["Field", "Value"])
    rows = [
        ("Project Number", "DEMO-001"),
        ("Project Name", "Riverside Learning Centre Extension"),
        ("Client Name", "Northbridge Education Trust"),
        ("Location", "Salford Quays Campus"),
        ("Region", "North West"),
        ("Sector", "Education"),
        ("Cost Stage", "Tender"),
        ("Budget Stage", "Pre-Contract"),
        *CONTRACTOR_LABELS,
        ("Data Status", "Draft"),
        ("Demolition", "No"),
        ("New Build", "Yes"),
        ("Refurbishment", "No"),
        ("Horizontal Extension", "Yes"),
        ("Vertical Extension", "No"),
        ("Basement", "No"),
        ("Asbestos", "No"),
        ("Contamination", "No"),
        ("Spec Level", "Medium"),
        ("Site Type", "Brownfield"),
        ("Nr of Storeys", 3),
        ("Total Height Ground To Roof", 13.5),
        ("Basement Area", 0),
        ("Basement Height", 0),
        ("Complexity Rating", 3),
        ("Access Constraints", "Restricted - live campus"),
        ("Occupied?", "Yes"),
        ("Base Date", "2025-06-01"),
        ("Currency", "GBP"),
        ("Programme Length In Weeks", 78),
        ("Programme Type", "Traditional"),
        ("GIFA", 4250),
        (
            "Notes",
            "Fictional sample project for ingestion tests and Stage B demo. "
            "SUMMARY first metric pair is Costplan; variance = tender − Costplan.",
        ),
    ]
    for label, value in rows:
        ws.append([label, value])


def _write_project_quants(wb: Workbook) -> None:
    ws = wb.create_sheet("Project Information - 2")
    ws.append(["Name", "Qty", "Unit", "Comments"])
    ws.append(["GIFA", 4250, "m2", "Gross internal floor area"])
    ws.append(["Site Area", 11800, "m2", ""])
    ws.append(["Parking Spaces", 42, "nr", ""])
    ws.append(["Storeys", 3, "nr", "Above ground"])


def _write_element_quants(wb: Workbook) -> None:
    ws = wb.create_sheet("Project Information - 3")
    ws.append(["Code", "Element", "Qty", "Unit", "Comments"])
    ws.append([1.1, "Foundations", 1200, "m2", ""])
    ws.append([1.2, "Basement Excavation", 0, "m3", "Not applicable"])
    ws.append([2.1, "Frame", 4250, "m2", ""])
    ws.append([2.2, "Upper Floors", 2800, "m2", ""])
    ws.append([3.1, "External Walls", 2100, "m2", ""])
    ws.append([4.1, "Roof", 1450, "m2", ""])


def _write_summary(wb: Workbook) -> None:
    ws = wb.create_sheet("SUMMARY")
    # First Rate/Total pair = Costplan, then each tenderer (matches true template).
    ws.append(
        [
            "Ref",
            "Element",
            COSTPLAN,
            None,
            SELECTED,
            None,
            "Horizon Construction PLC",
            None,
            "Meridian Works Ltd",
            None,
        ]
    )
    ws.append(["", "", "Rate", "Total", "Rate", "Total", "Rate", "Total", "Rate", "Total"])

    for row in SUMMARY_ROWS:
        (
            ref,
            name,
            _is_l1,
            cp_rate,
            cp_total,
            a_rate,
            a_total,
            h_rate,
            h_total,
            m_rate,
            m_total,
        ) = row
        ws.append([ref, name, cp_rate, cp_total, a_rate, a_total, h_rate, h_total, m_rate, m_total])

    costplan_budget = _party_l2_total(0)
    apex_final = _party_l2_total(1)
    horizon_final = _party_l2_total(2)
    meridian_final = _party_l2_total(3)

    ws.append([])
    # Costplan column shows the budget; tenderer columns show final adjusted sums.
    ws.append(
        [
            "",
            "Total Tender Sum (Final Adjusted)",
            None,
            costplan_budget,
            None,
            apex_final,
            None,
            horizon_final,
            None,
            meridian_final,
        ]
    )
    # Variance from Costplan = Final Adjusted − Costplan budget (engine label match).
    ws.append(
        [
            "",
            "Variance from Costplan",
            None,
            0,
            None,
            apex_final - costplan_budget,
            None,
            horizon_final - costplan_budget,
            None,
            meridian_final - costplan_budget,
        ]
    )


def _metric_block(qty, unit, rate, total) -> list:
    return [qty, unit, rate, total]


def _write_l3_sheet(
    wb: Workbook,
    code: str,
    name: str,
    lines: list[dict],
) -> None:
    """
    lines: each dict has description plus metric blocks for
    costplan / apex / horizon / meridian as (qty, unit, rate, total).

    Layout mirrors the true template: Costplan first, then every tenderer.
    Spacer columns keep contractor labels outside neighbouring probe windows
    used by ingestion when choosing the selected-contractor block.
    """
    ws = wb.create_sheet(f"{code} {name}")
    parties = [COSTPLAN, *TENDERERS]

    header_parties: list = [None, None]
    metric_header: list = ["Item", "Description"]
    for party in parties:
        header_parties.extend([party, None, None, None, None, None])
        metric_header.extend(["Qty", "Unit", "Rate", "Total", None, None])
    ws.append(header_parties)
    ws.append(metric_header)

    for line in lines:
        row: list = [None, line["description"]]
        for party in ("costplan", "apex", "horizon", "meridian"):
            qty, unit, rate, total = line[party]
            row.extend(_metric_block(qty, unit, rate, total))
            row.extend([None, None])
        ws.append(row)


def build() -> Path:
    wb = Workbook()
    default = wb.active
    wb.remove(default)

    _write_project_information(wb)
    _write_project_quants(wb)
    _write_element_quants(wb)
    _write_summary(wb)

    _write_l3_sheet(
        wb,
        "1.1",
        "Foundations",
        [
            {
                "description": "Excavate for foundations",
                "costplan": (1200, "m2", 42, 50400),
                "apex": (1200, "m2", 45, 54000),
                "horizon": (1200, "m2", 48, 57600),
                "meridian": (1200, "m2", 46, 55200),
            },
            {
                "description": "Concrete strip foundations",
                "costplan": (180, "m3", 160, 28800),
                "apex": (180, "m3", 165, 29700),
                "horizon": (180, "m3", 170, 30600),
                "meridian": (180, "m3", 168, 30240),
            },
            {
                "description": "Hardcore and blinding",
                "costplan": (1200, "m2", 26, 31200),
                "apex": (1200, "m2", 28, 33600),
                "horizon": (1200, "m2", 30, 36000),
                "meridian": (1200, "m2", 29, 34800),
            },
            {
                "description": "Heading - Ground slab",
                "costplan": (None, None, None, None),
                "apex": (None, None, None, None),
                "horizon": (None, None, None, None),
                "meridian": (None, None, None, None),
            },
            {
                "description": "Reinforced ground slab",
                "costplan": (1200, "m2", 90, 108000),
                "apex": (1200, "m2", 95, 114000),
                "horizon": (1200, "m2", 98, 117600),
                "meridian": (1200, "m2", 96, 115200),
            },
        ],
    )
    _write_l3_sheet(
        wb,
        "2.1",
        "Frame",
        [
            {
                "description": "Steel frame supply and erect",
                "costplan": (185, "t", 2700, 499500),
                "apex": (185, "t", 2800, 518000),
                "horizon": (185, "t", 2950, 545750),
                "meridian": (185, "t", 2850, 527250),
            },
            {
                "description": "Secondary steelwork",
                "costplan": (42, "t", 3000, 126000),
                "apex": (42, "t", 3100, 130200),
                "horizon": (42, "t", 3200, 134400),
                "meridian": (42, "t", 3150, 132300),
            },
            {
                "description": "Fire protection to steel",
                "costplan": (4250, "m2", 17, 72250),
                "apex": (4250, "m2", 18, 76500),
                "horizon": (4250, "m2", 19, 80750),
                "meridian": (4250, "m2", 18.5, 78625),
            },
            {
                "description": "Holding-down bolts and baseplates",
                "costplan": (64, "nr", 210, 13440),
                "apex": (64, "nr", 220, 14080),
                "horizon": (64, "nr", 230, 14720),
                "meridian": (64, "nr", 225, 14400),
            },
        ],
    )

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    wb.save(OUTPUT)

    costplan_budget = _party_l2_total(0)
    print(
        "Costplan budget:",
        costplan_budget,
        "| Apex final:",
        _party_l2_total(1),
        "| Apex variance:",
        _party_l2_total(1) - costplan_budget,
    )
    return OUTPUT


if __name__ == "__main__":
    path = build()
    print(f"Wrote {path}")
