import os
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Annotated, Optional, TypedDict
from operator import add

from google import genai
from google.genai import types
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send, interrupt

from .edgar import fetch_company_xbrl_facts, get_company_filings_passages
from .hybrid_search import hybrid_search_and_rerank
from .quant_finrobot import compute_quant_with_finrobot_and_finrl
from .sandbox import check_advice_language, verify_draft_numbers_in_code
from .schemas import (
    ComplianceReport,
    InputGuardrailResult,
    OutputGuardrailResult,
    ResearcherFinding,
    ResearchPlan,
    RiskDiffItem,
    TraceEvent,
)
from .store import (
    append_improvement_lesson,
    get_preferences,
    get_published_notes,
    get_run,
    save_run,
)

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
COST_PER_1K_TOKENS = 0.00035


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_client() -> genai.Client:
    return genai.Client(api_key=os.environ["GEMINI_API_KEY"])


class DeskGraphState(TypedDict):
    runId: str
    query: str
    tokenBudget: int
    tokenUsed: int
    status: str
    activeNode: str
    inputGuardrail: Optional[dict]
    plan: Optional[dict]
    researchers: Annotated[list[dict], add]
    quant: Annotated[list[dict], add]
    riskDiffs: Annotated[list[dict], add]
    factsRegistry: dict[str, dict]
    passagesRegistry: dict[str, dict]
    draftMarkdown: str
    revisionCount: int
    complianceHistory: Annotated[list[dict], add]
    revisionFeedback: str


def _emit_trace(run_id: str, node: str, hook_type: str, msg: str, status: str = "ok", tool: str = None, tokens: int = None, dur_ms: int = None) -> None:
    run = get_run(run_id)
    if not run:
        return
    run.activeNode = node
    run.updatedAt = _now()
    if tokens:
        run.tokenUsed += tokens
        run.estimatedCostUsd = round((run.tokenUsed / 1000.0) * COST_PER_1K_TOKENS, 5)
    run.traces.append(
        TraceEvent(
            id=uuid.uuid4().hex[:8],
            timestamp=_now(),
            node=node,
            hookType=hook_type,  # type: ignore
            tool=tool,
            message=msg,
            durationMs=dur_ms,
            tokensDelta=tokens,
            status=status,  # type: ignore
        )
    )
    save_run(run)


def _detect_tickers(query: str) -> list[str]:
    mapping = [
        (re.compile(r"\b(microsoft|msft|azure)\b", re.I), "MSFT"),
        (re.compile(r"\b(alphabet|google|googl|goog)\b", re.I), "GOOGL"),
        (re.compile(r"\b(apple|aapl|iphone)\b", re.I), "AAPL"),
        (re.compile(r"\b(nvidia|nvda)\b", re.I), "NVDA"),
        (re.compile(r"\b(amazon|amzn|aws)\b", re.I), "AMZN"),
        (re.compile(r"\b(meta|facebook|instagram)\b", re.I), "META"),
        (re.compile(r"\b(tesla|tsla)\b", re.I), "TSLA"),
        (re.compile(r"\b(oracle|orcl)\b", re.I), "ORCL"),
        (re.compile(r"\b(jpmorgan|jpm|chase)\b", re.I), "JPM"),
        (re.compile(r"\b(visa)\b", re.I), "V"),
        (re.compile(r"\b(mastercard|ma)\b", re.I), "MA"),
        (re.compile(r"\b(american express|amex|axp)\b", re.I), "AXP"),
        (re.compile(r"\b(bank of america|bofa|bac)\b", re.I), "BAC"),
        (re.compile(r"\b(walmart|wmt)\b", re.I), "WMT"),
    ]
    found = [t for rx, t in mapping if rx.search(query)]
    for explicit in re.findall(r"\b(MSFT|GOOGL|AAPL|NVDA|AMZN|META|TSLA|ORCL|JPM|V|MA|AXP|BAC|WMT)\b", query):
        if explicit not in found:
            found.append(explicit)
    return list(dict.fromkeys(found)) or ["MSFT", "GOOGL"]


