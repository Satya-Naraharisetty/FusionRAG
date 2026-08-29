from typing import Any
from uuid import UUID


class DocumentException(Exception):
    """Base domain exception for document management and processing errors."""

    error_code: str = "DOCUMENT_ERROR"
    status_code: int = 500

    def __init__(
        self, message: str | None = None, details: dict[str, Any] | None = None
    ) -> None:
        self.message = message or "An unexpected document management error occurred."
        self.details = details or {}
        super().__init__(self.message)

    def to_dict(self) -> dict[str, Any]:
        return {
            "error_code": self.error_code,
            "message": self.message,
            "details": self.details,
        }

    def __str__(self) -> str:
        if self.details:
            return f"{self.message} (details: {self.details})"
        return self.message


class UnsupportedDocumentType(DocumentException):
    """Raised when an uploaded file format or MIME type is unsupported or invalid."""

    error_code = "UNSUPPORTED_DOCUMENT_TYPE"
    status_code = 415

    def __init__(
        self,
        message: str | None = None,
        mime_type: str | None = None,
        filename: str | None = None,
    ) -> None:
        details: dict[str, Any] = {}
        if mime_type:
            details["mime_type"] = mime_type
        if filename:
            details["filename"] = filename
        default_msg = f"Unsupported or invalid document type: {mime_type or filename or 'unknown'}."
        super().__init__(message=message or default_msg, details=details)


class DocumentTooLarge(DocumentException):
    """Raised when an uploaded document file size exceeds the configured system threshold."""

    error_code = "DOCUMENT_TOO_LARGE"
    status_code = 413

    def __init__(
        self,
        message: str | None = None,
        file_size_bytes: int | None = None,
        max_size_bytes: int | None = None,
    ) -> None:
        details: dict[str, Any] = {}
        if file_size_bytes is not None:
            details["file_size_bytes"] = file_size_bytes
        if max_size_bytes is not None:
            details["max_size_bytes"] = max_size_bytes
        default_msg = (
            f"Document size ({file_size_bytes} bytes) exceeds maximum limit ({max_size_bytes} bytes)."
            if file_size_bytes and max_size_bytes
            else "Document exceeds maximum allowed file size."
        )
        super().__init__(message=message or default_msg, details=details)


class DocumentExtractionFailed(DocumentException):
    """Raised when text or layout extraction fails during document parsing."""

    error_code = "DOCUMENT_EXTRACTION_FAILED"
    status_code = 422

    def __init__(
        self,
        message: str | None = None,
        document_id: UUID | None = None,
        extractor: str | None = None,
        reason: str | None = None,
    ) -> None:
        details: dict[str, Any] = {}
        if document_id:
            details["document_id"] = str(document_id)
        if extractor:
            details["extractor"] = extractor
        if reason:
            details["reason"] = reason
        default_msg = (
            f"Failed to extract content from document: {reason or 'extractor error'}."
        )
        super().__init__(message=message or default_msg, details=details)


class DocumentCorrupted(DocumentException):
    """Raised when a document payload is unreadable, malformed, or fails integrity/decompression checks."""

    error_code = "DOCUMENT_CORRUPTED"
    status_code = 400

    def __init__(
        self,
        message: str | None = None,
        document_id: UUID | None = None,
        reason: str | None = None,
    ) -> None:
        details: dict[str, Any] = {}
        if document_id:
            details["document_id"] = str(document_id)
        if reason:
            details["reason"] = reason
        default_msg = f"Document payload is corrupted or unreadable: {reason or 'header/structural error'}."
        super().__init__(message=message or default_msg, details=details)


class DocumentNotFound(DocumentException):
    """Raised when a requested document ID does not exist in the database."""

    error_code = "DOCUMENT_NOT_FOUND"
    status_code = 404

    def __init__(
        self,
        message: str | None = None,
        document_id: UUID | None = None,
        user_id: UUID | None = None,
    ) -> None:
        details: dict[str, Any] = {}
        if document_id:
            details["document_id"] = str(document_id)
        if user_id:
            details["user_id"] = str(user_id)
        default_msg = f"Document {document_id or ''} was not found."
        super().__init__(message=message or default_msg, details=details)


class UnauthorizedDocumentAccess(DocumentException):
    """Raised when an authenticated user attempts to access a document outside their authorized scope."""

    error_code = "UNAUTHORIZED_DOCUMENT_ACCESS"
    status_code = 403

    def __init__(
        self,
        message: str | None = None,
        document_id: UUID | None = None,
        user_id: UUID | None = None,
    ) -> None:
        details: dict[str, Any] = {}
        if document_id:
            details["document_id"] = str(document_id)
        if user_id:
            details["user_id"] = str(user_id)
        default_msg = "Access denied: you do not have permission to access the requested document."
        super().__init__(message=message or default_msg, details=details)


class DuplicateDocumentException(DocumentException):
    """Raised when a document with identical checksum or identity already exists for the user."""

    error_code = "DUPLICATE_DOCUMENT"
    status_code = 409

    def __init__(
        self,
        message: str | None = None,
        checksum: str | None = None,
        existing_document_id: UUID | None = None,
    ) -> None:
        details: dict[str, Any] = {}
        if checksum:
            details["checksum"] = checksum
        if existing_document_id:
            details["existing_document_id"] = str(existing_document_id)
        default_msg = "A document with the same content checksum already exists."
        super().__init__(message=message or default_msg, details=details)


