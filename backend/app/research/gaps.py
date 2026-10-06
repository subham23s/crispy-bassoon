"""Evidence-grounded candidate research gap analysis."""
from __future__ import annotations

from collections import Counter
from typing import Any, Iterable

from app.research.papers import PaperRecord, compare_papers, extract_paper
from app.verification.nli_verifier import build_verifier, NLIUnavailable


def analyze_gap_candidates(documents: Iterable[Any]) -> dict[str, Any]:
    source_documents = list(documents)
    papers: list[PaperRecord] = []
    provenance: dict[str, dict[str, Any]] = {}
    for document in source_documents:
        paper = extract_paper(document.content, document.title)
        if not paper.title:
            continue
        papers.append(paper)
        provenance[paper.title] = {"document_id": document.document_id, "title": document.title, "source": document.source, "url": document.url}
    comparison = compare_papers(papers)
    limitation_counts: Counter[str] = Counter()
    limitation_evidence: dict[str, list[dict[str, Any]]] = {}
    for paper in papers:
        for limitation in [part.strip() for part in paper.limitations.replace(";", ".").split(".") if part.strip()]:
            key = " ".join(limitation.lower().split())
            limitation_counts[key] += 1
            limitation_evidence.setdefault(key, []).append(provenance.get(paper.title, {"title": paper.title}))
    contradictions: list[dict[str, Any]] = []
    verifier = build_verifier(provider="auto")
    for left_index, left in enumerate(papers):
        for right in papers[left_index + 1:]:
            if not left.results or not right.results:
                continue
            left_sentences = [part.strip() for part in left.results.split(".") if len(part.split()) >= 4]
            right_sentences = [part.strip() for part in right.results.split(".") if len(part.split()) >= 4]
            for premise in left_sentences[:8]:
                for hypothesis in right_sentences[:8]:
                    try:
                        result = verifier.verify(premise, hypothesis)
                    except Exception:
                        continue
                    if result.label == "CONTRADICTION" and result.scores.get("CONTRADICTION", 0.0) >= 0.5:
                        contradictions.append({"paper_a": provenance.get(left.title, {"title": left.title}), "paper_b": provenance.get(right.title, {"title": right.title}), "claim_a": premise, "claim_b": hypothesis, "verification": result.to_dict(), "status": "REVIEW_REQUIRED"})
                        if len(contradictions) >= 20:
                            break
                if len(contradictions) >= 20:
                    break
            if len(contradictions) >= 20:
                break
    candidates: list[dict[str, Any]] = []
    for limitation, count in limitation_counts.items():
        if count < 2:
            continue
        candidates.append({
            "title": "Candidate gap: recurring reported limitation",
            "hypothesis": f"The supplied papers repeatedly report a related limitation: {limitation}",
            "status": "CANDIDATE_HYPOTHESIS",
            "supporting_evidence": limitation_evidence[limitation],
            "basis": {"recurrence_count": count, "analysis": "same limitation language observed across extracted paper sections"},
            "warning": "This is an evidence-grounded candidate for investigation, not an established research gap.",
        })
    repeated = comparison.get("repeated_datasets", [])
    for item in repeated:
        evidence = [provenance.get(paper.title, {"title": paper.title}) for paper in papers if paper.dataset.strip().lower() == item["dataset"]]
        candidates.append({
            "title": "Candidate gap: repeated dataset setting",
            "hypothesis": f"The supplied papers may under-explore evaluation outside the repeated dataset setting '{item['dataset']}'.",
            "status": "CANDIDATE_HYPOTHESIS",
            "supporting_evidence": evidence,
            "basis": {"dataset": item["dataset"], "paper_count": item["paper_count"]},
            "warning": "The corpus is not necessarily exhaustive; inspect additional literature before asserting a gap.",
        })
    if contradictions:
        candidates.append({
            "title": "Candidate gap: conflicting reported results",
            "hypothesis": "The supplied papers contain result passages that require a controlled comparison of datasets, preprocessing, and evaluation settings.",
            "status": "CANDIDATE_HYPOTHESIS",
            "supporting_evidence": contradictions,
            "basis": {"contradiction_count": len(contradictions)},
            "warning": "The contradiction signal is an automated review aid, not proof that the papers disagree scientifically.",
        })
    return {"candidate_gaps": candidates, "paper_count": len(papers), "comparison": comparison, "contradictions": contradictions, "limitations": ["Only explicitly extracted sections and supplied documents were compared.", "Contradictions require review of the original papers and may not be detected from incomplete extraction."]}