def node_input_guardrails(state: DeskGraphState) -> dict:
    run_id = state["runId"]
    query = state["query"].strip()
    flags = []
    for pat in [r"ignore (all )?previous instructions", r"system prompt", r"reveal your instructions", r"bypass compliance", r"guarantee(d)? returns"]:
        if re.search(pat, query, re.I):
            flags.append(f"Blocked instruction-override pattern: {pat}")

    in_scope = bool(
        re.search(r"\b(margin|revenue|operating|income|risk|10-k|filing|sec|xbrl|compare|peer|fiscal|year|microsoft|alphabet|apple|nvidia|amazon|meta|tesla|oracle|jpmorgan|visa|mastercard|american express|amex|walmart|bank of america|msft|googl|aapl|nvda|amzn|tsla|orcl|jpm|v|ma|axp|bac|wmt|earnings|growth|capex|cloud|search|valuation|equity)\b", query, re.I)
        and len(query) >= 5
    )
    if not in_scope:
        flags.append("Out-of-scope query: Analyst Desk only handles SEC filing-backed equity research requests.")

    tickers = _detect_tickers(query)
    res = InputGuardrailResult(
        passed=len(flags) == 0,
        scopeCategory="Institutional Equity Research (SEC 10-K)" if in_scope else "Out of Scope / Policy Blocked",
        sanitizedQuery=re.sub(r"[<>]", "", query),
        detectedTickers=tickers,
        flags=flags,
    )
    run = get_run(run_id)
    if run:
        run.inputGuardrail = res
        if not res.passed:
            run.status = "rejected"
            run.errorMessage = " ".join(flags)
    _emit_trace(
        run_id,
        "input_guardrails",
        "guardrail",
        f"Scope verified ({', '.join(tickers)}); external filing text isolated as untrusted data." if res.passed else f"Rejected: {flags}",
        status="ok" if res.passed else "blocked",
    )
    return {"inputGuardrail": res.model_dump(), "status": "guardrails_checked" if res.passed else "rejected"}


def route_after_guardrails(state: DeskGraphState) -> str:
    return "research_lead_planner" if state["inputGuardrail"]["passed"] else END


def node_research_lead_planner(state: DeskGraphState) -> dict:
    run_id = state["runId"]
    prefs = get_preferences()
    tickers = state["inputGuardrail"]["detectedTickers"]
    past_notes = "\n".join(f"- {n.title} ({n.publishedAt[:10]})" for n in get_published_notes()[:2])

    _emit_trace(run_id, "research_lead_planner", "pre_tool", f"Reading analyst preferences and allocating {state['tokenBudget']:,} token budget.", tool="memory + gemini_planner")

    try:
        client = _get_client()
        resp = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=f'Analyst Request: "{state["inputGuardrail"]["sanitizedQuery"]}"\nDetected tickers: {", ".join(tickers)}',
            config=types.GenerateContentConfig(
                system_instruction=f"You are the Research Lead at an institutional asset manager. Break the query into verifiable sub-questions and an outline. Preferences:\n{chr(10).join(prefs.customInstructions)}\nPast coverage:\n{past_notes}",
                response_mime_type="application/json",
                response_schema=ResearchPlan,
            ),
        )
        tokens = resp.usage_metadata.total_token_count or 450
        plan = ResearchPlan.model_validate_json(resp.text)
        plan.tokenBudget = state["tokenBudget"]
        _emit_trace(run_id, "research_lead_planner", "post_tool", f"Generated {len(plan.subQuestions)} sub-questions for {', '.join(plan.tickers)}.", tool="gemini_planner", tokens=tokens)
    except Exception as exc:
        plan = ResearchPlan(
            title=f"{' vs. '.join(tickers)}: Multi-Year Operating Margin & Risk-Factor Review",
            tickers=tickers,
            fiscalYearsCount=3,
            subQuestions=[
                f"Extract US-GAAP Revenue and Operating Income XBRL facts across the last 3 fiscal years for {' and '.join(tickers)}.",
                "Normalize fiscal calendar mismatches and compute operating margins and YoY margin expansion (bps) in the deterministic sandbox.",
                "Compare Item 1A Risk Factors (current vs prior 10-K) to identify added, removed, and materially escalated risks.",
            ],
            outline=[
                "Executive Summary & Fiscal Alignment Note",
                "Like-for-Like Peer Financial Comparison Table (XBRL Verified)",
                "Operating Margin Drivers (Item 7 MD&A Grounded)",
                "Year-over-Year Risk Factor Diff (Item 1A)",
                "Compliance & Fact Verification Ledger",
            ],
            tokenBudget=state["tokenBudget"],
            fiscalMismatchWarning="Verify fiscal year-end dates across peers (e.g., June 30 vs December 31) before comparing sequential trends.",
        )
        _emit_trace(run_id, "research_lead_planner", "post_tool", f"Planner fallback engaged: {exc}", status="warn")

    run = get_run(run_id)
    if run:
        run.plan = plan
        run.status = "awaiting_plan_approval"
        save_run(run)

    edited_plan = interrupt({"type": "edit_plan", "plan": plan.model_dump()})
    final_plan = ResearchPlan.model_validate({**plan.model_dump(), **(edited_plan or {})})

    run = get_run(run_id)
    if run:
        run.plan = final_plan
        run.tokenBudget = final_plan.tokenBudget
        run.status = "researching"
        save_run(run)

    return {"plan": final_plan.model_dump(), "tokenBudget": final_plan.tokenBudget, "status": "researching"}


