import { Suspense } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider } from "./context/AuthContext";
import { UploadQueueProvider } from "./context/UploadQueueContext";
import { ThemeProvider } from "./context/ThemeContext";
import { LoginForm } from "./components/auth/LoginForm";
import { RegisterForm } from "./components/auth/RegisterForm";
import { ProtectedRoute } from "./routes/ProtectedRoute";
import { PublicRoute } from "./routes/PublicRoute";
import { ChatLayout } from "./components/layout/ChatLayout";
import { ErrorBoundary } from "./components/error/ErrorBoundary";
import { ErrorPage } from "./components/error/ErrorPage";
import { Toaster } from "react-hot-toast";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { lazyWithRetry } from "./utils/lazyWithRetry";

// Lazy-loaded pages with auto-recovery on new deployment chunk rotations
const ChatPage = lazyWithRetry(() => import("./pages/ChatPage"));
const DocumentsPage = lazyWithRetry(() => import("./pages/DocumentsPage"));
const SettingsPage = lazyWithRetry(() => import("./pages/SettingsPage"));
const OAuthCallbackPage = lazyWithRetry(() => import("./pages/OAuthCallbackPage"));
const AdminDashboardPage = lazyWithRetry(() => import("./pages/AdminDashboardPage"));
const VerifyEmailPage = lazyWithRetry(() => import("./pages/VerifyEmailPage"));

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
      staleTime: 5 * 60 * 1000, // 5 minutes
    },
  },
});

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <BrowserRouter>
          <AuthProvider>
            {/* Above <Routes> (and the lazy-page Suspense) so the upload queue
                survives navigation — in-flight uploads keep processing in the
                background wherever the user goes. */}
            <UploadQueueProvider>
            <Suspense
              fallback={
                <div className="flex h-dvh w-dvw items-center justify-center bg-[var(--bg-primary)] text-[var(--text-primary)]">
                  <div className="flex flex-col items-center gap-3">
                    <div className="h-8 w-8 animate-spin rounded-full border-2 border-[var(--accent-primary)] border-t-transparent"></div>
                    <p className="text-xs text-[var(--text-secondary)] font-medium">Loading Hybrid RAG...</p>
                  </div>
                </div>
              }
            >
              <Routes>
                {/* Public guest-only routes */}
                <Route element={<PublicRoute />}>
                  <Route path="/login" element={<LoginForm />} />
                  <Route path="/register" element={<RegisterForm />} />
                  <Route path="/verify-email" element={<VerifyEmailPage />} />
                </Route>

                {/* Secure application routes */}
                <Route element={<ProtectedRoute />}>
                  <Route element={<ChatLayout />}>
                    <Route index element={<Navigate to="/chat" replace />} />
                    <Route
                      path="/chat"
                      element={
                        <ErrorBoundary>
                          <ChatPage />
                        </ErrorBoundary>
                      }
                    />
                    <Route
                      path="/chat/:conversationId"
                      element={
                        <ErrorBoundary>
                          <ChatPage />
                        </ErrorBoundary>
                      }
                    />
                    <Route
                      path="/documents"
                      element={
                        <ErrorBoundary>
                          <DocumentsPage />
                        </ErrorBoundary>
                      }
                    />
                    <Route
                      path="/settings"
                      element={
                        <ErrorBoundary>
                          <SettingsPage />
                        </ErrorBoundary>
                      }
                    />
                    <Route
                      path="/admin/dashboard"
                      element={
                        <ErrorBoundary>
                          <AdminDashboardPage />
                        </ErrorBoundary>
                      }
                    />
                  </Route>
                </Route>

                {/* OAuth callback — must be outside both Public and Protected
                    guards so it is reachable immediately after redirect */}
                <Route path="/oauth/callback" element={<OAuthCallbackPage />} />

                {/* Fallbacks */}
                <Route path="/401" element={<ErrorPage status={401} />} />
                <Route path="/403" element={<ErrorPage status={403} />} />
                <Route path="/500" element={<ErrorPage status={500} />} />
                <Route path="*" element={<ErrorPage status={404} />} />
              </Routes>
            </Suspense>
            </UploadQueueProvider>
            <Toaster
              position="bottom-right"
              toastOptions={{
                className: "bg-[var(--bg-elevated)] border border-[var(--border-default)] text-[var(--text-primary)] text-xs font-medium shadow-sm",
                duration: 4000,
              }}
            />
          </AuthProvider>
        </BrowserRouter>
      </ThemeProvider>
    </QueryClientProvider>
  );
}

export default App;
