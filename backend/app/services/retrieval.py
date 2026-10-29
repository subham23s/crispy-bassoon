"""Explainable hybrid retrieval: lexical TF-IDF-lite + BM25-style scoring + RRF."""
from __future__ import annotations

import math
import hashlib
import re
from collections import Counter, defaultdict
from datetime import date
from typing import Iterable

from app.models import Chunk, Document, Evidence, QueryUnderstanding
from app.services.corpus import DocumentStore
from app.services.query_understanding import INTENT_KEYWORDS

STOPWORDS = {
    "the", "and", "for", "that", "this", "with", "from", "what", "which", "how", "are", "is", "was", "were", "about", "into", "can", "does", "its", "their", "have", "has", "to", "of", "in", "on", "a", "an", "or", "be", "as", "by", "it", "at", "do", "i", "me", "my", "please",
}


def tokens(text: str) -> list[str]:
    return [word for word in re.findall(r"[a-z0-9][a-z0-9_.-]*", text.lower()) if word not in STOPWORDS and len(word) > 1]


def _bm25(query_terms: list[str], document_terms: list[str], average_length: float) -> float:
    if not query_terms or not document_terms:
        return 0.0
    counts = Counter(document_terms)
    query_counts = Counter(query_terms)
    k1, b = 1.5, 0.75
    score = 0.0
    for term, qtf in query_counts.items():
        tf = counts.get(term, 0)
        if not tf:
            continue
        idf = 1.0  # IDF is applied by the corpus-level ranker.
        denominator = tf + k1 * (1 - b + b * len(document_terms) / max(average_length, 1.0))
        score += idf * ((tf * (k1 + 1)) / denominator) * min(qtf, 2)
    return score


def _tfidf_cosine(query_terms: list[str], document_terms: list[str], doc_frequency: Counter[str], total_docs: int) -> float:
    if not query_terms or not document_terms:
        return 0.0
    q = Counter(query_terms)
    d = Counter(document_terms)
    query_vector: dict[str, float] = {}
    doc_vector: dict[str, float] = {}
    for term, count in q.items():
        idf = math.log((total_docs + 1) / (doc_frequency.get(term, 0) + 1)) + 1
        query_vector[term] = (1 + math.log(count)) * idf
    for term, count in d.items():
        idf = math.log((total_docs + 1) / (doc_frequency.get(term, 0) + 1)) + 1
        doc_vector[term] = (1 + math.log(count)) * idf
    dot = sum(query_vector.get(term, 0.0) * doc_vector.get(term, 0.0) for term in query_vector)
    q_norm = math.sqrt(sum(value * value for value in query_vector.values()))
    d_norm = math.sqrt(sum(value * value for value in doc_vector.values()))
    return dot / (q_norm * d_norm) if q_norm and d_norm else 0.0


def _recency(document: Document, now: date | None = None) -> float:
    if not document.update_date and not document.publication_date:
        return 0.45
    raw = document.update_date or document.publication_date
    try:
        age = ((now or date.today()) - date.fromisoformat(raw[:10])).days
    except ValueError:
        return 0.45
    if age <= 0:
        return 1.0
    return max(0.15, min(1.0, 1.0 - age / (365 * 8)))


def _graph_relevance(query: str, chunk: Chunk) -> float:
    query_terms = set(tokens(query))
    chunk_terms = set(tokens(chunk.text))
    graph_terms = {"cve", "cwe", "capec", "attack", "technique", "mitigation", "malware", "actor", "kev", "cvss", "owasp"}
    overlap = len(query_terms.intersection(graph_terms).intersection(chunk_terms))
    return min(1.0, overlap / 3.0) if overlap else 0.0