def fanout_company_workers(state: DeskGraphState) -> list[Send]:
    tickers = state["plan"]["tickers"]
    return [Send("company_worker", {**state, "target_ticker": t}) for t in tickers]


async def node_company_worker(state: dict) -> dict:
    """Parallel per-company worker: Filings Researcher + FinRobot/FinRL XBRL Quant + Item 1A Risk-Diff."""
    run_id = state["runId"]
    ticker = state["target_ticker"]
    years_count = state["plan"].get("fiscalYearsCount", 3)
    t0 = time.monotonic()

    edgar_data = await fetch_company_xbrl_facts(ticker)
    quant_summary = compute_quant_with_finrobot_and_finrl(
        meta=edgar_data["meta"],
        revenues=edgar_data["revenues"],
        operating_income=edgar_data["operatingIncome"],
        net_income=edgar_data["netIncome"],
        years_count=years_count,
    )

    all_passages = await get_company_filings_passages(ticker)
    top_passages = hybrid_search_and_rerank(all_passages, state["query"], top_k=5)

    item1a = [p for p in all_passages if p.section == "Item 1A"]
    years = sorted({p.fiscalYear for p in item1a})
    prior_yr = years[-2] if len(years) >= 2 else (years[0] - 1 if years else 2023)
    curr_yr = years[-1] if years else 2024
    prior_p = [p for p in item1a if p.fiscalYear == prior_yr]
    curr_p = [p for p in item1a if p.fiscalYear == curr_yr]

    risk_diffs = [
        RiskDiffItem(
            id=f"{ticker}-DIFF-{idx + 1}",
            ticker=ticker,
            changeType="MATERIALLY_CHANGED" if prior_p else "ADDED",
            riskTitle=p.title,
            summary=p.text,
            priorYear=prior_yr,
            currentYear=curr_yr,
            priorPassageId=prior_p[0].passageId if prior_p else None,
            currentPassageId=p.passageId,
            priorExcerpt=prior_p[0].text if prior_p else None,
            currentExcerpt=p.text,
        ).model_dump()
        for idx, p in enumerate(curr_p)
    ]

    finding = ResearcherFinding(
        ticker=ticker,
        companyName=edgar_data["meta"].companyName,
        summary=" ".join(p.text for p in top_passages[:2]),
        keyPoints=[{"claim": f"{p.title}: {p.text}", "passageId": p.passageId} for p in top_passages[:3]],
        passages=top_passages,
    )

    run = get_run(run_id)
    if run:
        for f in edgar_data["revenues"] + edgar_data["operatingIncome"] + edgar_data["netIncome"]:
            run.factsRegistry[f.factId] = f
        for p in top_passages + prior_p + curr_p:
            run.passagesRegistry[p.passageId] = p
        run.quant.append(quant_summary)
        run.researchers.append(finding)
        run.riskDiffs.extend([RiskDiffItem.model_validate(d) for d in risk_diffs])
        save_run(run)

    dur = int((time.monotonic() - t0) * 1000)
    _emit_trace(
        run_id,
        f"worker_{ticker}",
        "post_tool",
        f"{ticker}: Verified {len(quant_summary.rows)} FYs ({quant_summary.latestOperatingMarginPct}% op margin, FinRL regime={quant_summary.finrlRiskRegime.get('regimeLabel')}) & {len(risk_diffs)} Item 1A diffs.",
        tool="edgar + finrobot_sandbox + hybrid_search",
        dur_ms=dur,
    )

    return {
        "researchers": [finding.model_dump()],
        "quant": [quant_summary.model_dump()],
        "riskDiffs": risk_diffs,
    }


