import json
import re
import subprocess
import sys
from typing import Any
from .schemas import NumericCheckResult, QuantCompanySummary, XbrlFact


def execute_deterministic_python(code: str, payload: Any, timeout_sec: float = 2.0) -> dict[str, Any]:
    """Runs ratio & FinRobot/FinRL math in a clean, isolated Python subprocess (-I isolated mode)."""
    proc = subprocess.run(
        [sys.executable, "-I", "-c", code],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        timeout=timeout_sec,
        check=True,
    )
    return json.loads(proc.stdout)


PROHIBITED_ADVICE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b(strong buy|buy rating|sell rating|hold rating|overweight|underweight)\b", re.I), "Broker-dealer rating language"),
    (re.compile(r"\b(price target|target price)\b", re.I), "Price target projection"),
    (re.compile(r"\b(guaranteed|risk-free|certain to rise|sure to outperform|will outperform)\b", re.I), "Promise of future returns"),
    (re.compile(r"\b(you should buy|investors should buy|recommend buying|recommend selling)\b", re.I), "Direct personalized investment advice"),
]


def check_advice_language(markdown: str) -> list[str]:
    violations: list[str] = []
    for pattern, label in PROHIBITED_ADVICE_PATTERNS:
        m = pattern.search(markdown)
        if m:
            violations.append(f'{label}: "{m.group(0)}"')
    return violations


def verify_draft_numbers_in_code(
    markdown: str,
    quant_summaries: list[QuantCompanySummary],
    facts_registry: dict[str, XbrlFact],
) -> dict[str, Any]:
    """Code-based Compliance Check: links every $B, %, and bps token to its verified XBRL Fact ID."""
    valid_by_fact: dict[str, list[float]] = {}
    all_valid: list[tuple[float, str]] = []

    def reg(fid: str, val: float) -> None:
        valid_by_fact.setdefault(fid, []).append(val)
        all_valid.append((val, fid))

    for q in quant_summaries:
        for r in q.rows:
            reg(r.revenueFactId, r.revenueB)
            if r.yoyRevenueGrowthPct is not None:
                reg(r.revenueFactId, r.yoyRevenueGrowthPct)
            reg(r.operatingIncomeFactId, r.operatingIncomeB)
            reg(r.operatingIncomeFactId, r.operatingMarginPct)
            if r.marginDeltaBps is not None:
                reg(r.operatingIncomeFactId, float(r.marginDeltaBps))
                reg(r.operatingIncomeFactId, float(abs(r.marginDeltaBps)))
            if r.netIncomeB is not None and r.netIncomeFactId:
                reg(r.netIncomeFactId, r.netIncomeB)
        if q.threeYearMarginDeltaBps is not None and q.rows:
            last_op = q.rows[-1].operatingIncomeFactId
            reg(last_op, float(q.threeYearMarginDeltaBps))
            reg(last_op, float(abs(q.threeYearMarginDeltaBps)))

    for fid, fact in facts_registry.items():
        reg(fid, fact.valueBillions)

    unverified_fact_refs = sorted(
        {
            f"FACT:{m.group(1)}"
            for m in re.finditer(r"\[FACT:([^\]]+)\]", markdown)
            if f"FACT:{m.group(1)}" not in facts_registry and f"FACT:{m.group(1)}" not in valid_by_fact
        }
    )

    checks: list[NumericCheckResult] = []
    num_re = re.compile(r"(\$[0-9]+(?:\.[0-9]+)?\s*[BM]|[+-]?[0-9]+(?:\.[0-9]+)?%|[+-]?[0-9]+\s*bps)", re.I)

    for line in markdown.splitlines():
        if re.match(r"^\s*\|[\s:-]+\|\s*$", line):
            continue
        line_facts = [f"FACT:{m.group(1)}" for m in re.finditer(r"\[FACT:([^\]]+)\]", line)]
        for m in num_re.finditer(line):
            raw_tok = m.group(0)
            numeric = float(re.sub(r"[^0-9.-]", "", raw_tok))
            tol = 15.0 if "bps" in raw_tok.lower() else 0.25
            matched = False
            matched_fid = line_facts[0] if line_facts else None
            expected_val = None
            reason = "No matching XBRL or sandbox figure found"

            for fid in line_facts:
                for cand in valid_by_fact.get(fid, []):
                    if abs(cand - numeric) <= tol or abs(cand - abs(numeric)) <= tol:
                        matched = True
                        matched_fid = fid
                        expected_val = cand
                        reason = f"Verified against {fid} (sandbox value {cand})"
                        break
                if matched:
                    break

            if not matched and not line_facts:
                for cand_val, cand_fid in all_valid:
                    if abs(cand_val - numeric) <= tol:
                        matched_fid = cand_fid
                        expected_val = cand_val
                        reason = f"Numeric value matches {cand_fid} ({cand_val}), but inline [FACT:...] citation is missing on this line"
                        break

            checks.append(
                NumericCheckResult(
                    extractedText=raw_tok,
                    numericValue=numeric,
                    citedFactId=matched_fid,
                    expectedValue=expected_val,
                    matched=matched,
                    reason=reason,
                )
            )

    verified_count = sum(1 for c in checks if c.matched)
    return {
        "checks": checks[:40],
        "verifiedCount": verified_count,
        "totalCount": len(checks),
        "unverifiedFactRefs": unverified_fact_refs,
    }
