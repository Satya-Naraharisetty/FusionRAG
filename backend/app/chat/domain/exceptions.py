class ChatException(Exception):
    """Base exception for chat and orchestration."""
    pass


class NoRelevantContext(ChatException):
    """Raised when there is no matching context or it doesn't fit in the budget."""
    pass


class LLMProviderError(ChatException):
    """Raised on LLM API or connection failures."""
    pass


class PromptTooLarge(ChatException):
    """Raised when the prompt built exceeds token limits."""
    pass


class TokenBudgetExceeded(ChatException):
    """Raised when the configured budget is exceeded."""
    pass


class StreamingCancelled(ChatException):
    """Raised when a streaming request is cancelled by the client."""
    pass


class ConversationNotFoundException(ChatException):
    """Raised when a conversation is not found."""
    pass


class ConversationConcurrentUpdateException(ChatException):
    """Raised when an optimistic locking version conflict is detected."""
    pass


class UnauthorizedConversationAccessException(ChatException):
    """Raised when a user attempts to access a conversation they do not own."""
    pass


class InvalidStatusTransitionException(ChatException):
    """Raised when a message status transition is illegal."""
    pass
