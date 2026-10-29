"""Deterministic query understanding.

This first-stage classifier is deliberately explainable and does not require a
model download. It is a baseline that can later be replaced or augmented by a
trained classifier through the same interface.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from collections import Counter

from app.models import QueryUnderstanding


def _model_prediction(text: str, task: str) -> tuple[str | None, str]:
    """Use a trained local model when configured, with explicit engine labels."""
    provider = os.getenv(f"{task.upper()}_PROVIDER", "auto").lower()
    root = Path(__file__).resolve().parents[3]
    transformer_default = root / "data" / "ml" / task / "transformer_model"
    sklearn_default = root / "data" / "ml" / task / ("intent_model.pkl" if task == "intent" else "ood_model.pkl")
    configured = os.getenv(f"{task.upper()}_MODEL", str(transformer_default))
    if provider in {"deterministic", "keywords", "none"}:
        return None, "deterministic_keywords"
    if provider in {"sklearn", "auto"} and (provider == "sklearn" or not Path(configured).exists()) and sklearn_default.exists():
        try:
            import pickle
            with sklearn_default.open("rb") as handle:
                model = pickle.load(handle)
            prediction = str(model.predict([text])[0])
            if task == "ood":
                prediction = "OUT_OF_DOMAIN" if prediction == "OUT_OF_DOMAIN" else "IN_DOMAIN"
            return prediction, f"sklearn_{task}_baseline"
        except Exception as exc:
            if provider == "sklearn":
                return None, f"deterministic_fallback_after_sklearn_unavailable:{type(exc).__name__}"
    if provider not in {"transformer", "auto"} or (provider == "auto" and not Path(configured).exists()):
        return None, "deterministic_keywords_auto_unavailable"
    try:
        from ml.models.inference import intent_classifier, ood_classifier
        predictor = intent_classifier(configured) if task == "intent" else ood_classifier(configured)
        prediction = predictor.predict(text)
        return prediction.label, f"transformer:{prediction.model}"
    except Exception as exc:
        if provider == "transformer":
            return None, f"deterministic_fallback_after_transformer_unavailable:{type(exc).__name__}"
        return None, "deterministic_keywords_auto_failed"


INTENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "vulnerability": ("cve", "vulnerability", "cvss", "patch", "exploit", "affected version", "kev"),
    "threat_intelligence": ("threat actor", "apt", "campaign", "malware", "ransomware", "ioc", "indicator", "ttp", "mitre", "att&ck", "technique", "tactic"),
    "malware": ("malware", "trojan", "worm", "ransomware", "backdoor", "payload"),
    "network_security": ("network", "firewall", "ids", "ips", "dns", "packet", "segmentation"),
    "web_security": ("web", "xss", "csrf", "ssrf", "sql injection", "owasp", "web application"),
    "cloud_security": ("cloud", "kubernetes", "container", "iam", "s3", "azure", "aws", "gcp"),
    "email_security": ("phishing", "spear phishing", "email security", "business email compromise", "smishing", "vishing", "malicious link", "email spoofing"),
    "social_engineering": ("social engineering", "credential harvesting", "credential theft", "pretexting", "tailgating"),
    "cryptography": ("cryptography", "encryption", "cipher", "hash", "tls", "rsa", "key exchange"),
    "digital_forensics": ("forensics", "disk image", "memory dump", "artifact", "timeline analysis"),
    "incident_response": ("incident", "breach", "containment", "eradication", "playbook", "alert"),
    "ai_security": ("prompt injection", "llm", "machine learning security", "model poisoning", "adversarial"),
    "threat_hunting": ("threat hunting", "hunt", "suspicious", "anomaly", "detection rule", "sigma"),
    "security_tools": ("nmap", "wireshark", "snort", "packet capture", "network scanner", "security tool"),
    "research_literature": ("paper", "research", "literature", "dataset", "methodology", "research gap", "study"),
    "compliance": ("compliance", "nist", "iso 27001", "control", "audit", "gdpr", "policy"),
    "general_cybersecurity": ("cybersecurity", "security", "attack", "defense", "mitigation", "authentication", "access control"),
}

DOMAIN_ALIASES = {
    "vulnerability": "vulnerability management",
    "threat_intelligence": "threat intelligence",
    "research_literature": "cybersecurity research",
    "security_tools": "cybersecurity tools",
    "ai_security": "AI security",
    "general_cybersecurity": "cybersecurity",
}

SECURITY_TERMS = set(word for values in INTENT_KEYWORDS.values() for phrase in values for word in phrase.split())
TEMPORAL_TERMS = ("current", "latest", "today", "historical", "in 2024", "in 2023", "timeline", "changed", "version", "superseded", "as of")
MULTIHOP_TERMS = ("and then", "related to", "map", "associated", "what mitigation", "which mitigation", "which technique", "chain", "relationship")


def _detect_language(text: str) -> str:
    if re.search(r"[\u0900-\u097F]", text):
        return "hi"
    hinglish = {"kya", "kaise", "hai", "ke", "liye", "batao", "samjhao"}
    if len(hinglish.intersection(set(re.findall(r"[a-z]+", text.lower())))) >= 2:
        return "hinglish"
    return "en"


def _entities(text: str) -> list[dict[str, str]]:
    entities: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def add(kind: str, value: str) -> None:
        key = (kind, value.lower())
        if key not in seen:
            seen.add(key)
            entities.append({"type": kind, "value": value})

    for value in re.findall(r"\bCVE-\d{4}-\d{4,7}\b", text, flags=re.IGNORECASE):
        add("cve", value.upper())
    for value in re.findall(r"\b(?:T|S)\d{4}(?:\.\d{3})?\b", text, flags=re.IGNORECASE):
        add("attack_technique", value.upper())
    for value in re.findall(r"\b(?:[0-9a-f]{32}|[0-9a-f]{40}|[0-9a-f]{64})\b", text, flags=re.IGNORECASE):
        add("hash", value)
    for value in re.findall(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", text):
        add("ipv4", value)
    for value in re.findall(r"\b[A-Za-z0-9.-]+\.(?:com|org|net|io|gov|in|edu)\b", text, flags=re.IGNORECASE):
        add("domain", value)
    for value in re.findall(r"\b(?:CWE|CAPEC)-\d+\b", text, flags=re.IGNORECASE):
        add("weakness_or_pattern", value.upper())
    return entities


def understand_query(query: str) -> QueryUnderstanding:
    text = " ".join(query.strip().split())
    lowered = text.lower()
    scores = Counter()
    for intent_name, phrases in INTENT_KEYWORDS.items():
        for phrase in phrases:
            if phrase in lowered:
                scores[intent_name] += 1 if " " in phrase else 2
    keyword_intent = scores.most_common(1)[0][0] if scores else "out_of_domain"
    # An explicit product/tool name should anchor tool questions even when a
    # nearby generic word (for example, "network") matches another intent.
    if re.search(r"\b(?:nmap|wireshark|snort)\b", lowered):
        keyword_intent = "security_tools"
    predicted_intent, intent_engine = _model_prediction(text, "intent")
    auto_intent = os.getenv("INTENT_PROVIDER", "auto").lower() == "auto"
    if predicted_intent in INTENT_KEYWORDS and (not auto_intent or keyword_intent == "out_of_domain"):
        intent = predicted_intent
    else:
        intent = keyword_intent
        if predicted_intent and predicted_intent != keyword_intent:
            intent_engine = f"{intent_engine}:keyword_selected"
    predicted_ood, ood_engine = _model_prediction(text, "ood")
    entities = _entities(text)
    keyword_in_domain = bool(scores) or bool(entities)
    if predicted_ood == "OUT_OF_DOMAIN":
        # A small bootstrap classifier must not override an explicit security
        # identifier/keyword signal in automatic mode. Explicit provider modes
        # retain model authority and expose the engine in the response.
        is_in_domain = keyword_in_domain if ood_engine.startswith("sklearn_") and os.getenv("OOD_PROVIDER", "auto").lower() == "auto" else False
    elif predicted_ood == "IN_DOMAIN":
        is_in_domain = True
    else:
        is_in_domain = keyword_in_domain
    reason = "" if is_in_domain else "No cybersecurity vocabulary or recognizable security identifier was found."
    if predicted_ood == "OUT_OF_DOMAIN" and not is_in_domain:
        reason = "The configured OOD model classified the query as outside the supported cybersecurity domain."
    if not is_in_domain:
        intent = "out_of_domain"
        domain = "out_of_domain"
    else:
        domain = DOMAIN_ALIASES.get(intent, intent.replace("_", " "))

    word_count = len(text.split())
    complexity = "simple" if word_count <= 10 else "moderate" if word_count <= 28 else "complex"
    if len(entities) >= 2 or any(term in lowered for term in MULTIHOP_TERMS):
        complexity = "complex"
    query_type = "identifier_lookup" if entities else "explanation"
    if any(term in lowered for term in ("compare", "difference", "versus", "vs")):
        query_type = "comparison"
    elif any(term in lowered for term in ("how do i", "how can", "steps", "recommend")):
        query_type = "recommendation"
    elif any(term in lowered for term in ("research", "paper", "literature", "gap")):
        query_type = "research"

    terms = [word for word in re.findall(r"[a-z0-9-]+", lowered) if len(word) > 2]
    # Keep the user's original terms as the retrieval anchor. Generic additions
    # such as "cybersecurity evidence" made unrelated trusted documents score as
    # matches for narrow questions (for example, ransomware-specific questions).
    expansions = [text]
    subqueries = [text]
    for splitter in (" and ", ";", " then "):
        if splitter in lowered:
            subqueries = [part.strip() for part in re.split(re.escape(splitter), text, flags=re.IGNORECASE) if part.strip()]
            break
    if len(subqueries) == 1 and len(terms) > 12:
        subqueries = [text, f"evidence and authoritative sources for: {text}"]

    return QueryUnderstanding(
        raw_query=text,
        intent=intent,
        domain=domain,
        complexity=complexity,
        language=_detect_language(text),
        entities=entities,
        query_type=query_type,
        requires_temporal_reasoning=any(term in lowered for term in TEMPORAL_TERMS),
        requires_multihop_reasoning=len(entities) > 1 or any(term in lowered for term in MULTIHOP_TERMS),
        is_in_domain=is_in_domain,
        out_of_domain_reason=reason,
        classification_engine=intent_engine,
        ood_engine=ood_engine,
        expanded_queries=list(dict.fromkeys(expansions)),
        subqueries=subqueries,
    )