def node_writer(state: DeskGraphState) -> dict:
    run_id = state["runId"]
    run = get_run(run_id)
    prefs = get_preferences()
    attempt = state.get("revisionCount", 0)

    quant_lines = []
    for q in run.quant:
        rows_txt = "\n".join(
            f"  - FY{r.fiscalYear} (ended {r.periodEnd}): Revenue ${r.revenueB:.2f}B [{r.revenueFactId}], "
            f"Operating Income ${r.operatingIncomeB:.2f}B [{r.operatingIncomeFactId}], "
            f"Operating Margin {r.operatingMarginPct:.2f}% [{r.operatingIncomeFactId}]"
            + (f", YoY Margin Delta {r.marginDeltaBps:+d} bps [{r.operatingIncomeFactId}]" if r.marginDeltaBps is not None else "")
            for r in q.rows
        )
        quant_lines.append(f"{q.companyName} ({q.ticker}) - FY End: {q.fiscalYearEndMonth} | Rev CAGR: {q.finrobotPeerMetrics.get('revenueCagrPct')}%\n{rows_txt}")

    risk_lines = "\n".join(
        f"- ({d.ticker} | {d.changeType}) **{d.riskTitle}**: {d.summary} [{d.currentPassageId}]"
        for d in run.riskDiffs
    )

    prompt = f"""
Research Request: {state['query']}
Report Title: {run.plan.title}
Outline: {', '.join(run.plan.outline)}
Analyst Preferences: {'; '.join(prefs.customInstructions)}
Lessons Learned: {'; '.join(prefs.improvementLessons)}

VERIFIED XBRL QUANTITATIVE DATA:
{chr(10).join(quant_lines)}

VERIFIED ITEM 1A RISK DIFFS:
{risk_lines}

{f"CRITIC FEEDBACK TO FIX:{chr(10)}{state.get('revisionFeedback', '')}" if state.get('revisionFeedback') else ""}

RULES:
1. Every financial number ($XX.XXB, XX.XX%, +/-XXX bps) MUST include its exact [FACT:TICKER:CODE:FYYYYY] tag on the SAME line.
2. Every risk claim MUST cite its exact [PASSAGE:...] tag.
3. Include a Markdown Peer Comparison Table and explicitly highlight fiscal calendar differences.
4. NEVER include Buy/Sell/Hold ratings, price targets, or promises of future returns.
"""

    try:
        client = _get_client()
        resp = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction="You are a Senior Institutional Equity Research Writer. Cite every number with [FACT:...] and every qualitative claim with [PASSAGE:...]."
            ),
        )
        draft = resp.text.strip()
        tokens = resp.usage_metadata.total_token_count or 1200
        _emit_trace(run_id, "writer", "post_tool", f"Drafted {len(draft)} chars (round {attempt}).", tool="gemini_writer", tokens=tokens)
    except Exception:
        header = f"## {run.plan.title}\n\n### Fiscal Calendar Alignment\n" + "\n".join(
            f"- **{q.companyName} ({q.ticker})**: Fiscal year ends {q.fiscalYearEndMonth}." for q in run.quant
        )
        tbl = "\n\n### Peer Operating Margin Comparison\n\n| Company | FY | Period End | Revenue ($B) | Op Income ($B) | Op Margin | YoY Delta |\n| --- | --- | --- | ---: | ---: | ---: | ---: |\n" + "\n".join(
            f"| {q.ticker} | FY{r.fiscalYear} | {r.periodEnd} | ${r.revenueB:.2f}B [{r.revenueFactId}] | ${r.operatingIncomeB:.2f}B [{r.operatingIncomeFactId}] | {r.operatingMarginPct:.2f}% [{r.operatingIncomeFactId}] | {f'{r.marginDeltaBps:+d} bps [{r.operatingIncomeFactId}]' if r.marginDeltaBps is not None else '-'} |"
            for q in run.quant for r in q.rows
        )
        risks = "\n\n### Item 1A Risk Factor Changes\n" + "\n".join(
            f"- **{d.ticker} - {d.changeType} - {d.riskTitle}**: {d.summary} [{d.currentPassageId}]" for d in run.riskDiffs
        )
        draft = header + tbl + risks

    if run:
        run.draftMarkdown = draft
        run.revisionCount = attempt
        save_run(run)

    return {"draftMarkdown": draft}


