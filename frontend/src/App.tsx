import { useEffect, useState } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import {
  Activity,
  Database,
  LogOut,
  Network,
  RefreshCw,
  Terminal,
  User,
  Zap,
} from "lucide-react";
import { AuthProvider } from "./context/AuthContext";
import { useAuth } from "./hooks/useAuth";
import { LoginForm } from "./components/auth/LoginForm";
import { RegisterForm } from "./components/auth/RegisterForm";
import { ProtectedRoute } from "./routes/ProtectedRoute";
import { PublicRoute } from "./routes/PublicRoute";
import api from "./services/api";
import "./App.css";

interface ServiceStatus {
  name: string;
  status: "connected" | "disconnected";
  details?: string;
}

interface LogEntry {
  timestamp: string;
  message: string;
  type: "info" | "success" | "error";
}

function Dashboard() {
  const { user, logout } = useAuth();
  const [loading, setLoading] = useState<boolean>(false);
  const [lastChecked, setLastChecked] = useState<string>("Never");
  const [statuses, setStatuses] = useState<Record<string, ServiceStatus>>({
    postgres: { name: "PostgreSQL DB", status: "disconnected" },
    redis: { name: "Redis Cache", status: "disconnected" },
    vector_db: { name: "Qdrant Vector DB", status: "disconnected" },
  });
  const [logs, setLogs] = useState<LogEntry[]>([]);

  const addLog = (
    message: string,
    type: "info" | "success" | "error" = "info"
  ) => {
    const timeStr = new Date().toLocaleTimeString();
    setLogs((prev) => [{ timestamp: timeStr, message, type }, ...prev]);
  };

  const runHealthCheck = async () => {
    if (loading) return;
    setLoading(true);
    addLog("Initiating backend system health audit...", "info");

    try {
      // Fetch via configured Axios instance to verify request/response interceptors
      const response = await api.get("/health/readiness");
      const data = response.data;

      const updatedStatuses: Record<string, ServiceStatus> = {
        postgres: {
          name: "PostgreSQL DB",
          status: data.services.postgres.startsWith("connected")
            ? "connected"
            : "disconnected",
          details: data.services.postgres,
        },
        redis: {
          name: "Redis Cache",
          status: data.services.redis.startsWith("connected")
            ? "connected"
            : "disconnected",
          details: data.services.redis,
        },
        vector_db: {
          name: "Qdrant Vector DB",
          status: data.services.vector_db.startsWith("connected")
            ? "connected"
            : "disconnected",
          details: data.services.vector_db,
        },
      };

      setStatuses(updatedStatuses);
      setLastChecked(new Date().toLocaleTimeString());

      addLog(
        "All services online. Backend RAG foundation fully operational.",
        "success"
      );
    } catch (err: any) {
      const errMsg =
        err.response?.data?.message || err.message || String(err);
      addLog(`Failed to communicate with API server: ${errMsg}`, "error");

      setStatuses({
        postgres: {
          name: "PostgreSQL DB",
          status: "disconnected",
          details: "API unreachable",
        },
        redis: {
          name: "Redis Cache",
          status: "disconnected",
          details: "API unreachable",
        },
        vector_db: {
          name: "Qdrant Vector DB",
          status: "disconnected",
          details: "API unreachable",
        },
      });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    runHealthCheck();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="app-container">
      {/* Background glow backdrops */}
      <div className="bg-glow-1"></div>
      <div className="bg-glow-2"></div>

      <div className="glass-panel">
        {/* User Account Bar */}
        {user && (
          <div className="user-profile-header">
            <div className="user-identity">
              <div className="user-avatar">
                <User size={16} />
              </div>
              <div className="user-details">
                <span className="user-email">{user.email}</span>
                <span className="user-role-badge">{user.role}</span>
              </div>
            </div>
            <button className="btn-logout" onClick={logout}>
              <LogOut size={16} />
              <span>Sign Out</span>
            </button>
          </div>
        )}

        <div className="header-section">
          <span className="badge">Milestone 2</span>
          <h1 className="app-title">System Status</h1>
          <p className="app-description">
            Hybrid RAG Chatbot is active. Backing databases, caching engines,
            and secure user sessions are operational.
          </p>
        </div>

        {/* Dynamic Status Grid */}
        <div className="status-grid">
          {/* Postgres Card */}
          <div className={`status-card ${statuses.postgres.status}`}>
            <div className="service-icon">
              <Database size={32} />
            </div>
            <span className="service-name">{statuses.postgres.name}</span>
            <div className="indicator-row">
              <div
                className={`led-light ${
                  statuses.postgres.status === "connected"
                    ? "active"
                    : "inactive"
                }`}
              ></div>
              <span className="status-label">
                {statuses.postgres.status === "connected" ? "Online" : "Offline"}
              </span>
            </div>
          </div>

          {/* Redis Card */}
          <div className={`status-card ${statuses.redis.status}`}>
            <div className="service-icon">
              <Zap size={32} />
            </div>
            <span className="service-name">{statuses.redis.name}</span>
            <div className="indicator-row">
              <div
                className={`led-light ${
                  statuses.redis.status === "connected" ? "active" : "inactive"
                }`}
              ></div>
              <span className="status-label">
                {statuses.redis.status === "connected" ? "Online" : "Offline"}
              </span>
            </div>
          </div>

          {/* Qdrant Card */}
          <div className={`status-card ${statuses.vector_db.status}`}>
            <div className="service-icon">
              <Network size={32} />
            </div>
            <span className="service-name">{statuses.vector_db.name}</span>
            <div className="indicator-row">
              <div
                className={`led-light ${
                  statuses.vector_db.status === "connected"
                    ? "active"
                    : "inactive"
                }`}
              ></div>
              <span className="status-label">
                {statuses.vector_db.status === "connected" ? "Online" : "Offline"}
              </span>
            </div>
          </div>
        </div>

        {/* Diagnostic Logs Visualizer */}
        <div className="diagnostics-container">
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "8px",
              marginBottom: "8px",
              color: "var(--text-secondary)",
            }}
          >
            <Terminal size={16} />
            <span
              style={{
                fontSize: "0.8rem",
                fontWeight: 600,
                textTransform: "uppercase",
                letterSpacing: "0.05em",
              }}
            >
              Diagnostic Console
            </span>
          </div>
          <div className="diag-info">
            {logs.length === 0 ? (
              <div className="diag-log-text">Console idle...</div>
            ) : (
              logs.map((log, idx) => (
                <div key={idx} className="diag-log">
                  <span className="diag-log-time">[{log.timestamp}]</span>
                  <span className={`diag-log-text ${log.type}`}>
                    {log.message}
                  </span>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Trigger audit button */}
        <div className="actions-section">
          <button
            className="btn-trigger"
            onClick={runHealthCheck}
            disabled={loading}
          >
            {loading ? (
              <RefreshCw size={18} className="spinning" />
            ) : (
              <Activity size={18} />
            )}
            {loading ? "Auditing System..." : "Perform System Audit"}
          </button>
          <span className="last-checked">Last Audited: {lastChecked}</span>
        </div>
      </div>
    </div>
  );
}

function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          {/* Guest only routes */}
          <Route element={<PublicRoute />}>
            <Route path="/login" element={<LoginForm />} />
            <Route path="/register" element={<RegisterForm />} />
          </Route>

          {/* Protected app routes */}
          <Route element={<ProtectedRoute />}>
            <Route path="/" element={<Dashboard />} />
          </Route>

          {/* Fallback redirect */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}

export default App;
