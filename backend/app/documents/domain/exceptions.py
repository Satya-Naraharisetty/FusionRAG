class DocumentException(Exception):
    """Base exception for document management errors."""

    pass


class UnsupportedDocumentType(DocumentException):
    """Raised when the uploaded file type is not supported."""

    pass


class DocumentTooLarge(DocumentException):
    """Raised when the uploaded file exceeds maximum configured size."""

    pass


class DocumentExtractionFailed(DocumentException):
    """Raised when text extraction fails."""

    pass


class DocumentCorrupted(DocumentException):
    """Raised when the document is parsed but found to be corrupted."""

    pass


class DocumentNotFound(DocumentException):
    """Raised when a document is not found."""

    pass


class UnauthorizedDocumentAccess(DocumentException):
    """Raised when a user attempts to access a document they do not own."""

    pass


class DuplicateDocumentException(DocumentException):
    """Raised when a user uploads a document that has already been uploaded."""

    pass


class InvalidStateTransitionException(DocumentException):
    """Raised when an invalid state transition is requested."""

    pass


class DocumentProcessingInProgressException(DocumentException):
    """Raised when an operation cannot proceed because the document is currently queued or processing."""

    pass
