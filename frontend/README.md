# Fusion RAG — Frontend Client

The frontend Single Page Application (SPA) for the **Fusion RAG Platform**, built with **React 19**, **Vite 5**, **TypeScript**, **Tailwind CSS v4**, **TanStack Query v5**, and **Radix UI**.

---

## Architecture Overview

The frontend is structured into modular components, pages, hooks, contexts, and API services:

```
frontend/
├── src/
│   ├── api/                     # Type-safe API client wrappers (auth, chat, documents, admin, observability, evaluation)
│   ├── components/              # UI components
│   │   ├── auth/                # Login, Register, ReauthDialog
│   │   ├── chat/                # ChatArea, ChatInput, ChatMessage, CitationDrawer, TraceInspector
│   │   ├── command/             # Global command palette and search
│   │   ├── documents/           # DocumentCard, UploadDropzone, DocumentFilterBar
│   │   ├── layout/              # Header, Navigation, MainLayout
│   │   ├── sidebar/             # ConversationList, ConversationItem, FolderTree, SidebarUploadIndicator
│   │   └── ui/                  # Radix UI primitives, accessible buttons, badges, modals, spinners, tooltips
│   ├── context/                 # Global Context Providers
│   │   ├── AuthContext.tsx      # Authentication state, silent token refresh timer, user session
│   │   ├── ThemeContext.tsx     # Light/Dark mode state management and CSS custom properties
│   │   └── UploadQueueContext.tsx # Persistent background file upload queue and stage tracking
│   ├── hooks/                   # Custom React hooks (useAuth, useConversations, useDocuments, useSSEChat, useDrafts, etc.)
│   ├── lib/                     # Utilities, Shiki syntax highlighter, KaTeX math formatter, notifications
│   ├── pages/                   # Top-level view routes
│   │   ├── AdminDashboardPage.tsx # Observability KPIs, execution traces, evaluation benchmark runner
│   │   ├── ChatPage.tsx         # Conversational chat interface with SSE streaming
│   │   ├── DocumentsPage.tsx    # Two-tier document manager (Global vs Conversation files)
│   │   ├── OAuthCallbackPage.tsx # Google / GitHub OAuth callback handler
│   │   ├── SettingsPage.tsx     # Account settings, theme preferences, password-gated deletion
│   │   └── VerifyEmailPage.tsx  # Resend email verification code confirmation
│   ├── routes/                  # ProtectedRoute and PublicRoute boundary components (React Router v7)
│   └── tests/                   # Vitest unit and integration test suite with MSW mocks
├── e2e/                         # E2E test scripts for live authentication and document flows
├── vite.config.ts               # Vite bundler configuration with @tailwindcss/vite & vite-plugin-pwa
└── package.json                 # Dependencies and scripts
```

---

## Key Frontend Features

1. **Real-Time Streaming Chat (`/chat`)**:
   - Server-Sent Events (SSE) consumer streaming tokens, citations, and metadata.
   - Markdown rendering with **Shiki** syntax highlighting, copy code buttons, and **KaTeX** math formulas.
   - Inline citation badges (`[1]`, `[2]`) opening an interactive drawer highlighting source sentences.
   - Message draft persistence across conversation switches (`useDrafts`).
   - Virtualized message list with **TanStack Virtual** for high-performance rendering of long conversations.
   - Chat export to Markdown or JSON.

2. **Two-Tier Document Management (`/documents`)**:
   - Drag-and-drop file upload (`UploadDropzone`) with multi-stage progress tracking (Validating $\rightarrow$ Scanning $\rightarrow$ Uploading $\rightarrow$ Chunking $\rightarrow$ Vectorizing).
   - Global Library documents addressable across chats via `@documents` mentions.
   - Conversation-scoped attachments uploaded directly in the composer.
   - Tagging, folder organization, search, and cascade deletion.

3. **In-App Admin Console (`/admin/dashboard`)**:
   - Real-time observability dashboard displaying request throughput, token volume, and estimated dollar costs.
   - Detailed LLM execution trace waterfalls showing retrieval, fusion, reranking, and generation latency breakdowns.
   - RAG evaluation suite runner (triggering benchmarks, comparing against baselines, and rendering HTML reports).

4. **Security & Authentication**:
   - Email/password authentication, Google & GitHub OAuth 2.0 social login.
   - Email verification token confirmation (`/verify-email`).
   - Re-authentication security modal for sensitive operations.
   - Password-gated account deletion (`DELETE /api/v1/auth/account`).

5. **Design System, UI & PWA**:
   - **Tailwind CSS v4** styling with curated dark and light mode themes.
   - Accessible UI primitives built on **Radix UI**.
   - Progressive Web App (PWA) offline asset caching via **`vite-plugin-pwa`** and **`workbox-window`**.

---

## Local Development Setup

### 1. Prerequisites
- Node.js v18+
- npm (or pnpm / yarn)
- Backend running at `http://localhost:8000`

### 2. Environment Configuration
```bash
cp .env.example .env
```
Ensure `VITE_API_BASE_URL=http://localhost:8000` is set.

### 3. Install & Start Development Server
```bash
npm install
npm run dev
```
Open [http://localhost:5173](http://localhost:5173) in your browser.

---

## Testing & Quality Assurance

```bash
# Run unit & component tests
npm run test

# Run tests in watch mode
npm run test:watch

# Linting & TypeScript verification
npm run typecheck
npm run lint
npm run build

# Run E2E smoke tests against live running stack
npm run e2e:login
npm run e2e:account-delete
npm run e2e:redis-fallback
npm run e2e:two-tier
```
