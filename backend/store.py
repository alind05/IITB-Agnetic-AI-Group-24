import json
from pathlib import Path
from typing import Optional
from .schemas import AnalystPreferences, PublishedNote, ResearchRunState

DATA_DIR = Path(".data")
PORTAL_FILE = DATA_DIR / "portal-notes.json"
PREFS_FILE = DATA_DIR / "analyst-preferences.json"

SEED_NOTES = [
    PublishedNote(
        noteId="NOTE-2025-MSFT-GOOGL-01",
        runId="seed-run-001",
        title="Prior Coverage Baseline: Microsoft vs. Alphabet Margin & Cloud Capex Trajectory",
        query="Baseline operating margin comparison for MSFT and GOOGL prior to FY2025 10-K cycle.",
        tickers=["MSFT", "GOOGL"],
        analystName="Equity Analyst Desk, CFA",
        publishedAt="2025-09-18T14:30:00Z",
        markdown=(
            "### Coverage Baseline Summary (Prior Note)\n\n"
            "In our September 2025 baseline note, Microsoft reported FY2024 operating margin of 44.6% "
            "on $245.12B revenue [FACT:MSFT:Revenues:FY2024], while Alphabet reported FY2024 operating margin "
            "of 32.1% on $350.02B revenue [FACT:GOOGL:Revenues:FY2024]. Key risk themes highlighted at that "
            "time centered on AI infrastructure depreciation schedules and antitrust remedies in Search distribution."
        ),
        verifiedNumbersCount=4,
        totalNumbersCount=4,
        tokenUsed=11420,
        estimatedCostUsd=0.0042,
        elapsedMs=6840,
        revisionsUsed=0,
    )
]

_RUNS_MAP: dict[str, ResearchRunState] = {}


def _ensure_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def save_run(run: ResearchRunState) -> None:
    _RUNS_MAP[run.runId] = run


def get_run(run_id: str) -> Optional[ResearchRunState]:
    return _RUNS_MAP.get(run_id)


def list_runs() -> list[ResearchRunState]:
    return sorted(_RUNS_MAP.values(), key=lambda r: r.createdAt, reverse=True)


def get_preferences() -> AnalystPreferences:
    _ensure_dir()
    if not PREFS_FILE.exists():
        prefs = AnalystPreferences()
        PREFS_FILE.write_text(prefs.model_dump_json(indent=2), encoding="utf-8")
        return prefs
    try:
        return AnalystPreferences.model_validate_json(PREFS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return AnalystPreferences()


def update_preferences(patch: dict) -> AnalystPreferences:
    _ensure_dir()
    current = get_preferences().model_dump()
    current.update({k: v for k, v in patch.items() if v is not None})
    updated = AnalystPreferences.model_validate(current)
    PREFS_FILE.write_text(updated.model_dump_json(indent=2), encoding="utf-8")
    return updated


def append_improvement_lesson(lesson: str) -> None:
    prefs = get_preferences()
    cleaned = lesson.strip()
    if not cleaned or cleaned in prefs.improvementLessons:
        return
    prefs.improvementLessons = ([cleaned] + prefs.improvementLessons)[:12]
    update_preferences(prefs.model_dump())


def get_published_notes() -> list[PublishedNote]:
    _ensure_dir()
    if not PORTAL_FILE.exists():
        PORTAL_FILE.write_text(
            json.dumps([n.model_dump() for n in SEED_NOTES], indent=2), encoding="utf-8"
        )
        return list(SEED_NOTES)
    try:
        raw = json.loads(PORTAL_FILE.read_text(encoding="utf-8"))
        return [PublishedNote.model_validate(item) for item in raw]
    except Exception:
        return list(SEED_NOTES)


def save_published_note(note: PublishedNote) -> list[PublishedNote]:
    _ensure_dir()
    existing = [n for n in get_published_notes() if n.noteId != note.noteId]
    updated = [note] + existing
    PORTAL_FILE.write_text(
        json.dumps([n.model_dump() for n in updated], indent=2), encoding="utf-8"
    )
    return updated
