from decimal import Decimal
from uuid import UUID

from app.documents.domain.models import (
    format_visual_embedding_payload,
    generate_element_id,
    generate_entity_id,
    generate_qdrant_point_id,
    normalize_entity_name,
    normalize_entity_type,
    sanitize_cell_value,
)


def test_deterministic_element_id_generation():
    user_id = UUID("11111111-1111-1111-1111-111111111111")
    doc_id = UUID("22222222-2222-2222-2222-222222222222")
    version = 1
    index = 0

    id1 = generate_element_id(user_id, doc_id, version, index)
    id2 = generate_element_id(user_id, doc_id, version, index)
    assert id1 == id2
    assert isinstance(id1, UUID)

    # Different version yields different ID
    id_v2 = generate_element_id(user_id, doc_id, 2, index)
    assert id1 != id_v2


def test_deterministic_entity_id_and_normalization():
    user_id = UUID("11111111-1111-1111-1111-111111111111")
    raw_name_1 = "   Alphabet Inc.  \n"
    raw_name_2 = "alphabet inc."
    type_1 = "ORGANIZATION"
    type_2 = "organization"

    norm_1 = normalize_entity_name(raw_name_1)
    norm_2 = normalize_entity_name(raw_name_2)
    assert norm_1 == norm_2 == "alphabet inc."

    norm_type_1 = normalize_entity_type(type_1)
    norm_type_2 = normalize_entity_type(type_2)
    assert norm_type_1 == norm_type_2 == "ORGANIZATION"

    id1 = generate_entity_id(user_id, norm_1, norm_type_1)
    id2 = generate_entity_id(user_id, norm_2, norm_type_2)
    assert id1 == id2


def test_deterministic_qdrant_point_id():
    user_id = UUID("11111111-1111-1111-1111-111111111111")
    doc_id = UUID("22222222-2222-2222-2222-222222222222")
    elem_id = UUID("33333333-3333-3333-3333-333333333333")
    contract = "text-embedding-3-small:1536:cosine:v1"

    p1 = generate_qdrant_point_id(user_id, doc_id, 1, elem_id, "TEXT", contract)
    p2 = generate_qdrant_point_id(user_id, doc_id, 1, elem_id, "TEXT", contract)
    assert p1 == p2

    p_visual = generate_qdrant_point_id(
        user_id, doc_id, 1, elem_id, "VISUAL_SEMANTIC", contract
    )
    assert p1 != p_visual


def test_sanitize_cell_value_numeric_and_injection():
    # Valid positive and negative numbers
    num, s_val = sanitize_cell_value("-150.50")
    assert num == Decimal("-150.50")
    assert s_val == "-150.50"

    num_pos, s_val_pos = sanitize_cell_value("+42")
    assert num_pos == Decimal("42")
    assert s_val_pos == "+42"

    num_clean, s_val_clean = sanitize_cell_value("1,234.56")
    assert num_clean == Decimal("1234.56")

    # Formula injection attempts
    inj_1, s_inj_1 = sanitize_cell_value("=SUM(A1:B10)")
    assert inj_1 is None
    assert s_inj_1 == "'=SUM(A1:B10)"

    inj_2, s_inj_2 = sanitize_cell_value("@malicious_cmd")
    assert inj_2 is None
    assert s_inj_2 == "'@malicious_cmd"

    inj_3, s_inj_3 = sanitize_cell_value("-cmd|' /C calc'!A0")
    assert inj_3 is None
    assert s_inj_3.startswith("'-")


def test_format_visual_embedding_payload():
    payload = format_visual_embedding_payload(
        element_type="CHART",
        caption="Q3 Revenue",
        visual_description="Bar chart showing upward quarterly growth.",
        extracted_data="Q1: $10M, Q2: $14M, Q3: $18M",
    )
    assert "Type: CHART" in payload
    assert "Caption: Q3 Revenue" in payload
    assert "Description: Bar chart showing upward quarterly growth." in payload
    assert "Data: Q1: $10M, Q2: $14M, Q3: $18M" in payload
