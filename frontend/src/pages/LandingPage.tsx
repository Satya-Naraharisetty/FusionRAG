import React, { useState } from "react";
import { Link } from "react-router-dom";
import { SEOHead } from "../components/seo/SEOHead";
import { useAuth } from "../hooks/useAuth";
import {
  ArrowRight,
  CheckCircle2,
  Cpu,
  FileText,
  GitBranch,
  Layers,
  Lock,
  Network,
  Search,
  ShieldCheck,
  Sparkles,
  Terminal,
} from "lucide-react";

export const LandingPage: React.FC = () => {
  const { isAuthenticated } = useAuth();
  const [activeTab, setActiveTab] = useState<"finance" | "technical" | "graph">("finance");

  const handleRunDemo = (tab: "finance" | "technical" | "graph") => {
    setActiveTab(tab);
  };

  const demoScenarios = {
    finance: {
      query: "Compare Q3 enterprise revenue across regional filings and compute YoY CAGR",
      plan: ["TableAgent: Extract revenue matrices", "AnalysisAgent: AST-sandboxed CAGR compute", "ResearchAgent: Retrieve 10-K risk disclosures"],
      agents: [
        { name: "TableAgent", role: "Tabular Matrix Extraction", status: "completed", time: "42ms" },
        { name: "AnalysisAgent", role: "AST SafeCalculator Math", status: "completed", time: "18ms" },
        { name: "ResearchAgent", role: "Hybrid Vector + BM25", status: "completed", time: "85ms" },
      ],
      retrieval: {
        vector: "Qdrant Matryoshka ANN (0.892)",
        sparse: "Postgres FTS BM25 (Rank 1/40)",
        fusion: "RRF Combined (0.0328, k=60)",
        rerank: "Jina Cross-Encoder v2 (0.974)",
      },
      answer: "Q3 enterprise revenue reached $482.4M, representing a 34.2% YoY growth (verified 3-year CAGR: 28.6%). Gross margin expanded 280 bps driven by hybrid cloud subscription volume.",
      citations: [
        { id: "SEC-10K §3.2", label: "FY26_Q3_Financials.pdf", page: "p. 18" },
        { id: "MathEngine", label: "AST SafeCalculator Formula: ((482.4/359.5)-1)*100", page: "verified" },
      ],
    },
    technical: {
      query: "Verify AES-256-GCM envelope encryption and crypto-shredding key rotation",
      plan: ["DocumentAgent: Inspect security spec", "ResearchAgent: Match NIST SP 800-38D", "MasterAgent: Verify zero-leakage invariant"],
      agents: [
        { name: "DocumentAgent", role: "Tenant Ownership Gate", status: "completed", time: "24ms" },
        { name: "ResearchAgent", role: "NIST Crypto Compliance", status: "completed", time: "64ms" },
        { name: "MasterAgent", role: "Topological Verification", status: "completed", time: "12ms" },
      ],
      retrieval: {
        vector: "Qdrant Matryoshka ANN (0.941)",
        sparse: "Postgres FTS BM25 (Rank 1/12)",
        fusion: "RRF Combined (0.0331, k=60)",
        rerank: "Jina Cross-Encoder v2 (0.988)",
      },
      answer: "Cache entries in Redis L2 are encrypted using user-specific Data Encryption Keys (DEKs) wrapped by the master Key Encryption Key. Account deletion permanently destroys the user DEK, instantly rendering all historic ciphertext unrecoverable.",
      citations: [
        { id: "ARCH §4.3", label: "ARCHITECTURE.md (Security Engine)", page: "line 428" },
        { id: "NIST-800", label: "AES-256-GCM Verification Suite", page: "passed" },
      ],
    },
    graph: {
      query: "Traverse supplier dependencies and identify single-point-of-failure semiconductor vendors",
      plan: ["GraphAgent: Multi-hop triple traversal", "TableAgent: Join inventory buffers", "Synthesis: Isolate contextual subgraph"],
      agents: [
        { name: "GraphAgent", role: "PostgresGraphRetriever 3-Hop", status: "completed", time: "56ms" },
        { name: "TableAgent", role: "BOM Inventory Join", status: "completed", time: "38ms" },
        { name: "ResearchAgent", role: "Supplier Contract Clauses", status: "completed", time: "72ms" },
      ],
      retrieval: {
        vector: "Qdrant Subgraph Embeddings (0.912)",
        sparse: "Postgres Lexical Entity Match",
        fusion: "RRF Combined (0.0319, k=60)",
        rerank: "Jina Cross-Encoder v2 (0.965)",
      },
      answer: "Multi-hop graph traversal identified 2 critical single-source silicon vendors: FabCo Global (ASIC controllers) and SiliconFoundry LLC (RF modules). Current buffer inventories provide 45 days of operational coverage.",
      citations: [
        { id: "GraphTriple", label: "GraphEdge::Component_Supplied_By", page: "edge_id: 8492" },
        { id: "SupplyChain", label: "Q3_Vendor_Audit_Master.xlsx", page: "sheet: BOM" },
      ],
    },
  };

  const currentDemo = demoScenarios[activeTab];

  return (
    <div className="min-h-screen bg-[var(--bg-primary)] text-[var(--text-primary)] selection:bg-[var(--accent-primary)] selection:text-black">
      <SEOHead
        title="FusionRAG — Unified Enterprise Hybrid Retrieval & Multi-Agent QA"
        description="Enterprise Hybrid RAG platform combining 7 specialist agents, 4-stage neural reranking, and sub-10ms encrypted caching with zero local PyTorch dependencies."
        keywords="FusionRAG, Hybrid RAG, Multi-Agent DAG, Qdrant, BM25, Cross-Encoder, FastAPI, React 19, Citations, DeepEval"
      />

      {/* Top Navigation */}
      <header className="sticky top-0 z-50 border-b border-[var(--border-subtle)] bg-[var(--bg-primary)]/85 backdrop-blur-xl">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-3.5">
          {/* Brand */}
          <Link to="/" className="flex items-center gap-3 group">
            <div className="flex h-9 w-9 items-center justify-center rounded-[var(--radius-lg)] bg-[image:var(--gradient-main)] text-white shadow-[var(--shadow-glow)] transition-transform duration-200 group-hover:scale-105">
              <span className="font-title text-lg font-bold leading-none">F</span>
            </div>
            <div className="flex flex-col">
              <div className="flex items-center gap-2">
                <span className="font-title text-lg font-bold tracking-tight text-[var(--text-primary)]">
                  Fusion<span className="text-[var(--accent-primary)]">RAG</span>
                </span>
                <span className="inline-flex items-center gap-1 rounded-full border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-2 py-0.5 text-[10px] font-semibold text-[var(--accent-secondary)]">
                  <span className="h-1.5 w-1.5 rounded-full bg-[var(--accent-primary)] animate-pulse"></span>
                  v0.1.0-prod
                </span>
              </div>
            </div>
          </Link>

          {/* Links */}
          <nav className="hidden md:flex items-center gap-8 text-sm font-medium text-[var(--text-secondary)]">
            <a href="#agents" className="transition hover:text-[var(--text-primary)]">
              Multi-Agent DAG
            </a>
            <a href="#retrieval" className="transition hover:text-[var(--text-primary)]">
              4-Stage Hybrid Fusion
            </a>
            <a href="#caching" className="transition hover:text-[var(--text-primary)]">
              Encrypted Caching
            </a>
            <a href="#evaluation" className="transition hover:text-[var(--text-primary)]">
              Evaluations
            </a>
            <a
              href="https://github.com"
              target="_blank"
              rel="noopener noreferrer"
              className="transition hover:text-[var(--text-primary)]"
            >
              GitHub
            </a>
          </nav>

          {/* Action Button */}
          <div className="flex items-center gap-3">
            {isAuthenticated ? (
              <Link
                to="/chat"
                className="inline-flex items-center gap-2 rounded-[var(--radius-lg)] bg-[var(--accent-primary)] px-4 py-2 text-xs font-semibold text-black shadow-[var(--shadow-glow)] transition duration-150 hover:bg-[var(--accent-secondary)] hover:shadow-cyan-400/30"
              >
                <span>Launch Studio</span>
                <ArrowRight size={14} />
              </Link>
            ) : (
              <>
                <Link
                  to="/login"
                  className="hidden sm:inline-flex text-xs font-semibold text-[var(--text-secondary)] transition hover:text-[var(--text-primary)] px-3 py-1.5"
                >
                  Sign In
                </Link>
                <Link
                  to="/register"
                  className="inline-flex items-center gap-2 rounded-[var(--radius-lg)] bg-[var(--accent-primary)] px-4 py-2 text-xs font-semibold text-black shadow-[var(--shadow-glow)] transition duration-150 hover:bg-[var(--accent-secondary)] hover:shadow-cyan-400/30"
                >
                  <span>Start Free</span>
                  <ArrowRight size={14} />
                </Link>
              </>
            )}
          </div>
        </div>
      </header>

      <main>
        {/* =========================================================================
            SECTION 1: HERO — ONE SECTION PER SCREEN (Fig.ma / X.ai aesthetic)
           ========================================================================= */}
        <section className="relative min-h-[calc(100vh-60px)] flex flex-col justify-center px-6 py-12 md:py-16 overflow-hidden border-b border-[var(--border-subtle)]">
          {/* Subtle Ambient Radial Lighting */}
          <div className="pointer-events-none absolute -top-40 left-1/2 -translate-x-1/2 h-[600px] w-[1000px] rounded-full bg-[radial-gradient(circle_at_center,rgba(0,210,253,0.12)_0%,rgba(130,162,255,0.04)_45%,transparent_70%)] blur-3xl"></div>

          <div className="mx-auto w-full max-w-7xl relative z-10 flex flex-col items-center text-center">
            {/* Status Pill */}
            <div className="mb-6 inline-flex items-center gap-2 rounded-full border border-[var(--border-cyan)] bg-[var(--bg-secondary)]/90 px-4 py-1.5 text-xs font-medium text-[var(--accent-secondary)] shadow-[var(--shadow-glow)]">
              <span className="flex h-2 w-2 rounded-full bg-[var(--accent-primary)]"></span>
              <span>Zero Local PyTorch Bloat · 7 Parallel Agents · Sub-10ms Cached QA</span>
            </div>

            {/* Main Headline */}
            <h1 className="font-title text-4xl sm:text-6xl md:text-7xl font-extrabold tracking-tight text-white max-w-5xl leading-[1.08] mb-6">
              The Enterprise RAG Platform{" "}
              <span className="bg-gradient-to-r from-white via-[var(--accent-secondary)] to-[var(--accent-primary)] bg-clip-text text-transparent">
                Engineered for Zero Fluff.
              </span>
            </h1>

            {/* Subhead */}
            <p className="max-w-3xl text-base sm:text-lg md:text-xl text-[var(--text-secondary)] leading-relaxed mb-10">
              Most RAG stacks drown in 10GB CUDA drivers, single-agent bottlenecks, and ungrounded hallucinations.
              FusionRAG pairs a Kahn's-algorithm DAG with a 4-stage hybrid fusion retriever (Dense Vector + BM25 + Cross-Encoder)
              delivering 4.0x parallel speedup and mathematical citation provenance.
            </p>

            {/* CTA Group */}
            <div className="flex flex-wrap items-center justify-center gap-4 mb-16">
              <Link
                to={isAuthenticated ? "/chat" : "/register"}
                className="inline-flex items-center gap-2.5 rounded-[var(--radius-xl)] bg-[image:var(--gradient-main)] px-7 py-3.5 text-sm font-bold text-black shadow-[var(--shadow-glow)] transition-all duration-200 hover:scale-[1.02] hover:shadow-cyan-400/35 cursor-pointer"
              >
                <span>{isAuthenticated ? "Enter Chat Studio" : "Deploy Knowledge Base"}</span>
                <ArrowRight size={16} />
              </Link>
              <a
                href="#interactive-demo"
                className="inline-flex items-center gap-2 rounded-[var(--radius-xl)] border border-[var(--border-default)] bg-[var(--bg-secondary)]/80 px-6 py-3.5 text-sm font-semibold text-[var(--text-primary)] transition-all duration-200 hover:bg-[var(--bg-tertiary)] hover:border-[var(--border-hover)]"
              >
                <Terminal size={15} className="text-[var(--accent-primary)]" />
                <span>Inspect Live Pipeline</span>
              </a>
            </div>

            {/* Live Interactive Product UI Preview (House Rule 2 & 7: Real Product UI) */}
            <div
              id="interactive-demo"
              className="w-full max-w-5xl rounded-[var(--radius-2xl)] border border-[var(--border-cyan)] bg-[var(--bg-secondary)]/95 shadow-[var(--elevation-md)] overflow-hidden text-left"
            >
              {/* Window Header */}
              <div className="flex flex-wrap items-center justify-between border-b border-[var(--border-subtle)] bg-[var(--bg-tertiary)]/70 px-5 py-3">
                <div className="flex items-center gap-2">
                  <div className="h-3 w-3 rounded-full bg-[#ff5f56]/80"></div>
                  <div className="h-3 w-3 rounded-full bg-[#ffbd2e]/80"></div>
                  <div className="h-3 w-3 rounded-full bg-[#27c93f]/80"></div>
                  <span className="ml-3 font-mono text-xs text-[var(--text-muted)]">
                    fusionrag.engine // execution-trace
                  </span>
                </div>

                {/* Scenario Switcher Tabs */}
                <div className="flex items-center gap-1.5 rounded-[var(--radius-md)] bg-[var(--bg-primary)] p-1 border border-[var(--border-subtle)]">
                  <button
                    onClick={() => handleRunDemo("finance")}
                    className={`rounded px-3 py-1 text-xs font-semibold transition ${
                      activeTab === "finance"
                        ? "bg-[var(--accent-primary)] text-black"
                        : "text-[var(--text-secondary)] hover:text-white"
                    }`}
                  >
                    Financial QA
                  </button>
                  <button
                    onClick={() => handleRunDemo("technical")}
                    className={`rounded px-3 py-1 text-xs font-semibold transition ${
                      activeTab === "technical"
                        ? "bg-[var(--accent-primary)] text-black"
                        : "text-[var(--text-secondary)] hover:text-white"
                    }`}
                  >
                    Security Invariants
                  </button>
                  <button
                    onClick={() => handleRunDemo("graph")}
                    className={`rounded px-3 py-1 text-xs font-semibold transition ${
                      activeTab === "graph"
                        ? "bg-[var(--accent-primary)] text-black"
                        : "text-[var(--text-secondary)] hover:text-white"
                    }`}
                  >
                    Multi-Hop Graph
                  </button>
                </div>
              </div>

              {/* Window Body */}
              <div className="p-6 space-y-6">
                {/* Query Input Box */}
                <div className="flex items-center gap-3 rounded-[var(--radius-xl)] bg-[var(--bg-primary)] border border-[var(--border-subtle)] px-4 py-3">
                  <span className="font-mono text-xs text-[var(--accent-primary)] font-bold">QUERY&gt;</span>
                  <span className="font-mono text-sm text-white flex-1 truncate">{currentDemo.query}</span>
                  <span className="text-[10px] uppercase font-mono px-2 py-0.5 rounded bg-[var(--accent-primary)]/10 text-[var(--accent-primary)] border border-[var(--border-cyan)]">
                    4.0x speedup
                  </span>
                </div>

                {/* Grid: Agents Dispatched + Retrieval Pipeline */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {/* Left: MasterAgent DAG Wave */}
                  <div className="rounded-[var(--radius-lg)] bg-[var(--bg-tertiary)]/50 border border-[var(--border-subtle)] p-4 space-y-3">
                    <div className="flex items-center justify-between text-xs font-semibold text-[var(--text-secondary)] uppercase tracking-wider">
                      <span className="flex items-center gap-1.5">
                        <GitBranch size={13} className="text-[var(--accent-primary)]" />
                        MasterAgent Dynamic DAG
                      </span>
                      <span className="text-[var(--accent-success)]">Kahn Cycle-Free</span>
                    </div>

                    <div className="space-y-2">
                      {currentDemo.agents.map((agent, i) => (
                        <div
                          key={i}
                          className="flex items-center justify-between rounded-[var(--radius-md)] bg-[var(--bg-primary)]/80 border border-[var(--border-subtle)] px-3 py-2 text-xs"
                        >
                          <div className="flex items-center gap-2">
                            <span className="text-[var(--accent-primary)] font-mono font-bold">⚡</span>
                            <span className="font-semibold text-white">{agent.name}</span>
                            <span className="text-[var(--text-muted)] text-[11px] hidden sm:inline">
                              ({agent.role})
                            </span>
                          </div>
                          <div className="flex items-center gap-2">
                            <span className="text-[10px] font-mono text-[var(--accent-secondary)]">{agent.time}</span>
                            <CheckCircle2 size={13} className="text-[var(--accent-success)]" />
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Right: 4-Stage Fusion Stage */}
                  <div className="rounded-[var(--radius-lg)] bg-[var(--bg-tertiary)]/50 border border-[var(--border-subtle)] p-4 space-y-3">
                    <div className="flex items-center justify-between text-xs font-semibold text-[var(--text-secondary)] uppercase tracking-wider">
                      <span className="flex items-center gap-1.5">
                        <Layers size={13} className="text-[var(--accent-primary)]" />
                        4-Stage Hybrid Fusion Engine
                      </span>
                      <span className="text-[var(--accent-primary)]">Score: 0.988</span>
                    </div>

                    <div className="space-y-1.5 font-mono text-xs">
                      <div className="flex justify-between rounded bg-[var(--bg-primary)]/80 px-2.5 py-1.5 border border-[var(--border-subtle)]">
                        <span className="text-[var(--text-secondary)]">Branch 1 (Dense):</span>
                        <span className="text-white">{currentDemo.retrieval.vector}</span>
                      </div>
                      <div className="flex justify-between rounded bg-[var(--bg-primary)]/80 px-2.5 py-1.5 border border-[var(--border-subtle)]">
                        <span className="text-[var(--text-secondary)]">Branch 2 (Lexical):</span>
                        <span className="text-white">{currentDemo.retrieval.sparse}</span>
                      </div>
                      <div className="flex justify-between rounded bg-[var(--bg-primary)]/80 px-2.5 py-1.5 border border-[var(--border-subtle)]">
                        <span className="text-[var(--accent-secondary)]">Reciprocal Rank:</span>
                        <span className="text-white">{currentDemo.retrieval.fusion}</span>
                      </div>
                      <div className="flex justify-between rounded bg-[var(--bg-primary)]/80 px-2.5 py-1.5 border border-[var(--border-cyan)]">
                        <span className="text-[var(--accent-primary)] font-bold">Jina Reranker v2:</span>
                        <span className="text-[var(--accent-primary)] font-bold">{currentDemo.retrieval.rerank}</span>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Grounded Streaming Result with Provenance Badges */}
                <div className="rounded-[var(--radius-xl)] bg-[var(--bg-primary)] border border-[var(--border-cyan)] p-4 space-y-3">
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-semibold text-white flex items-center gap-2">
                      <Sparkles size={14} className="text-[var(--accent-primary)]" />
                      Grounded Synthesis with Strict XML Context Isolation
                    </span>
                    <span className="font-mono text-[11px] text-[var(--accent-primary)]">&lt;10ms L3 cache hit</span>
                  </div>

                  <p className="text-sm text-[var(--text-primary)] leading-relaxed">{currentDemo.answer}</p>

                  <div className="flex flex-wrap items-center gap-2 pt-1 border-t border-[var(--border-subtle)]">
                    <span className="text-xs font-semibold text-[var(--text-muted)]">Verified Citations:</span>
                    {currentDemo.citations.map((cite, i) => (
                      <span
                        key={i}
                        className="inline-flex items-center gap-1.5 rounded-[var(--radius-md)] bg-[var(--accent-primary)]/10 border border-[var(--border-cyan)] px-2.5 py-1 text-xs text-[var(--accent-secondary)] font-mono"
                      >
                        <FileText size={11} />
                        <span>[{cite.id}]</span>
                        <span className="text-white font-sans">{cite.label}</span>
                        <span className="text-[var(--text-muted)]">({cite.page})</span>
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* =========================================================================
            SECTION 2: MULTI-AGENT DAG ORCHESTRATION ARCHITECTURE (Bento Grid)
           ========================================================================= */}
        <section id="agents" className="py-24 px-6 border-b border-[var(--border-subtle)] bg-[var(--bg-secondary)]/40">
          <div className="mx-auto max-w-7xl">
            <div className="text-center max-w-3xl mx-auto mb-16">
              <div className="inline-flex items-center gap-2 rounded-full border border-[var(--border-subtle)] bg-[var(--bg-tertiary)] px-3.5 py-1 text-xs font-semibold text-[var(--accent-secondary)] mb-4">
                <GitBranch size={13} />
                <span>Hierarchical Multi-Agent Subsystem</span>
              </div>
              <h2 className="font-title text-3xl sm:text-5xl font-bold text-white mb-4">
                7 Production-Wired Specialist Agents.
              </h2>
              <p className="text-base text-[var(--text-secondary)] leading-relaxed">
                Rather than treating retrieval as a single linear prompt, MasterAgent decomposes user queries
                into dependency-aware ExecutionPlans with Kahn's cycle prevention, running specialists in topological waves.
              </p>
            </div>

            {/* Bento Grid */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              {/* Agent 1 */}
              <div className="rounded-[var(--radius-xl)] bg-[var(--bg-primary)] border border-[var(--border-subtle)] p-6 transition duration-200 hover:-translate-y-1 hover:border-[var(--border-cyan)] hover:shadow-[var(--shadow-glow)]">
                <div className="flex h-12 w-12 items-center justify-center rounded-[var(--radius-lg)] bg-[var(--accent-primary)]/10 text-[var(--accent-primary)] border border-[var(--border-cyan)] mb-5">
                  <Search size={22} />
                </div>
                <h3 className="font-title text-xl font-bold text-white mb-2">ResearchAgent</h3>
                <p className="text-sm text-[var(--text-secondary)] leading-relaxed mb-4">
                  4-stage hybrid Fusion RAG combining Dense Qdrant vectors with Sparse BM25, Reciprocal Rank Fusion, MMR diversification, and Cross-Encoder attention.
                </p>
                <div className="flex flex-wrap gap-1.5 font-mono text-[11px] text-[var(--accent-secondary)]">
                  <span className="rounded bg-[var(--bg-tertiary)] px-2 py-0.5 border border-[var(--border-subtle)]">Qdrant ANN</span>
                  <span className="rounded bg-[var(--bg-tertiary)] px-2 py-0.5 border border-[var(--border-subtle)]">BM25 Sparse</span>
                  <span className="rounded bg-[var(--bg-tertiary)] px-2 py-0.5 border border-[var(--border-subtle)]">MMR (λ=0.5)</span>
                </div>
              </div>

              {/* Agent 2 */}
              <div className="rounded-[var(--radius-xl)] bg-[var(--bg-primary)] border border-[var(--border-subtle)] p-6 transition duration-200 hover:-translate-y-1 hover:border-[var(--border-cyan)] hover:shadow-[var(--shadow-glow)]">
                <div className="flex h-12 w-12 items-center justify-center rounded-[var(--radius-lg)] bg-[var(--accent-primary)]/10 text-[var(--accent-primary)] border border-[var(--border-cyan)] mb-5">
                  <Network size={22} />
                </div>
                <h3 className="font-title text-xl font-bold text-white mb-2">GraphAgent</h3>
                <p className="text-sm text-[var(--text-secondary)] leading-relaxed mb-4">
                  Executes multi-hop Knowledge Graph traversal across normalized entity triples, mentions, and confidence scores via PostgresGraphRetriever.
                </p>
                <div className="flex flex-wrap gap-1.5 font-mono text-[11px] text-[var(--accent-secondary)]">
                  <span className="rounded bg-[var(--bg-tertiary)] px-2 py-0.5 border border-[var(--border-subtle)]">3-Hop Traversal</span>
                  <span className="rounded bg-[var(--bg-tertiary)] px-2 py-0.5 border border-[var(--border-subtle)]">Entity Triples</span>
                  <span className="rounded bg-[var(--bg-tertiary)] px-2 py-0.5 border border-[var(--border-subtle)]">Idempotent</span>
                </div>
              </div>

              {/* Agent 3 */}
              <div className="rounded-[var(--radius-xl)] bg-[var(--bg-primary)] border border-[var(--border-subtle)] p-6 transition duration-200 hover:-translate-y-1 hover:border-[var(--border-cyan)] hover:shadow-[var(--shadow-glow)]">
                <div className="flex h-12 w-12 items-center justify-center rounded-[var(--radius-lg)] bg-[var(--accent-primary)]/10 text-[var(--accent-primary)] border border-[var(--border-cyan)] mb-5">
                  <Terminal size={22} />
                </div>
                <h3 className="font-title text-xl font-bold text-white mb-2">AnalysisAgent</h3>
                <p className="text-sm text-[var(--text-secondary)] leading-relaxed mb-4">
                  AST-sandboxed symbolic mathematics and SafeCalculator execution, calculating growth rates, compound metrics, and ratio bounds with zero eval() risk.
                </p>
                <div className="flex flex-wrap gap-1.5 font-mono text-[11px] text-[var(--accent-secondary)]">
                  <span className="rounded bg-[var(--bg-tertiary)] px-2 py-0.5 border border-[var(--border-subtle)]">AST Sandboxed</span>
                  <span className="rounded bg-[var(--bg-tertiary)] px-2 py-0.5 border border-[var(--border-subtle)]">SafeCalculator</span>
                  <span className="rounded bg-[var(--bg-tertiary)] px-2 py-0.5 border border-[var(--border-subtle)]">CAGR Engine</span>
                </div>
              </div>

              {/* Agent 4 */}
              <div className="rounded-[var(--radius-xl)] bg-[var(--bg-primary)] border border-[var(--border-subtle)] p-6 transition duration-200 hover:-translate-y-1 hover:border-[var(--border-cyan)] hover:shadow-[var(--shadow-glow)]">
                <div className="flex h-12 w-12 items-center justify-center rounded-[var(--radius-lg)] bg-[var(--accent-primary)]/10 text-[var(--accent-primary)] border border-[var(--border-cyan)] mb-5">
                  <Layers size={22} />
                </div>
                <h3 className="font-title text-xl font-bold text-white mb-2">TableAgent</h3>
                <p className="text-sm text-[var(--text-secondary)] leading-relaxed mb-4">
                  Structured table element extraction and upstream DAG SQL aggregation (SUM, AVG, MIN, MAX, CAGR) directly parsing multi-format Markdown and CSV tables.
                </p>
                <div className="flex flex-wrap gap-1.5 font-mono text-[11px] text-[var(--accent-secondary)]">
                  <span className="rounded bg-[var(--bg-tertiary)] px-2 py-0.5 border border-[var(--border-subtle)]">SQL Aggregation</span>
                  <span className="rounded bg-[var(--bg-tertiary)] px-2 py-0.5 border border-[var(--border-subtle)]">CSV Parser</span>
                  <span className="rounded bg-[var(--bg-tertiary)] px-2 py-0.5 border border-[var(--border-subtle)]">Element Store</span>
                </div>
              </div>

              {/* Agent 5 */}
              <div className="rounded-[var(--radius-xl)] bg-[var(--bg-primary)] border border-[var(--border-subtle)] p-6 transition duration-200 hover:-translate-y-1 hover:border-[var(--border-cyan)] hover:shadow-[var(--shadow-glow)]">
                <div className="flex h-12 w-12 items-center justify-center rounded-[var(--radius-lg)] bg-[var(--accent-primary)]/10 text-[var(--accent-primary)] border border-[var(--border-cyan)] mb-5">
                  <Cpu size={22} />
                </div>
                <h3 className="font-title text-xl font-bold text-white mb-2">VisionAgent</h3>
                <p className="text-sm text-[var(--text-secondary)] leading-relaxed mb-4">
                  Multimodal diagram OCR transcription, chart trend reasoning, and visual figure analysis cached per page image hash to avoid redundant API fees.
                </p>
                <div className="flex flex-wrap gap-1.5 font-mono text-[11px] text-[var(--accent-secondary)]">
                  <span className="rounded bg-[var(--bg-tertiary)] px-2 py-0.5 border border-[var(--border-subtle)]">OCR Cache</span>
                  <span className="rounded bg-[var(--bg-tertiary)] px-2 py-0.5 border border-[var(--border-subtle)]">Diagram Vision</span>
                  <span className="rounded bg-[var(--bg-tertiary)] px-2 py-0.5 border border-[var(--border-subtle)]">SHA-256 Keys</span>
                </div>
              </div>

              {/* Agent 6 & 7 Unified */}
              <div className="rounded-[var(--radius-xl)] bg-[var(--bg-primary)] border border-[var(--border-subtle)] p-6 transition duration-200 hover:-translate-y-1 hover:border-[var(--border-cyan)] hover:shadow-[var(--shadow-glow)]">
                <div className="flex h-12 w-12 items-center justify-center rounded-[var(--radius-lg)] bg-[var(--accent-primary)]/10 text-[var(--accent-primary)] border border-[var(--border-cyan)] mb-5">
                  <ShieldCheck size={22} />
                </div>
                <h3 className="font-title text-xl font-bold text-white mb-2">Document & WebSearch</h3>
                <p className="text-sm text-[var(--text-secondary)] leading-relaxed mb-4">
                  DocumentAgent validates strict tenant ownership and chunk windows, while WebSearchAgent gates off-domain noise for real-time fact checks.
                </p>
                <div className="flex flex-wrap gap-1.5 font-mono text-[11px] text-[var(--accent-secondary)]">
                  <span className="rounded bg-[var(--bg-tertiary)] px-2 py-0.5 border border-[var(--border-subtle)]">Tenant Gating</span>
                  <span className="rounded bg-[var(--bg-tertiary)] px-2 py-0.5 border border-[var(--border-subtle)]">Domain Gate</span>
                  <span className="rounded bg-[var(--bg-tertiary)] px-2 py-0.5 border border-[var(--border-subtle)]">Sentence Window</span>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* =========================================================================
            SECTION 3: 4-STAGE RETRIEVAL FUSION VS CONVENTIONAL RAG
           ========================================================================= */}
        <section id="retrieval" className="py-24 px-6 border-b border-[var(--border-subtle)]">
          <div className="mx-auto max-w-7xl">
            <div className="text-center max-w-3xl mx-auto mb-16">
              <div className="inline-flex items-center gap-2 rounded-full border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3.5 py-1 text-xs font-semibold text-[var(--accent-primary)] mb-4">
                <Layers size={13} />
                <span>Eliminating Hallucinations</span>
              </div>
              <h2 className="font-title text-3xl sm:text-5xl font-bold text-white mb-4">
                Why Naive Vector Search Fails.
              </h2>
              <p className="text-base text-[var(--text-secondary)] leading-relaxed">
                Vector embeddings alone fail on exact part numbers, contract clauses, and specific figures.
                FusionRAG resolves this with a 4-stage multi-branch pipeline.
              </p>
            </div>

            {/* Pipeline Step Blocks */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <div className="rounded-[var(--radius-xl)] bg-[var(--bg-secondary)] border border-[var(--border-subtle)] p-6">
                <span className="font-mono text-xs font-bold text-[var(--accent-secondary)] block mb-2">STAGE 01</span>
                <h4 className="font-title text-lg font-bold text-white mb-2">Multi-Branch Candidate Retrieval</h4>
                <p className="text-xs text-[var(--text-secondary)] leading-relaxed">
                  Concurrently queries Qdrant (cosine ANN vector search) and native PostgreSQL Full-Text Search with GIN indexes.
                </p>
              </div>

              <div className="rounded-[var(--radius-xl)] bg-[var(--bg-secondary)] border border-[var(--border-subtle)] p-6">
                <span className="font-mono text-xs font-bold text-[var(--accent-secondary)] block mb-2">STAGE 02</span>
                <h4 className="font-title text-lg font-bold text-white mb-2">Reciprocal Rank Fusion (RRF)</h4>
                <p className="text-xs text-[var(--text-secondary)] leading-relaxed">
                  Fuses candidate rankings without score scale mismatch: <code>RRF(d) = Σ 1 / (60 + r(d))</code> for seamless ranking unification.
                </p>
              </div>

              <div className="rounded-[var(--radius-xl)] bg-[var(--bg-secondary)] border border-[var(--border-subtle)] p-6">
                <span className="font-mono text-xs font-bold text-[var(--accent-secondary)] block mb-2">STAGE 03</span>
                <h4 className="font-title text-lg font-bold text-white mb-2">Maximal Marginal Relevance (MMR)</h4>
                <p className="text-xs text-[var(--text-secondary)] leading-relaxed">
                  Penalizes informational redundancy (λ=0.5), selecting candidate passages that maximize unique information coverage.
                </p>
              </div>

              <div className="rounded-[var(--radius-xl)] bg-[var(--bg-secondary)] border border-[var(--border-cyan)] p-6 bg-[var(--bg-tertiary)] shadow-[var(--shadow-glow)]">
                <span className="font-mono text-xs font-bold text-[var(--accent-primary)] block mb-2">STAGE 04</span>
                <h4 className="font-title text-lg font-bold text-white mb-2">Neural Cross-Encoder Reranking</h4>
                <p className="text-xs text-[var(--text-secondary)] leading-relaxed">
                  Runs deep cross-attention via Jina v2 multilingual reranker bounded by asyncio semaphores, isolating true semantic matches.
                </p>
              </div>
            </div>

            {/* Comparison Table */}
            <div className="mt-12 overflow-x-auto rounded-[var(--radius-xl)] border border-[var(--border-subtle)] bg-[var(--bg-secondary)]/70">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-[var(--border-subtle)] bg-[var(--bg-tertiary)] font-title text-xs font-bold uppercase tracking-wider text-[var(--text-muted)]">
                  <tr>
                    <th className="px-6 py-4">Capability</th>
                    <th className="px-6 py-4">Naive Vector RAG</th>
                    <th className="px-6 py-4">Pure Keyword BM25</th>
                    <th className="px-6 py-4 text-[var(--accent-primary)]">FusionRAG Hybrid</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[var(--border-subtle)] text-xs font-medium">
                  <tr>
                    <td className="px-6 py-3.5 font-semibold text-white">Exact SKU &amp; ID Lookup</td>
                    <td className="px-6 py-3.5 text-red-400">Poor (Cosine drift)</td>
                    <td className="px-6 py-3.5 text-emerald-400">Excellent</td>
                    <td className="px-6 py-3.5 text-[var(--accent-primary)] font-bold">Flawless (BM25 Branch)</td>
                  </tr>
                  <tr>
                    <td className="px-6 py-3.5 font-semibold text-white">Conceptual Paraphrasing</td>
                    <td className="px-6 py-3.5 text-emerald-400">Good</td>
                    <td className="px-6 py-3.5 text-red-400">Fails (Token mismatch)</td>
                    <td className="px-6 py-3.5 text-[var(--accent-primary)] font-bold">Flawless (Dense ANN)</td>
                  </tr>
                  <tr>
                    <td className="px-6 py-3.5 font-semibold text-white">Passage Redundancy Filter</td>
                    <td className="px-6 py-3.5 text-red-400">None (Duplicate chunks)</td>
                    <td className="px-6 py-3.5 text-red-400">None</td>
                    <td className="px-6 py-3.5 text-[var(--accent-primary)] font-bold">MMR Diversity Filter (λ=0.5)</td>
                  </tr>
                  <tr>
                    <td className="px-6 py-3.5 font-semibold text-white">Cross-Attention Scoring</td>
                    <td className="px-6 py-3.5 text-red-400">Bi-encoder only</td>
                    <td className="px-6 py-3.5 text-red-400">None</td>
                    <td className="px-6 py-3.5 text-[var(--accent-primary)] font-bold">Jina Cross-Encoder v2</td>
                  </tr>
                  <tr>
                    <td className="px-6 py-3.5 font-semibold text-white">Local Weight Footprint</td>
                    <td className="px-6 py-3.5 text-amber-400">4GB – 12GB PyTorch</td>
                    <td className="px-6 py-3.5 text-emerald-400">&lt;100MB</td>
                    <td className="px-6 py-3.5 text-[var(--accent-primary)] font-bold">Zero Local Weights (&lt;450MB)</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </section>

        {/* =========================================================================
            SECTION 4: ENCRYPTED MULTI-TIER CACHING & CRYPTO-SHREDDING
           ========================================================================= */}
        <section id="caching" className="py-24 px-6 border-b border-[var(--border-subtle)] bg-[var(--bg-secondary)]/30">
          <div className="mx-auto max-w-7xl">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-12 items-center">
              <div>
                <div className="inline-flex items-center gap-2 rounded-full border border-[var(--border-cyan)] bg-[var(--bg-tertiary)] px-3.5 py-1 text-xs font-semibold text-[var(--accent-secondary)] mb-4">
                  <Lock size={13} />
                  <span>Enterprise Data Security</span>
                </div>
                <h2 className="font-title text-3xl sm:text-5xl font-bold text-white mb-6 leading-tight">
                  Sub-10ms Answers with Active-Version Invalidation.
                </h2>
                <p className="text-base text-[var(--text-secondary)] leading-relaxed mb-6">
                  Traditional RAG caches suffer from stale answers whenever underlying files change.
                  FusionRAG keys its L3 response cache on a composite hash of all authorized documents:
                  <code>(doc_id, active_version)</code>. Any file edit, re-indexing, or deletion instantly
                  invalidates dependent cache entries.
                </p>

                <div className="space-y-4 font-sans text-sm">
                  <div className="flex items-start gap-3">
                    <CheckCircle2 size={18} className="text-[var(--accent-primary)] mt-0.5 flex-shrink-0" />
                    <div>
                      <strong className="text-white">L1/L2/L3 Multi-Tier Architecture:</strong> In-memory LRU process cache (L1), distributed Redis (L2), and Encrypted RAG Response Cache (L3).
                    </div>
                  </div>
                  <div className="flex items-start gap-3">
                    <CheckCircle2 size={18} className="text-[var(--accent-primary)] mt-0.5 flex-shrink-0" />
                    <div>
                      <strong className="text-white">AES-256-GCM Envelope Encryption:</strong> Cached responses in Redis are sealed with user-specific Data Encryption Keys.
                    </div>
                  </div>
                  <div className="flex items-start gap-3">
                    <CheckCircle2 size={18} className="text-[var(--accent-primary)] mt-0.5 flex-shrink-0" />
                    <div>
                      <strong className="text-white">Instant Crypto-Shredding:</strong> Deleting an account destroys the user DEK, mathematically shredding all cached ciphertext in milliseconds.
                    </div>
                  </div>
                </div>
              </div>

              {/* Cache Pipeline Diagram */}
              <div className="rounded-[var(--radius-2xl)] border border-[var(--border-subtle)] bg-[var(--bg-primary)] p-6 shadow-xl">
                <div className="flex items-center justify-between border-b border-[var(--border-subtle)] pb-4 mb-6">
                  <span className="font-mono text-xs text-[var(--accent-primary)] font-bold">CACHE HIERARCHY FLOW</span>
                  <span className="text-[10px] uppercase font-mono px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                    Zero Stale Data
                  </span>
                </div>

                <div className="space-y-3 font-mono text-xs">
                  <div className="rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-3">
                    <div className="flex justify-between text-[var(--accent-secondary)] mb-1">
                      <span>L1 In-Memory Process LRU</span>
                      <span>&lt;0.5ms</span>
                    </div>
                    <p className="text-[11px] text-[var(--text-muted)] font-sans">
                      Python process cache for query decomposition heuristics and classification.
                    </p>
                  </div>

                  <div className="rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-3">
                    <div className="flex justify-between text-[var(--accent-secondary)] mb-1">
                      <span>L2 Distributed Redis Stream &amp; Session</span>
                      <span>1.8ms</span>
                    </div>
                    <p className="text-[11px] text-[var(--text-muted)] font-sans">
                      Consumer groups (group:document_workers) with background durable ingestion reap.
                    </p>
                  </div>

                  <div className="rounded-[var(--radius-lg)] border border-[var(--border-cyan)] bg-[var(--bg-tertiary)] p-4 shadow-[var(--shadow-glow)]">
                    <div className="flex justify-between text-[var(--accent-primary)] font-bold mb-1">
                      <span>L3 Encrypted RAG Cache (AES-256-GCM)</span>
                      <span>8.2ms</span>
                    </div>
                    <p className="text-[11px] text-[var(--text-secondary)] font-sans mb-2">
                      Full synthesized answer + citation metadata replayed via synthetic paced SSE streaming.
                    </p>
                    <div className="text-[10px] bg-[var(--bg-primary)] px-2 py-1 rounded text-[var(--text-muted)]">
                      Key: SHA256(user_id + query + hash(doc1:v3, doc2:v1))
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* =========================================================================
            SECTION 5: AUTOMATED EVALUATIONS & AUDITING (DeepEval + Ragas)
           ========================================================================= */}
        <section id="evaluation" className="py-24 px-6 border-b border-[var(--border-subtle)]">
          <div className="mx-auto max-w-7xl text-center">
            <div className="inline-flex items-center gap-2 rounded-full border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3.5 py-1 text-xs font-semibold text-[var(--accent-primary)] mb-4">
              <ShieldCheck size={13} />
              <span>Observable Quality Benchmarks</span>
            </div>
            <h2 className="font-title text-3xl sm:text-5xl font-bold text-white mb-4">
              Continuous Quality Evaluations.
            </h2>
            <p className="text-base text-[var(--text-secondary)] max-w-2xl mx-auto mb-16 leading-relaxed">
              Every release is audited against golden test sets using automated DeepEval and Ragas pipelines,
              tracking faithfulness, answer relevancy, and context recall over time.
            </p>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
              <div className="rounded-[var(--radius-xl)] bg-[var(--bg-secondary)] border border-[var(--border-subtle)] p-6 text-center">
                <span className="font-title text-4xl font-extrabold text-[var(--accent-primary)] block mb-1">0.96</span>
                <span className="text-sm font-semibold text-white block mb-1">Faithfulness</span>
                <p className="text-xs text-[var(--text-muted)]">Zero ungrounded hallucinations against retrieved context</p>
              </div>

              <div className="rounded-[var(--radius-xl)] bg-[var(--bg-secondary)] border border-[var(--border-subtle)] p-6 text-center">
                <span className="font-title text-4xl font-extrabold text-[var(--accent-primary)] block mb-1">0.94</span>
                <span className="text-sm font-semibold text-white block mb-1">Answer Relevancy</span>
                <p className="text-xs text-[var(--text-muted)]">Precise intent satisfaction without circular verbosity</p>
              </div>

              <div className="rounded-[var(--radius-xl)] bg-[var(--bg-secondary)] border border-[var(--border-subtle)] p-6 text-center">
                <span className="font-title text-4xl font-extrabold text-[var(--accent-primary)] block mb-1">0.92</span>
                <span className="text-sm font-semibold text-white block mb-1">Context Precision</span>
                <p className="text-xs text-[var(--text-muted)]">Cross-encoder reranker places ground-truth passage in rank 1</p>
              </div>

              <div className="rounded-[var(--radius-xl)] bg-[var(--bg-secondary)] border border-[var(--border-subtle)] p-6 text-center">
                <span className="font-title text-4xl font-extrabold text-emerald-400 block mb-1">&lt;0.02</span>
                <span className="text-sm font-semibold text-white block mb-1">Hallucination Rate</span>
                <p className="text-xs text-[var(--text-muted)]">Strict XML context boundaries eliminate false claims</p>
              </div>
            </div>
          </div>
        </section>

        {/* =========================================================================
            SECTION 6: CALL TO ACTION — CLEAN & DIRECT
           ========================================================================= */}
        <section className="py-24 px-6 relative overflow-hidden text-center">
          <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(0,210,253,0.08)_0%,transparent_60%)]"></div>

          <div className="mx-auto max-w-4xl relative z-10">
            <h2 className="font-title text-4xl sm:text-6xl font-extrabold text-white mb-6 leading-tight">
              Ready to Upgrade Your Retrieval Architecture?
            </h2>
            <p className="text-base sm:text-lg text-[var(--text-secondary)] mb-10 max-w-2xl mx-auto">
              Start indexing documents in seconds. Experience multi-agent DAG execution, 4-stage hybrid fusion, and sub-10ms cached answers.
            </p>

            <div className="flex flex-wrap items-center justify-center gap-4">
              <Link
                to={isAuthenticated ? "/chat" : "/register"}
                className="inline-flex items-center gap-2.5 rounded-[var(--radius-xl)] bg-[image:var(--gradient-main)] px-8 py-4 text-sm font-bold text-black shadow-[var(--shadow-glow)] transition-all duration-200 hover:scale-[1.02] hover:shadow-cyan-400/40 cursor-pointer"
              >
                <span>{isAuthenticated ? "Launch Chat Studio" : "Get Started Now"}</span>
                <ArrowRight size={16} />
              </Link>
              <Link
                to="/login"
                className="inline-flex items-center gap-2 rounded-[var(--radius-xl)] border border-[var(--border-default)] bg-[var(--bg-secondary)] px-7 py-4 text-sm font-semibold text-white transition hover:bg-[var(--bg-tertiary)]"
              >
                <span>Existing User Sign In</span>
              </Link>
            </div>
          </div>
        </section>
      </main>

      {/* Footer */}
      <footer className="border-t border-[var(--border-subtle)] bg-[var(--bg-primary)] px-6 py-12">
        <div className="mx-auto max-w-7xl flex flex-col md:flex-row items-center justify-between gap-6 text-xs text-[var(--text-muted)]">
          <div className="flex items-center gap-3">
            <div className="flex h-6 w-6 items-center justify-center rounded-[var(--radius-md)] bg-[image:var(--gradient-main)] text-white text-[11px] font-bold font-title">
              F
            </div>
            <span className="font-title font-semibold text-white">FusionRAG</span>
            <span>—</span>
            <span>Production-Grade Hybrid Retrieval &amp; Multi-Agent Intelligence</span>
          </div>

          <div className="flex items-center gap-6">
            <Link to="/login" className="hover:text-white transition">
              Sign In
            </Link>
            <Link to="/register" className="hover:text-white transition">
              Register
            </Link>
            <a
              href="https://fusionrag.vercel.app"
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-white transition"
            >
              Live Demo
            </a>
            <span className="inline-flex items-center gap-1.5 text-emerald-400">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
              All Systems Operational
            </span>
          </div>
        </div>
      </footer>
    </div>
  );
};

export default LandingPage;
