import logging

from app.chat.domain.multi_agent import CapabilityDescriptor, CapabilityType

logger = logging.getLogger(__name__)


class CapabilityRegistry:
    """
    Deterministic infrastructure/application service that registers, validates,
    and exposes available capabilities.

    Not an agent. Does not execute tasks, query databases, or call LLMs.
    Runtime requests cannot register or unregister capabilities.
    """

    def __init__(self, capabilities: list[CapabilityDescriptor] | None = None) -> None:
        self._capabilities: dict[str, CapabilityDescriptor] = {}
        if capabilities:
            for desc in capabilities:
                self.register(desc)

    def validate_descriptor(self, descriptor: CapabilityDescriptor) -> list[str]:
        """Validates a capability descriptor against invariants."""
        errors: list[str] = []
        if not descriptor.capability_id or not descriptor.capability_id.strip():
            errors.append("Capability ID must not be empty.")
        if descriptor.capability_type not in CapabilityType:
            errors.append(f"Invalid capability type: {descriptor.capability_type}")
        if descriptor.estimated_latency_ms < 0:
            errors.append("Estimated latency ms must be non-negative.")
        if descriptor.estimated_cost_units < 0:
            errors.append("Estimated cost units must be non-negative.")
        return errors

    def register(self, descriptor: CapabilityDescriptor) -> None:
        """
        Registers a capability descriptor.
        Raises ValueError if the descriptor is invalid.
        """
        errors = self.validate_descriptor(descriptor)
        if errors:
            raise ValueError(
                f"Invalid capability descriptor '{descriptor.capability_id}': {'; '.join(errors)}"
            )
        self._capabilities[descriptor.capability_id] = descriptor
        logger.debug(
            "Registered capability: %s (%s)",
            descriptor.capability_id,
            descriptor.capability_type.value,
        )

    def unregister(self, capability_id: str) -> bool:
        """
        Unregisters a capability by ID (used for test isolation / lifecycle teardown).
        """
        if capability_id in self._capabilities:
            del self._capabilities[capability_id]
            logger.debug("Unregistered capability: %s", capability_id)
            return True
        return False

    def get(self, capability_id: str) -> CapabilityDescriptor | None:
        """Retrieves a capability descriptor by ID."""
        return self._capabilities.get(capability_id)

    def list_enabled(self) -> list[CapabilityDescriptor]:
        """Lists all currently enabled capability descriptors."""
        return [c for c in self._capabilities.values() if c.enabled]

    def list_by_type(
        self, capability_type: CapabilityType
    ) -> list[CapabilityDescriptor]:
        """Lists all enabled capability descriptors matching the specified CapabilityType."""
        return [
            c
            for c in self._capabilities.values()
            if c.enabled and c.capability_type == capability_type
        ]

    def list_all(self) -> list[CapabilityDescriptor]:
        """Lists all registered capability descriptors (enabled and disabled)."""
        return list(self._capabilities.values())


def create_default_capability_registry() -> CapabilityRegistry:
    """
    Creates and returns the standard production CapabilityRegistry
    populated with core specialist capabilities.
    """
    default_descriptors = [
        CapabilityDescriptor(
            capability_id="research.hybrid_rag",
            capability_type=CapabilityType.RESEARCH,
            description="Performs hybrid dense and sparse search over indexed knowledge base chunks.",
            supported_operations=["semantic_search", "hybrid_search"],
            required_context=["user_id"],
            estimated_latency_ms=1200.0,
            estimated_cost_units=1.0,
            enabled=True,
            metadata={"specialist": "ResearchAgent"},
        ),
        CapabilityDescriptor(
            capability_id="document.inspection",
            capability_type=CapabilityType.DOCUMENT_INSPECTION,
            description="Direct inspection, metadata lookup, and chunk reading for specific user/conversation documents.",
            supported_operations=["inspect", "list", "read_chunk"],
            required_context=["user_id"],
            estimated_latency_ms=300.0,
            estimated_cost_units=0.2,
            enabled=True,
            metadata={"specialist": "DocumentAgent"},
        ),
        CapabilityDescriptor(
            capability_id="analysis.math_engine",
            capability_type=CapabilityType.ANALYSIS,
            description="AST-sandboxed scientific, engineering, financial, and symbolic mathematics engine (calculus, ODEs, transforms, matrices, CAGR, NPV, stats).",
            supported_operations=[
                "calculate",
                "compute",
                "growth_rate",
                "compare",
                "solve_equation",
                "solve_system",
                "solve_ode",
                "diff",
                "integrate",
                "limit",
                "series",
                "laplace_transform",
                "matrix_operations",
                "unit_convert",
                "cagr",
                "npv",
                "irr",
                "amortization",
                "wacc",
                "stats",
                "hypothesis_test",
                "correlation",
                "curve_fit",
            ],
            required_context=[],
            estimated_latency_ms=80.0,
            estimated_cost_units=0.05,
            enabled=True,
            metadata={"specialist": "AnalysisAgent"},
        ),
        CapabilityDescriptor(
            capability_id="web_search.live",
            capability_type=CapabilityType.WEB_SEARCH,
            description="Searches the live public web for real-time information, current news, facts, and online sources.",
            supported_operations=["web_search", "search_web", "live_search"],
            required_context=[],
            estimated_latency_ms=1500.0,
            estimated_cost_units=0.8,
            enabled=True,
            metadata={"specialist": "WebSearchAgent"},
        ),
        CapabilityDescriptor(
            capability_id="synthesis.grounded_summary",
            capability_type=CapabilityType.SYNTHESIS,
            description="Grounded multi-agent result synthesis and citation attribution.",
            supported_operations=["synthesize", "summarize"],
            required_context=["user_id"],
            estimated_latency_ms=800.0,
            estimated_cost_units=0.5,
            enabled=True,
            metadata={"specialist": "SynthesisAgent", "executable_worker": False},
        ),
        CapabilityDescriptor(
            capability_id="table.structured_engine",
            capability_type=CapabilityType.TABLE,
            description="Structured table parsing, column filtering, and deterministic Decimal arithmetic aggregation.",
            supported_operations=["parse_table", "table_aggregate", "table_filter"],
            required_context=["user_id"],
            estimated_latency_ms=100.0,
            estimated_cost_units=0.1,
            max_calls_per_plan=5,
            enabled=True,
            metadata={"specialist": "TableAgent"},
        ),
        CapabilityDescriptor(
            capability_id="vision.multimodal_inspection",
            capability_type=CapabilityType.VISION,
            description="Multimodal visual reasoning, diagram inspection, and chart/figure trend extraction.",
            supported_operations=["describe_image", "inspect_figure", "chart_analysis"],
            required_context=["user_id"],
            estimated_latency_ms=1000.0,
            estimated_cost_units=0.7,
            max_calls_per_plan=5,
            enabled=True,
            metadata={"specialist": "VisionAgent"},
        ),
        CapabilityDescriptor(
            capability_id="graph.knowledge_traversal",
            capability_type=CapabilityType.GRAPH,
            description="Knowledge graph traversal, entity relationship queries, and active-version evidence collection.",
            supported_operations=[
                "traverse_graph",
                "entity_relationships",
                "subgraph_search",
            ],
            required_context=["user_id"],
            estimated_latency_ms=400.0,
            estimated_cost_units=0.3,
            max_calls_per_plan=5,
            enabled=True,
            metadata={"specialist": "GraphAgent"},
        ),
    ]
    return CapabilityRegistry(default_descriptors)
