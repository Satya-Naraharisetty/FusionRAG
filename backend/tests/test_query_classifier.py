import pytest

from app.documents.services.query_classifier import (
    DeterministicQueryClassifier,
    QueryClassification,
    QueryType,
)


@pytest.fixture
def classifier():
    return DeterministicQueryClassifier()


def test_classifies_factual_query(classifier):
    classification: QueryClassification = classifier.classify(
        "What is the standard availability SLO for enterprise tier tenants?"
    )
    assert classification.query_type == QueryType.FACTUAL
    assert classification.confidence >= 0.80
    assert not classification.requires_expansion
    assert not classification.requires_decomposition
    assert classification.recommended_top_k == 10


def test_classifies_comparison_query_simple(classifier):
    classification = classifier.classify("Compare JWT and OAuth authentication")
    assert classification.query_type == QueryType.COMPARISON
    assert classification.confidence >= 0.80
    # Conservative policy: simple comparison does NOT decompose
    assert not classification.requires_decomposition
    assert classification.recommended_top_k == 12


def test_classifies_comparison_query_multi_target(classifier):
    classification = classifier.classify(
        "Compare 2024 and 2025 revenue metrics as well as operating costs across both reports"
    )
    assert classification.query_type in (
        QueryType.COMPARISON,
        QueryType.MULTI_HOP,
        QueryType.MULTI_DOCUMENT,
    )
    assert classification.requires_decomposition
    assert classification.recommended_top_k >= 15


def test_classifies_multi_hop_query(classifier):
    classification = classifier.classify(
        "What were 2025 revenue growth and also the engineering SLA target?"
    )
    assert classification.query_type == QueryType.MULTI_HOP
    assert classification.requires_decomposition
    assert classification.requires_expansion
    assert classification.recommended_top_k == 20


def test_classifies_multi_document_query(classifier):
    classification = classifier.classify(
        "Across all documents, compare the cloud encryption standards with the audit report"
    )
    assert classification.query_type == QueryType.MULTI_DOCUMENT
    assert classification.requires_decomposition
    assert classification.recommended_top_k == 20


def test_classifies_numerical_query(classifier):
    classification = classifier.classify(
        "What was the total consolidated GAAP revenue for FY2025?"
    )
    assert classification.query_type in (QueryType.NUMERICAL, QueryType.FACTUAL)
    assert not classification.requires_decomposition


def test_classifies_ambiguous_query(classifier):
    classification = classifier.classify("specs info")
    assert classification.query_type == QueryType.AMBIGUOUS
    assert classification.requires_expansion
    assert not classification.requires_decomposition


def test_classifies_conversational_query(classifier):
    classification = classifier.classify("Hello, how are you?")
    assert classification.query_type == QueryType.CONVERSATIONAL
    assert not classification.requires_expansion
    assert not classification.requires_decomposition
    assert classification.recommended_top_k == 5


def test_classification_is_deterministic(classifier):
    q = "What is the token lifetime for JWT access tokens?"
    c1 = classifier.classify(q)
    c2 = classifier.classify(q)
    assert c1.query_type == c2.query_type
    assert c1.confidence == c2.confidence
    assert c1.requires_expansion == c2.requires_expansion
    assert c1.requires_decomposition == c2.requires_decomposition
