from typing import Any
from .edgar import CompanyMeta
from .schemas import QuantCompanySummary, QuantYearRow, XbrlFact
from .sandbox import execute_deterministic_python


def compute_quant_with_finrobot_and_finrl(
    meta: CompanyMeta,
    revenues: list[XbrlFact],
    operating_income: list[XbrlFact],
    net_income: list[XbrlFact],
    years_count: int = 3,
) -> QuantCompanySummary:
    rev_by_fy = {f.fiscalYear: f for f in revenues}
    op_by_fy = {f.fiscalYear: f for f in operating_income}
    net_by_fy = {f.fiscalYear: f for f in net_income}

    common_years = sorted(set(rev_by_fy) & set(op_by_fy))[-max(2, min(4, years_count)) :]

    records = []
    for fy in common_years:
        r, o = rev_by_fy[fy], op_by_fy[fy]
        n = net_by_fy.get(fy)
        records.append(
            {
                "fy": fy,
                "periodEnd": r.periodEnd,
                "revVal": r.value,
                "revFactId": r.factId,
                "opVal": o.value,
                "opFactId": o.factId,
                "netVal": n.value if n else None,
                "netFactId": n.factId if n else None,
            }
        )

    sandbox_code = """
import json, sys, math
records = json.loads(sys.stdin.read())
rows = []
for i, cur in enumerate(records):
    prev = records[i - 1] if i > 0 else None
    rev_b = round(cur["revVal"] / 1e9, 2)
    op_b = round(cur["opVal"] / 1e9, 2)
    net_b = round(cur["netVal"] / 1e9, 2) if cur["netVal"] is not None else None
    op_margin = round((cur["opVal"] / cur["revVal"]) * 100.0, 2)
    net_margin = round((cur["netVal"] / cur["revVal"]) * 100.0, 2) if cur["netVal"] is not None else None
    yoy_rev = round(((cur["revVal"] - prev["revVal"]) / prev["revVal"]) * 100.0, 2) if prev else None
    prev_margin = (prev["opVal"] / prev["revVal"]) * 100.0 if prev else None
    delta_bps = int(round((op_margin - prev_margin) * 100)) if prev_margin is not None else None
    rows.append({
        "fiscalYear": cur["fy"],
        "periodEnd": cur["periodEnd"],
        "revenueB": rev_b,
        "revenueFactId": cur["revFactId"],
        "operatingIncomeB": op_b,
        "operatingIncomeFactId": cur["opFactId"],
        "netIncomeB": net_b,
        "netIncomeFactId": cur["netFactId"],
        "operatingMarginPct": op_margin,
        "netMarginPct": net_margin,
        "yoyRevenueGrowthPct": yoy_rev,
        "marginDeltaBps": delta_bps,
    })

cagr_rev = None
if len(rows) >= 2 and rows[0]["revenueB"] > 0:
    n_yrs = len(rows) - 1
    cagr_rev = round(((rows[-1]["revenueB"] / rows[0]["revenueB"]) ** (1.0 / n_yrs) - 1.0) * 100.0, 2)

margins = [r["operatingMarginPct"] for r in rows]
mean_m = sum(margins) / max(1, len(margins))
std_m = math.sqrt(sum((m - mean_m) ** 2 for m in margins) / max(1, len(margins)))
regime = "LOW_VOLATILITY_EXPANSION" if (len(margins) >= 2 and margins[-1] >= margins[0] and std_m < 6.0) else "HIGH_DISPERSION_SHIFT"

print(json.dumps({
    "rows": rows,
    "finrobotPeerMetrics": {
        "revenueCagrPct": cagr_rev,
        "latestOperatingIncomeB": rows[-1]["operatingIncomeB"] if rows else None,
        "latestNetMarginPct": rows[-1]["netMarginPct"] if rows else None,
    },
    "finrlRiskRegime": {
        "fundamentalTurbulenceStdPct": round(std_m, 2),
        "regimeLabel": regime,
        "note": "Quantitative regime diagnostic only; non-advisory."
    }
}))
""".strip()

    result = execute_deterministic_python(sandbox_code, records)
    rows = [QuantYearRow.model_validate(r) for r in result["rows"]]
    three_yr_delta = (
        int(round((rows[-1].operatingMarginPct - rows[0].operatingMarginPct) * 100))
        if len(rows) >= 2
        else None
    )

    return QuantCompanySummary(
        ticker=meta.ticker,
        companyName=meta.companyName,
        cik=meta.cik,
        fiscalYearEndMonth=meta.fiscalYearEndMonth,
        sourceType=revenues[0].sourceType if revenues else "cached_edgar",
        rows=rows,
        threeYearMarginDeltaBps=three_yr_delta,
        latestOperatingMarginPct=rows[-1].operatingMarginPct if rows else None,
        finrobotPeerMetrics=result.get("finrobotPeerMetrics", {}),
        finrlRiskRegime=result.get("finrlRiskRegime", {}),
        sandboxCodeExecuted=sandbox_code,
    )