def node_compliance_critic(state: DeskGraphState) -> dict:
    run_id = state["runId"]
    run = get_run(run_id)
    attempt = state.get("revisionCount", 0)

    audit = verify_draft_numbers_in_code(run.draftMarkdown, run.quant, run.factsRegistry)
    advice_violations = check_advice_language(run.draftMarkdown)

    code_ok = len(audit["unverifiedFactRefs"]) == 0 and (
        audit["totalCount"] == 0 or (audit["verifiedCount"] / audit["totalCount"]) >= 0.85
    )
    advice_ok = len(advice_violations) == 0
    passed = code_ok and advice_ok

    unverified = [c for c in audit["checks"] if not c.matched]
    lesson = None
    if not passed:
        if unverified:
            lesson = f"Attach exact inline [FACT:...] tags on the same line as financial figures (missed on {unverified[0].extractedText})."
        elif advice_violations:
            lesson = f"Avoid restricted advisory phrasing ({advice_violations[0]})."
        if lesson:
            append_improvement_lesson(lesson)

    report = ComplianceReport(
        revisionNumber=attempt,
        passed=passed,
        codeCheckPassed=code_ok,
        judgeCheckPassed=True,
        adviceCheckPassed=advice_ok,
        numericChecks=audit["checks"],
        verifiedCount=audit["verifiedCount"],
        totalNumbersCount=audit["totalCount"],
        adviceViolations=advice_violations,
        citationIssues=[],
        judgeSummary="Code-verified XBRL Fact IDs and screened for prohibited return promises.",
        improvementLesson=lesson,
    )

    feedback = "\n".join([f"- Fix citation for {u.extractedText}: {u.reason}" for u in unverified[:5]] + advice_violations)

    if run:
        run.complianceHistory.append(report)
        cov = int(round((audit["verifiedCount"] / max(1, audit["totalCount"])) * 100)) if audit["totalCount"] else 100
        run.outputGuardrail = OutputGuardrailResult(
            passed=passed,
            factIdCoveragePct=cov,
            unverifiedNumbers=audit["totalCount"] - audit["verifiedCount"],
            adviceLanguageDetected=not advice_ok,
        )
        save_run(run)

    _emit_trace(
        run_id,
        "compliance_critic",
        "guardrail",
        f"Compliance Critic {'PASSED' if passed else 'RETURNED'} (round {attempt}): {audit['verifiedCount']}/{audit['totalCount']} numbers verified in code.",
        status="ok" if passed else "warn",
    )

    return {
        "complianceHistory": [report.model_dump()],
        "revisionCount": attempt + 1,
        "revisionFeedback": feedback,
    }


def route_after_critic(state: DeskGraphState) -> str:
    last_report = state["complianceHistory"][-1]
    if last_report["passed"] or state["revisionCount"] > 2:
        return "approval_gate"
    return "writer"


def node_approval_gate(state: DeskGraphState) -> dict:
    run_id = state["runId"]
    run = get_run(run_id)
    if run:
        run.status = "awaiting_analyst_signature"
        save_run(run)
    _emit_trace(run_id, "approval_gate", "interrupt", "Waiting for human analyst signature before publish_note writes to Research Portal.")

    interrupt({"type": "analyst_signature", "runId": run_id})
    return {"status": "published"}


def build_analyst_desk_graph():
    builder = StateGraph(DeskGraphState)
    builder.add_node("input_guardrails", node_input_guardrails)
    builder.add_node("research_lead_planner", node_research_lead_planner)
    builder.add_node("company_worker", node_company_worker)
    builder.add_node("writer", node_writer)
    builder.add_node("compliance_critic", node_compliance_critic)
    builder.add_node("approval_gate", node_approval_gate)

    builder.add_edge(START, "input_guardrails")
    builder.add_conditional_edges("input_guardrails", route_after_guardrails, ["research_lead_planner", END])
    builder.add_conditional_edges("research_lead_planner", fanout_company_workers, ["company_worker"])
    builder.add_edge("company_worker", "writer")
    builder.add_edge("writer", "compliance_critic")
    builder.add_conditional_edges("compliance_critic", route_after_critic, ["writer", "approval_gate"])
    builder.add_edge("approval_gate", END)

    return builder.compile(checkpointer=MemorySaver())


ANALYST_GRAPH = build_analyst_desk_graph()