class InvalidStateTransitionException(DocumentException):
    """Raised when attempting an illegal document or processing run state machine transition."""

    error_code = "INVALID_STATE_TRANSITION"
    status_code = 400

    def __init__(
        self,
        message: str | None = None,
        current_state: str | None = None,
        target_state: str | None = None,
    ) -> None:
        details: dict[str, Any] = {}
        if current_state:
            details["current_state"] = current_state
        if target_state:
            details["target_state"] = target_state
        default_msg = (
            f"Cannot transition state from '{current_state}' to '{target_state}'."
        )
        super().__init__(message=message or default_msg, details=details)


class DocumentProcessingInProgressException(DocumentException):
    """Raised when an operation cannot proceed because the document is currently being processed."""

    error_code = "DOCUMENT_PROCESSING_IN_PROGRESS"
    status_code = 409

    def __init__(
        self, message: str | None = None, document_id: UUID | None = None
    ) -> None:
        details: dict[str, Any] = {}
        if document_id:
            details["document_id"] = str(document_id)
        default_msg = (
            "Document is currently being processed. Please wait for completion."
        )
        super().__init__(message=message or default_msg, details=details)


class ConfigurationIntegrityError(DocumentException):
    """Raised when processing configuration is missing, corrupt, or has an embedding contract mismatch."""

    error_code = "CONFIGURATION_INTEGRITY_ERROR"
    status_code = 500

    def __init__(
        self,
        message: str | None = None,
        config_id: UUID | None = None,
        contract_id: str | None = None,
    ) -> None:
        details: dict[str, Any] = {}
        if config_id:
            details["config_id"] = str(config_id)
        if contract_id:
            details["contract_id"] = contract_id
        default_msg = "Processing configuration integrity check failed or contract mismatch detected."
        super().__init__(message=message or default_msg, details=details)


class UnauthorizedCapabilityError(DocumentException):
    """Raised when an execution plan requests an unauthorized or non-allowlisted capability/operation."""

    error_code = "UNAUTHORIZED_CAPABILITY"
    status_code = 403

    def __init__(
        self,
        message: str | None = None,
        capability_id: str | None = None,
        operation: str | None = None,
    ) -> None:
        details: dict[str, Any] = {}
        if capability_id:
            details["capability_id"] = capability_id
        if operation:
            details["operation"] = operation
        default_msg = f"Unauthorized or forbidden capability operation: {capability_id or operation or 'unknown'}."
        super().__init__(message=message or default_msg, details=details)


class ValidationGateError(DocumentException):
    """Raised when artifact manifest verification fails during the pre-cutover validation gate."""

    error_code = "VALIDATION_GATE_ERROR"
    status_code = 422

    def __init__(
        self,
        message: str | None = None,
        run_id: UUID | None = None,
        reasons: list[str] | None = None,
    ) -> None:
        details: dict[str, Any] = {}
        if run_id:
            details["run_id"] = str(run_id)
        if reasons:
            details["reasons"] = reasons
        default_msg = (
            f"Validation gate rejected artifact manifest: {'; '.join(reasons or [])}."
        )
        super().__init__(message=message or default_msg, details=details)


class LeaseExpiredError(DocumentException):
    """Raised when a background worker attempts a fenced mutation after its worker lease has expired."""

    error_code = "LEASE_EXPIRED"
    status_code = 409

    def __init__(
        self,
        message: str | None = None,
        job_id: UUID | None = None,
        lease_token: UUID | None = None,
    ) -> None:
        details: dict[str, Any] = {}
        if job_id:
            details["job_id"] = str(job_id)
        if lease_token:
            details["lease_token"] = str(lease_token)
        default_msg = (
            "Worker lease has expired or was revoked. Mutation aborted for safety."
        )
        super().__init__(message=message or default_msg, details=details)


class CutoverRaceError(DocumentException):
    """Raised when an atomic cutover fails due to a concurrent update establishing a newer version."""

    error_code = "CUTOVER_RACE_ERROR"
    status_code = 409

    def __init__(
        self,
        message: str | None = None,
        document_id: UUID | None = None,
        target_version: int | None = None,
    ) -> None:
        details: dict[str, Any] = {}
        if document_id:
            details["document_id"] = str(document_id)
        if target_version is not None:
            details["target_version"] = target_version
        default_msg = f"Cutover race detected: document active_version has already progressed beyond version {target_version}."
        super().__init__(message=message or default_msg, details=details)


class EvidenceAuthorizationError(DocumentException):
    """Raised when retrieved evidence fails security, tenant isolation, or active-version checks."""

    error_code = "EVIDENCE_AUTHORIZATION_ERROR"
    status_code = 403

    def __init__(
        self,
        message: str | None = None,
        element_id: UUID | None = None,
        document_id: UUID | None = None,
    ) -> None:
        details: dict[str, Any] = {}
        if element_id:
            details["element_id"] = str(element_id)
        if document_id:
            details["document_id"] = str(document_id)
        default_msg = "Evidence failed authorization check: inactive version or cross-tenant scope violation."
        super().__init__(message=message or default_msg, details=details)


class CitationValidationError(DocumentException):
    """Raised when citation entailment verification fails or is contradicted by source evidence."""

    error_code = "CITATION_VALIDATION_ERROR"
    status_code = 422

    def __init__(
        self,
        message: str | None = None,
        claim_text: str | None = None,
        status_name: str | None = None,
    ) -> None:
        details: dict[str, Any] = {}
        if claim_text:
            details["claim_text"] = claim_text
        if status_name:
            details["status_name"] = status_name
        default_msg = f"Citation entailment validation failed (status: {status_name or 'UNVERIFIED'})."
        super().__init__(message=message or default_msg, details=details)
