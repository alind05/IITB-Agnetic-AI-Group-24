from __future__ import annotations
from typing import Any, Literal, Optional
from pydantic import BaseModel, Field

RunStatus = Literal[
    "idle",
    "guardrails_checked",
    "awaiting_plan_approval",
    "researching",
    "writing_and_critiquing",
    "awaiting_analyst_signature",
    "published",
    "rejected",
    "error",
]


class InputGuardrailResult(BaseModel):
    passed: bool
    scopeCategory: str
    sanitizedQuery: str
    detectedTickers: list[str]
    flags: list[str]
    webTextMarkedAsData: bool = True


class ResearchPlan(BaseModel):
    title: str
    tickers: list[str]
    fiscalYearsCount: int = 3
    subQuestions: list[str]
    outline: list[str]
    tokenBudget: int = 28000
    fiscalMismatchWarning: str


class XbrlFact(BaseModel):
    factId: str
    ticker: str
    companyName: str
    cik: str
    concept: str
    label: str
    fiscalYear: int
    fiscalEnd: str
    periodStart: str
    periodEnd: str
    value: float
    unit: str = "USD"
    valueBillions: float
    accession: str
    filedDate: str
    sourceType: Literal["live_edgar", "cached_edgar"]


class QuantYearRow(BaseModel):
    fiscalYear: int
    periodEnd: str
    revenueB: float
    revenueFactId: str
    operatingIncomeB: float
    operatingIncomeFactId: str
    netIncomeB: Optional[float] = None
    netIncomeFactId: Optional[str] = None
    operatingMarginPct: float
    netMarginPct: Optional[float] = None
    yoyRevenueGrowthPct: Optional[float] = None
    marginDeltaBps: Optional[int] = None


class QuantCompanySummary(BaseModel):
    ticker: str
    companyName: str
    cik: str
    fiscalYearEndMonth: str
    sourceType: Literal["live_edgar", "cached_edgar"]
    rows: list[QuantYearRow]
    threeYearMarginDeltaBps: Optional[int] = None
    latestOperatingMarginPct: Optional[float] = None
    # FinRobot & FinRL quantitative extensions (research-only diagnostics)
    finrobotPeerMetrics: dict[str, Any] = Field(default_factory=dict)
    finrlRiskRegime: dict[str, Any] = Field(default_factory=dict)
    sandboxCodeExecuted: str


class FilingPassage(BaseModel):
    passageId: str
    ticker: str
    fiscalYear: int
    section: Literal["Item 1A", "Item 7"]
    title: str
    text: str
    score: Optional[float] = None
    sourceLabel: str


class ResearcherFinding(BaseModel):
    ticker: str
    companyName: str
    summary: str
    keyPoints: list[dict[str, str]]
    passages: list[FilingPassage]


class RiskDiffItem(BaseModel):
    id: str
    ticker: str
    changeType: Literal["ADDED", "REMOVED", "MATERIALLY_CHANGED"]
    riskTitle: str
    summary: str
    priorYear: int
    currentYear: int
    priorPassageId: Optional[str] = None
    currentPassageId: Optional[str] = None
    priorExcerpt: Optional[str] = None
    currentExcerpt: Optional[str] = None


class NumericCheckResult(BaseModel):
    extractedText: str
    numericValue: float
    citedFactId: Optional[str] = None
    expectedValue: Optional[float] = None
    matched: bool
    reason: str


class ComplianceReport(BaseModel):
    revisionNumber: int
    passed: bool
    codeCheckPassed: bool
    judgeCheckPassed: bool
    adviceCheckPassed: bool
    numericChecks: list[NumericCheckResult]
    verifiedCount: int
    totalNumbersCount: int
    adviceViolations: list[str]
    citationIssues: list[str]
    judgeSummary: str
    improvementLesson: Optional[str] = None


class TraceEvent(BaseModel):
    id: str
    timestamp: str
    node: str
    hookType: Literal["graph_node", "pre_tool", "post_tool", "guardrail", "interrupt"]
    tool: Optional[str] = None
    message: str
    durationMs: Optional[int] = None
    tokensDelta: Optional[int] = None
    status: Literal["ok", "warn", "blocked"]


class CheckpointSnapshot(BaseModel):
    step: str
    timestamp: str
    tokenUsed: int
    summary: str


class OutputGuardrailResult(BaseModel):
    passed: bool
    factIdCoveragePct: int
    unverifiedNumbers: int
    adviceLanguageDetected: bool


class AnalystSignature(BaseModel):
    analystName: str
    attestation: str
    signedAt: str


class ResearchRunState(BaseModel):
    runId: str
    status: RunStatus
    query: str
    createdAt: str
    updatedAt: str
    activeNode: str
    inputGuardrail: Optional[InputGuardrailResult] = None
    plan: Optional[ResearchPlan] = None
    tokenBudget: int = 28000
    tokenUsed: int = 0
    estimatedCostUsd: float = 0.0
    elapsedMs: int = 0
    researchers: list[ResearcherFinding] = Field(default_factory=list)
    quant: list[QuantCompanySummary] = Field(default_factory=list)
    factsRegistry: dict[str, XbrlFact] = Field(default_factory=dict)
    passagesRegistry: dict[str, FilingPassage] = Field(default_factory=dict)
    riskDiffs: list[RiskDiffItem] = Field(default_factory=list)
    draftMarkdown: str = ""
    revisionCount: int = 0
    complianceHistory: list[ComplianceReport] = Field(default_factory=list)
    outputGuardrail: Optional[OutputGuardrailResult] = None
    signature: Optional[AnalystSignature] = None
    publishedNoteId: Optional[str] = None
    traces: list[TraceEvent] = Field(default_factory=list)
    checkpoints: list[CheckpointSnapshot] = Field(default_factory=list)
    errorMessage: Optional[str] = None


class PublishedNote(BaseModel):
    noteId: str
    runId: str
    title: str
    query: str
    tickers: list[str]
    analystName: str
    publishedAt: str
    markdown: str
    quant: list[QuantCompanySummary] = Field(default_factory=list)
    riskDiffs: list[RiskDiffItem] = Field(default_factory=list)
    factsRegistry: dict[str, XbrlFact] = Field(default_factory=dict)
    passagesRegistry: dict[str, FilingPassage] = Field(default_factory=dict)
    verifiedNumbersCount: int
    totalNumbersCount: int
    tokenUsed: int
    estimatedCostUsd: float
    elapsedMs: int
    revisionsUsed: int


class AnalystPreferences(BaseModel):
    analystName: str = "Equity Analyst Desk, CFA"
    alwaysIncludePeerTable: bool = True
    flagFiscalCalendarMismatches: bool = True
    requireFactIdOnEveryNumber: bool = True
    prohibitReturnPromises: bool = True
    defaultTokenBudget: int = 28000
    customInstructions: list[str] = Field(
        default_factory=lambda: [
            "Always include a like-for-like Peer Comparison Table showing revenue, operating income, and operating margin.",
            "Flag fiscal calendar mismatches (e.g., June 30 vs December 31 year-ends) before comparing YoY trends.",
        ]
    )
    improvementLessons: list[str] = Field(
        default_factory=lambda: [
            "Never state margin expansion in basis points without citing both prior-year and current-year XBRL fact IDs.",
            "Avoid forward-looking stock return promises, price targets, or buy/sell directives in institutional coverage notes.",
        ]
    )