class HybridRetriever:
    def __init__(self, store: DocumentStore) -> None:
        self.store = store
        self._index_version = -1
        self._prepared: list[tuple[Chunk, list[str]]] = []
        self._doc_frequency: Counter[str] = Counter()
        self._total_docs = 0
        self._average_length = 1.0
        self._counts: dict[str, Counter[str]] = {}
        self._norms: dict[str, float] = {}
        self._postings: dict[str, set[str]] = defaultdict(set)
        from app.services.graph import EvidenceGraph
        self.graph = EvidenceGraph()

    def _refresh_index(self) -> None:
        self.store.refresh_bootstrap()
        version = getattr(self.store, "version", 0)
        if version == self._index_version:
            return
        chunks = self.store.get_chunks()
        self._prepared = [(chunk, tokens(chunk.text)) for chunk in chunks]
        self._doc_frequency = Counter()
        for _, terms in self._prepared:
            self._doc_frequency.update(set(terms))
        self._total_docs = len(self._prepared)
        self._average_length = sum(len(terms) for _, terms in self._prepared) / max(self._total_docs, 1)
        self._counts = {chunk.chunk_id: Counter(terms) for chunk, terms in self._prepared}
        self._postings = defaultdict(set)
        self._norms = {}
        for chunk_id, counts in self._counts.items():
            for term in counts:
                self._postings[term].add(chunk_id)
            self._norms[chunk_id] = math.sqrt(sum(((1 + math.log(count)) * self._idf(term)) ** 2 for term, count in counts.items()))
        self._index_version = version

    def _idf(self, term: str) -> float:
        return math.log((self._total_docs + 1) / (self._doc_frequency.get(term, 0) + 1)) + 1

    def search(
        self,
        query: str,
        understanding: QueryUnderstanding,
        limit: int = 8,
        document_ids: set[str] | None = None,
        mode: str = "hybrid",
        *,
        source_priority: bool = True,
        temporal: bool = True,
        graph: bool = True,
        use_reranker: bool = True,
    ) -> list[Evidence]:
        if mode not in {"lexical", "dense", "hybrid"}:
            raise ValueError("retrieval mode must be lexical, dense, or hybrid")
        if limit <= 0:
            return []
        self._refresh_index()
        visible_ids = document_ids
        prepared = [(chunk, terms) for chunk, terms in self._prepared if visible_ids is None or chunk.document_id in visible_ids]
        chunks = [chunk for chunk, _ in prepared]
        if not chunks:
            return []
        doc_frequency = self._doc_frequency
        total_docs = self._total_docs
        average_length = self._average_length
        expanded = understanding.expanded_queries or [query]
        queries = [Counter(tokens(value)) for value in expanded]
        query_vectors = [{term: (1 + math.log(count)) * self._idf(term) for term, count in counts.items()} for counts in queries]
        query_norms = [math.sqrt(sum(value * value for value in vector.values())) for vector in query_vectors]
        lexical_scores: dict[str, float] = {}
        dense_scores: dict[str, float] = {}
        graph_scores: dict[str, float] = {}
        original_terms = tokens(query)
        graph_documents: dict[str, list[dict]] = {}
        if graph:
            for entity in understanding.entities[:6]:
                related = self.graph.search(entity["value"], depth=1, limit=40)
                if not related.get("edges"):
                    continue
                for node in related["nodes"]:
                    document_id = "kb-" + hashlib.sha256(f"{node.get('source', '')}:{node['id']}".encode()).hexdigest()[:24]
                    graph_documents[document_id] = [edge for edge in related["edges"] if node["id"] in (edge.get("source_entity_id"), edge.get("target_entity_id"))]
        matching_ids = set().union(*(self._postings.get(term, set()) for term in original_terms))
        prepared = [(chunk, terms) for chunk, terms in prepared if chunk.chunk_id in matching_ids or chunk.document_id in graph_documents]
        if not prepared:
            return []
        chunks = [chunk for chunk, _ in prepared]
        for chunk, terms in prepared:
            counts = self._counts[chunk.chunk_id]
            length_penalty = 1.5 * (0.25 + 0.75 * len(terms) / average_length)
            lexical_scores[chunk.chunk_id] = max(sum(math.log(1 + (total_docs - doc_frequency.get(term, 0) + 0.5) / (doc_frequency.get(term, 0) + 0.5)) * counts[term] * 2.5 / (counts[term] + length_penalty) * min(count, 2) for term, count in q.items() if counts[term]) for q in queries)
            dense_scores[chunk.chunk_id] = max((sum(value * (1 + math.log(counts[term])) * self._idf(term) for term, value in vector.items() if counts[term]) / (norm * self._norms[chunk.chunk_id]) if norm and self._norms[chunk.chunk_id] else 0.0) for vector, norm in zip(query_vectors, query_norms)) if mode != "lexical" else 0.0
            graph_scores[chunk.chunk_id] = min(1.0, len(graph_documents.get(chunk.document_id, [])) / 3.0) if graph else 0.0

        # Expanded queries improve recall, but must not pull every generic
        # authoritative document into the citation set. Keep only chunks with
        # a signal from the user's original query or a graph relationship.
        identifiers = re.findall(r"\b(?:CVE-\d{4}-\d{4,7}|CWE-\d+|CAPEC-\d+|T\d{4}(?:\.\d{3})?)\b", query, flags=re.IGNORECASE)
        identifier_candidates = [chunk for chunk, _ in prepared if any(identifier.lower() in chunk.text.lower() for identifier in identifiers)]
        lowered_query = query.lower()
        intent_terms = {
            term
            for phrase in INTENT_KEYWORDS.get(understanding.intent, ())
            if phrase in lowered_query
            for term in tokens(phrase)
        }
        source_hints = [hint for hint in ("nvd", "nist", "cisa", "mitre", "owasp", "cwe", "capec") if hint in query.lower()]
        source_candidates = []
        if source_hints:
            for chunk, _ in prepared:
                document = self.store.get_document(chunk.document_id)
                haystack = str(document.source if document else "").lower()
                if any(re.search(rf"\b{re.escape(hint)}\b", haystack) for hint in source_hints):
                    source_candidates.append(chunk)
        if identifiers:
            # Identifier lookups must match the requested identifier exactly;
            # do not substitute generic records from the same source family.
            candidates = identifier_candidates
        elif intent_terms:
            # For a classified topic, require at least one of the topic words in
            # the retrieved passage. Generic expansion terms alone are not proof
            # that a document answers a specific question.
            candidates = [chunk for chunk, terms in prepared if intent_terms.intersection(terms)]
            if source_hints and source_candidates:
                source_ids = {chunk.chunk_id for chunk in source_candidates}
                candidates = [chunk for chunk in candidates if chunk.chunk_id in source_ids]
        elif source_hints:
            candidates = source_candidates
        else:
            candidates = [
                chunk for chunk, terms in prepared
                if set(original_terms).intersection(terms)
                or _tfidf_cosine(original_terms, terms, doc_frequency, total_docs) > 0
                or graph_scores[chunk.chunk_id] > 0
            ]
        if graph_documents:
            selected_ids = {chunk.chunk_id for chunk in candidates}
            candidates += [chunk for chunk, _ in prepared if chunk.document_id in graph_documents and chunk.chunk_id not in selected_ids]
        lexical_order = sorted(candidates, key=lambda c: lexical_scores[c.chunk_id], reverse=True)
        dense_order = sorted(chunks, key=lambda c: dense_scores[c.chunk_id], reverse=True)
        graph_order = sorted(chunks, key=lambda c: graph_scores[c.chunk_id], reverse=True)
        rank_maps = []
        orders = {"lexical": (lexical_order,), "dense": (dense_order,), "hybrid": (lexical_order, dense_order)}[mode]
        if graph and any(graph_scores.values()):
            orders += (graph_order,)
        for ordered in orders:
            rank_maps.append({item.chunk_id: index + 1 for index, item in enumerate(ordered)})

        max_lexical = max((lexical_scores[chunk.chunk_id] for chunk in candidates), default=1.0) or 1.0
        max_rrf = max((sum(1 / (60 + ranks.get(chunk.chunk_id, len(candidates) + 1)) for ranks in rank_maps) for chunk in candidates), default=1.0)
        scored: list[Evidence] = []
        candidate_ids = {chunk.chunk_id for chunk in candidates}
        for chunk, _ in prepared:
            if chunk.chunk_id not in candidate_ids:
                continue
            document = self.store.get_document(chunk.document_id)
            if document is None:
                continue
            rrf = sum(1 / (60 + ranks.get(chunk.chunk_id, len(candidates) + 1)) for ranks in rank_maps)
            lexical = min(1.0, lexical_scores[chunk.chunk_id] / max_lexical)
            rrf_normalized = min(1.0, rrf / max_rrf)
            dense = dense_scores[chunk.chunk_id] if mode != "lexical" else 0.0
            relevance = lexical if mode == "lexical" else dense if mode == "dense" else min(1.0, 0.60 * dense + 0.40 * lexical)
            recency = _recency(document)
            authority = max(0.0, min(1.0, document.authority_score))
            graph_signal = graph_scores[chunk.chunk_id]
            weights = [(0.25, rrf_normalized), (0.50, relevance)]
            if source_priority:
                weights.append((0.15, authority))
            if temporal:
                weights.append((0.07, recency))
            if graph:
                weights.append((0.03, graph_signal))
            final = sum(weight * value for weight, value in weights) / sum(weight for weight, _ in weights)
            scored.append(
                Evidence(
                    chunk_id=chunk.chunk_id,
                    document_id=chunk.document_id,
                    title=document.title,
                    text=chunk.text,
                    source=document.source,
                    source_type=document.source_type,
                    url=chunk.url,
                    page_number=chunk.page_number,
                    section=chunk.section,
                    authority_score=authority,
                    relevance_score=relevance,
                    recency_score=recency,
                    graph_score=graph_signal,
                    final_score=final,
                    provenance={
                        "document_id": document.document_id,
                        "chunk_id": chunk.chunk_id,
                        "source": document.source,
                        "publication_date": document.publication_date,
                        "update_date": document.update_date,
                        "retrieved_at": date.today().isoformat(),
                        "ranking_explanation": f"{mode} retrieval with corpus-IDF BM25 and cached TF-IDF cosine; source_priority={source_priority}, temporal={temporal}, knowledge_graph={graph}.",
                        "graph_relationships": graph_documents.get(document.document_id, []),
                    },
                )
            )
        ranked = sorted(scored, key=lambda item: item.final_score, reverse=True)[: max(limit, limit * 3)]
        reranker_status = {"provider": "none", "status": "disabled_by_configuration"}
        if use_reranker:
            from app.services.reranking import rerank
            ranked, reranker_status = rerank(query, ranked)
        for item in ranked:
            item.provenance["reranker_status"] = reranker_status
        return ranked[:limit]
