import React from "react";
import { Link } from "react-router-dom";
import { SEOHead } from "../components/seo/SEOHead";
import { useAuth } from "../hooks/useAuth";

export const LandingPage: React.FC = () => {
  const { isAuthenticated } = useAuth();

  return (
    <div className="min-h-screen bg-[var(--bg-primary,#0b0e14)] text-[var(--text-primary,#f1f5f9)] selection:bg-[var(--accent-primary,#3b82f6)] selection:text-white">
      <SEOHead
        title="Unified Enterprise Hybrid Retrieval & QA"
        description="FusionRAG is a production-ready Hybrid RAG platform combining dense vector search, BM25 sparse retrieval, and cross-encoder reranking for verifiable, hallucination-free document QA."
        keywords="FusionRAG, Hybrid RAG, Dense Vector Search, BM25, Cross-Encoder Reranking, Qdrant, FastAPI, AI Document QA, DeepEval"
      />

      {/* Navigation Header */}
      <header className="sticky top-0 z-50 border-b border-[var(--border-default,#1e293b)] bg-[var(--bg-primary,#0b0e14)]/80 backdrop-blur-md">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-tr from-blue-600 to-indigo-500 shadow-md shadow-blue-500/20">
              <svg
                className="h-5 w-5 text-white"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M13 10V3L4 14h7v7l9-11h-7z"
                />
              </svg>
            </div>
            <span className="font-outfit text-xl font-bold tracking-tight text-white">
              Fusion<span className="text-blue-500">RAG</span>
            </span>
          </div>

          <nav className="flex items-center gap-4">
            {isAuthenticated ? (
              <Link
                to="/chat"
                className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-blue-500"
              >
                Open Chat Studio &rarr;
              </Link>
            ) : (
              <>
                <Link
                  to="/login"
                  className="text-sm font-medium text-[var(--text-secondary,#94a3b8)] transition hover:text-white"
                >
                  Sign In
                </Link>
                <Link
                  to="/register"
                  className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-blue-500"
                >
                  Get Started Free
                </Link>
              </>
            )}
          </nav>
        </div>
      </header>

      <main>
        {/* Hero Section */}
        <section className="relative overflow-hidden px-6 pt-20 pb-16 lg:pt-32 lg:pb-24">
          <div className="mx-auto max-w-5xl text-center">
            <div className="mb-6 inline-flex items-center gap-2 rounded-full border border-blue-500/30 bg-blue-500/10 px-3.5 py-1.5 text-xs font-medium text-blue-400">
              <span className="inline-block h-2 w-2 rounded-full bg-blue-400 animate-pulse"></span>
              Dense + BM25 Sparse Search + Cross-Encoder Reranking
            </div>

            <h1 className="font-outfit text-4xl font-extrabold tracking-tight sm:text-6xl text-white">
              Grounded, Enterprise QA with{" "}
              <span className="bg-gradient-to-r from-blue-400 via-indigo-400 to-purple-400 bg-clip-text text-transparent">
                Hybrid Retrieval
              </span>
            </h1>

            <p className="mx-auto mt-6 max-w-2xl text-lg text-[var(--text-secondary,#94a3b8)] leading-relaxed">
              Eliminate LLM hallucinations with multi-stage hybrid retrieval. Combine semantic dense
              embeddings with exact keyword BM25 scoring and neural cross-encoders to deliver
              high-precision answers with verifiable source citations.
            </p>

            <div className="mt-10 flex flex-wrap items-center justify-center gap-4">
              <Link
                to={isAuthenticated ? "/chat" : "/register"}
                className="rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 px-7 py-3.5 text-base font-semibold text-white shadow-lg shadow-blue-500/25 transition hover:shadow-blue-500/40 hover:scale-[1.02]"
              >
                {isAuthenticated ? "Launch Dashboard" : "Start Indexing Documents"}
              </Link>
              <Link
                to="/login"
                className="rounded-xl border border-[var(--border-default,#1e293b)] bg-[var(--bg-elevated,#1e293b)]/40 px-7 py-3.5 text-base font-medium text-white transition hover:bg-[var(--bg-elevated,#1e293b)] hover:border-slate-600"
              >
                Sign In &rarr;
              </Link>
            </div>
          </div>
        </section>

        {/* Feature Grid */}
        <section className="border-t border-[var(--border-default,#1e293b)] bg-[var(--bg-elevated,#0f172a)]/40 px-6 py-20">
          <div className="mx-auto max-w-7xl">
            <div className="text-center mb-16">
              <h2 className="font-outfit text-3xl font-bold text-white">
                Engineered for Accuracy & Scalability
              </h2>
              <p className="mt-3 text-sm text-[var(--text-secondary,#94a3b8)]">
                Built on modern vector databases, asynchronous queues, and rigorous benchmarking.
              </p>
            </div>

            <div className="grid gap-8 md:grid-cols-3">
              {/* Feature 1 */}
              <article className="rounded-2xl border border-[var(--border-default,#1e293b)] bg-[var(--bg-primary,#0b0e14)] p-8 shadow-sm transition hover:border-blue-500/50">
                <div className="mb-5 flex h-12 w-12 items-center justify-center rounded-xl bg-blue-500/10 text-blue-400">
                  <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
                    />
                  </svg>
                </div>
                <h3 className="font-outfit text-xl font-semibold text-white">
                  Hybrid Retrieval Pipeline
                </h3>
                <p className="mt-3 text-sm text-[var(--text-secondary,#94a3b8)] leading-relaxed">
                  Fuses semantic vector similarity (Qdrant) with lexical BM25 token matching via
                  Reciprocal Rank Fusion (RRF), ensuring exact keyword recall and conceptual
                  comprehension.
                </p>
              </article>

              {/* Feature 2 */}
              <article className="rounded-2xl border border-[var(--border-default,#1e293b)] bg-[var(--bg-primary,#0b0e14)] p-8 shadow-sm transition hover:border-indigo-500/50">
                <div className="mb-5 flex h-12 w-12 items-center justify-center rounded-xl bg-indigo-500/10 text-indigo-400">
                  <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
                    />
                  </svg>
                </div>
                <h3 className="font-outfit text-xl font-semibold text-white">
                  Cross-Encoder Reranking
                </h3>
                <p className="mt-3 text-sm text-[var(--text-secondary,#94a3b8)] leading-relaxed">
                  Second-stage cross-encoder scoring accurately isolates the most contextually
                  relevant passages, filtering out noise and drastically reducing hallucination
                  risks.
                </p>
              </article>

              {/* Feature 3 */}
              <article className="rounded-2xl border border-[var(--border-default,#1e293b)] bg-[var(--bg-primary,#0b0e14)] p-8 shadow-sm transition hover:border-purple-500/50">
                <div className="mb-5 flex h-12 w-12 items-center justify-center rounded-xl bg-purple-500/10 text-purple-400">
                  <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"
                    />
                  </svg>
                </div>
                <h3 className="font-outfit text-xl font-semibold text-white">
                  DeepEval & Ragas Auditing
                </h3>
                <p className="mt-3 text-sm text-[var(--text-secondary,#94a3b8)] leading-relaxed">
                  Continuous evaluation for Faithfulness, Answer Relevancy, Context Precision, and
                  Hallucination metrics with automated regression benchmarking.
                </p>
              </article>
            </div>
          </div>
        </section>

        {/* Architecture & Tech Stack Details */}
        <section className="px-6 py-20">
          <div className="mx-auto max-w-5xl rounded-3xl border border-[var(--border-default,#1e293b)] bg-gradient-to-b from-[var(--bg-elevated,#1e293b)]/30 to-transparent p-10 text-center">
            <h2 className="font-outfit text-2xl font-bold text-white sm:text-3xl">
              Enterprise Deployment Architecture
            </h2>
            <p className="mx-auto mt-4 max-w-2xl text-sm text-[var(--text-secondary,#94a3b8)]">
              Frontend deployed on Vercel with global CDN edge caching; asynchronous ingestion
              workers and FastAPI services hosted on Render with Redis Stream task orchestration.
            </p>

            <div className="mt-8 flex flex-wrap items-center justify-center gap-3 text-xs font-mono text-[var(--text-secondary,#94a3b8)]">
              <span className="rounded-lg border border-slate-700 bg-slate-800/80 px-3 py-1.5">
                FastAPI
              </span>
              <span className="rounded-lg border border-slate-700 bg-slate-800/80 px-3 py-1.5">
                React + Vite
              </span>
              <span className="rounded-lg border border-slate-700 bg-slate-800/80 px-3 py-1.5">
                Qdrant Vector DB
              </span>
              <span className="rounded-lg border border-slate-700 bg-slate-800/80 px-3 py-1.5">
                Redis Streams
              </span>
              <span className="rounded-lg border border-slate-700 bg-slate-800/80 px-3 py-1.5">
                Cross-Encoder
              </span>
              <span className="rounded-lg border border-slate-700 bg-slate-800/80 px-3 py-1.5">
                OpenTelemetry
              </span>
            </div>
          </div>
        </section>
      </main>

      {/* Footer */}
      <footer className="border-t border-[var(--border-default,#1e293b)] px-6 py-8">
        <div className="mx-auto flex max-w-7xl flex-col items-center justify-between gap-4 sm:flex-row text-xs text-[var(--text-secondary,#94a3b8)]">
          <p>&copy; {new Date().getFullYear()} FusionRAG. All rights reserved.</p>
          <div className="flex items-center gap-6">
            <Link to="/login" className="hover:text-white transition">
              Sign In
            </Link>
            <Link to="/register" className="hover:text-white transition">
              Register
            </Link>
            <a
              href="https://github.com"
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-white transition"
            >
              GitHub
            </a>
          </div>
        </div>
      </footer>
    </div>
  );
};

export default LandingPage;
