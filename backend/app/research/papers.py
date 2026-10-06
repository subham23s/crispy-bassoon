"""Evidence-preserving research-paper extraction and comparison.

Extraction is intentionally conservative. Every populated field carries the
source section/page spans where possible; missing fields are explicit rather
than inferred from unrelated text.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any


PAPER_FIELDS = (
    "abstract", "problem_statement", "methodology", "architecture", "dataset",
    "preprocessing", "features", "model", "hyperparameters", "training_procedure",
    "evaluation_metrics", "results", "limitations", "future_work", "references",
)


@dataclass
class PaperRecord:
    title: str
    authors: list[str] = field(default_factory=list)
    year: str = ""
    abstract: str = ""
    problem_statement: str = ""
    methodology: str = ""
    architecture: str = ""
    dataset: str = ""
    preprocessing: str = ""
    features: str = ""
    model: str = ""
    hyperparameters: str = ""
    training_procedure: str = ""
    evaluation_metrics: list[str] = field(default_factory=list)
    results: str = ""
    limitations: str = ""
    future_work: str = ""
    references: list[str] = field(default_factory=list)
    field_provenance: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    missing_fields: list[str] = field(default_factory=list)
    extraction_notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


SECTION_ALIASES = {
    "abstract": "abstract",
    "introduction": "problem_statement",
    "background": "problem_statement",
    "problem statement": "problem_statement",
    "problem formulation": "problem_statement",
    "method": "methodology",
    "methods": "methodology",
    "methodology": "methodology",
    "architecture": "architecture",
    "system architecture": "architecture",
    "dataset": "dataset",
    "datasets": "dataset",
    "data": "dataset",
    "data collection": "dataset",
    "preprocessing": "preprocessing",
    "data preprocessing": "preprocessing",
    "features": "features",
    "feature engineering": "features",
    "model": "model",
    "models": "model",
    "algorithm": "model",
    "hyperparameters": "hyperparameters",
    "parameter settings": "hyperparameters",
    "training": "training_procedure",
    "training procedure": "training_procedure",
    "experimental setup": "training_procedure",
    "evaluation": "evaluation_metrics",
    "evaluation metrics": "evaluation_metrics",
    "metrics": "evaluation_metrics",
    "results": "results",
    "experiments": "results",
    "limitations": "limitations",
    "threats to validity": "limitations",
    "future work": "future_work",
    "conclusion and future work": "future_work",
    "references": "references",
    "bibliography": "references",
}


def _heading(line: str) -> str:
    value = line.strip()
    value = re.sub(r"^#{1,6}\s*", "", value)
    value = re.sub(r"^\d+(?:\.\d+)*[.)]?\s+", "", value)
    value = re.sub(r"[*_`]+", "", value)
    return re.sub(r"\s+", " ", value).strip().lower().rstrip(":")


def _page_number(line: str) -> int | None:
    match = re.match(r"\s*\[Page\s+(\d+)\]", line, flags=re.IGNORECASE)
    return int(match.group(1)) if match else None


def _section_blocks(text: str) -> dict[str, tuple[str, list[dict[str, Any]]]]:
    lines = text.splitlines()
    blocks: dict[str, list[str]] = {}
    provenance: dict[str, list[dict[str, Any]]] = {}
    current: str | None = None
    current_page: int | None = None
    for index, raw in enumerate(lines, start=1):
        page = _page_number(raw)
        if page is not None:
            current_page = page
            if current:
                provenance.setdefault(current, []).append({"line_start": index, "page": current_page, "section": current})
            continue
        normalized = _heading(raw)
        if normalized in SECTION_ALIASES:
            current = SECTION_ALIASES[normalized]
            blocks.setdefault(current, [])
            provenance.setdefault(current, []).append({"line_start": index, "page": current_page, "section": normalized})
            continue
        if current:
            blocks[current].append(raw.strip())
            provenance[current][-1]["line_end"] = index
    return {key: ("\n".join(value).strip(), provenance.get(key, [])) for key, value in blocks.items()}


def extract_paper(text: str, filename: str = "uploaded-paper") -> PaperRecord:
    lines = [line.strip() for line in text.splitlines()]
    non_empty = [line for line in lines if line and not _page_number(line)]
    title = non_empty[0][:300] if non_empty else filename
    header = []
    for line in non_empty[:12]:
        if _heading(line) in SECTION_ALIASES:
            break
        header.append(line)
    year_match = re.search(r"(?im)^(?:(?:published|year|date)\s*:\s*)?((?:19|20)\d{2})(?:\s|$)", "\n".join(header))
    authors: list[str] = []
    if len(header) > 1 and "," in header[1] and len(header[1]) < 250:
        authors = [part.strip() for part in re.sub(r"(?i)^authors?:\s*", "", header[1]).split(",") if part.strip()]
    blocks = _section_blocks(text)
    values = {field: block[0] for field, block in blocks.items()}
    provenance = {field: block[1] for field, block in blocks.items()}
    metric_text = "\n".join(values.get(key, "") for key in ("evaluation_metrics", "results"))
    metrics = sorted(set(re.findall(r"\b(?:accuracy|precision|recall|f1(?:-score)?|auc|roc-auc|mcc|mae|rmse|latency|far|fpr|tpr)\b", metric_text, re.IGNORECASE)))
    if metrics:
        provenance["evaluation_metrics"] = [span for key in ("evaluation_metrics", "results") for span in blocks.get(key, ("", []))[1]]
    notes: list[str] = []
    if not blocks:
        notes.append("No recognizable section headings were found; only title/author/year metadata was extracted.")
    if not authors:
        notes.append("Authors were not confidently extracted from the available text.")
    missing = [field for field in PAPER_FIELDS if not values.get(field)]
    notes.append("Fields marked missing were not found in recognizable sections; no unsupported values were inferred.")
    references = [line.lstrip("-• ").strip() for line in text.splitlines() if line.strip() and (values.get("references") and line.strip() in values["references"])]
    # A reference section often has one citation per line; use its raw lines if available.
    if values.get("references"):
        references = [part.strip() for part in re.split(r"\s{2,}|\n", values["references"]) if part.strip()]
    return PaperRecord(
        title=title,
        authors=authors,
        year=year_match.group(1) if year_match else "",
        abstract=values.get("abstract", ""),
        problem_statement=values.get("problem_statement", ""),
        methodology=values.get("methodology", ""),
        architecture=values.get("architecture", ""),
        dataset=values.get("dataset", ""),
        preprocessing=values.get("preprocessing", ""),
        features=values.get("features", ""),
        model=values.get("model", ""),
        hyperparameters=values.get("hyperparameters", ""),
        training_procedure=values.get("training_procedure", ""),
        evaluation_metrics=metrics or ([values.get("evaluation_metrics", "")] if values.get("evaluation_metrics") else []),
        results=values.get("results", ""),
        limitations=values.get("limitations", ""),
        future_work=values.get("future_work", ""),
        references=references,
        field_provenance=provenance,
        missing_fields=missing,
        extraction_notes=notes,
    )


def compare_papers(papers: list[PaperRecord]) -> dict[str, Any]:
    rows = []
    for paper in papers:
        rows.append({"title": paper.title, "year": paper.year, "dataset": paper.dataset, "preprocessing": paper.preprocessing, "features": paper.features, "model": paper.model, "hyperparameters": paper.hyperparameters, "metrics": paper.evaluation_metrics, "results": paper.results, "limitations": paper.limitations, "missing_fields": paper.missing_fields, "field_provenance": paper.field_provenance})
    repeated_datasets: dict[str, int] = {}
    repeated_models: dict[str, int] = {}
    for paper in papers:
        for value, target in ((paper.dataset, repeated_datasets), (paper.model, repeated_models)):
            key = value.strip().lower()
            if key:
                target[key] = target.get(key, 0) + 1
    return {
        "papers": rows,
        "repeated_datasets": [{"dataset": key, "paper_count": count} for key, count in repeated_datasets.items() if count > 1],
        "repeated_models": [{"model": key, "paper_count": count} for key, count in repeated_models.items() if count > 1],
        "limitations": ["Comparison is only as complete as the extracted paper sections; inspect original papers before drawing conclusions."],
    }
