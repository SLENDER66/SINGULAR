import math

import pytest

from singular.provenance import ProvenanceChain, ProvenanceRecord


def record(record_id: str, previous_digest: str = "") -> ProvenanceRecord:
    return ProvenanceRecord.from_payload(
        record_id=record_id,
        source="test",
        recorded_at="2026-09-03T10:00:00Z",
        epistemic_type="FACT",
        confidence=0.9,
        payload={"id": record_id, "value": 42},
        transformation="observed",
        previous_digest=previous_digest,
    )


def test_payload_digest_is_deterministic() -> None:
    first = record("r1")
    second = ProvenanceRecord.from_payload(
        record_id="r1",
        source="test",
        recorded_at="2026-09-03T10:00:00Z",
        epistemic_type="FACT",
        confidence=0.9,
        payload={"value": 42, "id": "r1"},
        transformation="observed",
    )
    assert first.payload_digest == second.payload_digest
    assert first.digest() == second.digest()


def test_chain_links_and_verifies() -> None:
    chain = ProvenanceChain()
    first = record("r1")
    head = chain.append(first)
    chain.append(record("r2", head))
    assert chain.head_digest() == chain.records()[-1].digest()
    assert chain.verify()


def test_chain_rejects_broken_link_and_duplicate_id() -> None:
    chain = ProvenanceChain()
    first = record("r1")
    chain.append(first)
    with pytest.raises(ValueError, match="does not link"):
        chain.append(record("r2", "wrong"))
    with pytest.raises(ValueError, match="already exists"):
        chain.append(record("r1", first.digest()))


def test_chain_detects_tail_tampering() -> None:
    chain = ProvenanceChain()
    chain.append(record("r1"))
    original = chain.records()[0]
    object.__setattr__(original, "confidence", 0.1)
    assert chain.verify() is False


def test_record_rejects_non_finite_confidence() -> None:
    for confidence in (math.nan, math.inf, -math.inf):
        with pytest.raises(ValueError, match="between 0 and 1"):
            record("r1").__class__.from_payload(
                record_id="r2",
                source="test",
                recorded_at="2026-09-03T10:00:00Z",
                epistemic_type="FACT",
                confidence=confidence,
                payload={},
            )


def test_record_requires_payload_digest_and_valid_confidence() -> None:
    with pytest.raises(ValueError, match="payload_digest"):
        ProvenanceRecord(
            record_id="r1",
            source="test",
            recorded_at="2026-09-03T10:00:00Z",
            epistemic_type="FACT",
            confidence=0.9,
        )
    with pytest.raises(ValueError, match="between 0 and 1"):
        ProvenanceRecord.from_payload(
            record_id="r2",
            source="test",
            recorded_at="2026-09-03T10:00:00Z",
            epistemic_type="FACT",
            confidence=1.1,
            payload={},
        )
