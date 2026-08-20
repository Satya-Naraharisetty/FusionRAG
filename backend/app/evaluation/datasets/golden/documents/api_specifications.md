# Platform API Specifications & Developer Integration Guide

## Section 1: Authentication & Authorization Protocol
- **Token Endpoint**: `POST /api/v1/auth/token` accepts OAuth2 password flow credentials and returns a short-lived JSON Web Token (JWT) access token (lifetime: 15 minutes) and a refresh token (lifetime: 7 days).
- **Header Format**: All protected endpoints require `Authorization: Bearer <access_token>` in the HTTP request headers.
- **Role Hierarchy**: Supported user roles are `admin`, `editor`, and `viewer`. Only `admin` accounts can execute benchmark evaluations or configure system-level reranker models.

## Section 2: Rate Limiting & Throttling
- Standard Tier Tenants: Limited to 100 requests per minute per IP with a burst allowance of 20 requests.
- Enterprise Tier Tenants: Limited to 1000 requests per minute per tenant API key with dedicated Redis token bucket limiters.
- Throttled requests return HTTP status code `429 Too Many Requests` accompanied by standard `Retry-After` headers in seconds.

## Section 3: Document Management & Ingestion API
- **Document Upload**: `POST /api/v1/documents/upload` accepts multipart file uploads (PDF, DOCX, TXT, MD) up to 50 megabytes per file.
- **Document Replace**: `POST /api/v1/documents/{document_id}/replace` performs atomic replacement of an existing document while preserving document UUID and lineage.
- **Document Status**: `GET /api/v1/documents/{document_id}/status` returns current processing state (`PENDING`, `PARSING`, `INDEXED`, `FAILED`).

## Section 4: Chat & Multi-Agent Query API
- **Interactive Chat**: `POST /api/v1/chat/completions` accepts structured user prompts and optional conversation IDs, returning streaming server-sent events (SSE) with citations and diagnostic metrics.
- **Direct Search**: `POST /api/v1/documents/search` provides raw hybrid retrieval results including dense similarity scores, sparse BM25 scores, and cross-encoder reranked scores.
