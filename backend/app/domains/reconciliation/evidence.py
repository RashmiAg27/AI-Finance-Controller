from dataclasses import dataclass, field


@dataclass
class EvidenceItem:
    evidence_type: str
    field_name: str
    source_value: str | None
    target_value: str | None
    comparator: str
    passed: bool
    detail: dict = field(default_factory=dict)


@dataclass
class MatchCandidate:
    """One proposed match, not yet persisted. source_ids/target_ids support
    1:1 today and 1:N/N:1 once M4's aggregation pass populates more than one
    id on a side -- the shape is ready even though M2's passes only ever
    produce a single id per side."""

    source_ids: list[str]
    target_ids: list[str]
    rule_id: str
    rule_version: int
    match_type: str
    confidence: float
    evidence: list[EvidenceItem]

    @property
    def cardinality(self) -> str:
        if len(self.source_ids) == 1 and len(self.target_ids) == 1:
            return "ONE_TO_ONE"
        if len(self.source_ids) == 1 and len(self.target_ids) > 1:
            return "ONE_TO_MANY"
        if len(self.source_ids) > 1 and len(self.target_ids) == 1:
            return "MANY_TO_ONE"
        return "MANY_TO_MANY"
