import React from "react";
import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";

export const AdminRoute: React.FC = () => {
  const { user, isAuthenticated, isLoading } = useAuth();

  if (isLoading) {
    return (
      <div className="flex h-dvh w-dvw items-center justify-center bg-[var(--bg-primary)] text-[var(--text-primary)]">
        <div className="flex flex-col items-center gap-4">
          <div className="h-10 w-10 animate-spin rounded-full border-4 border-[var(--accent-primary)] border-t-transparent"></div>
          <p className="text-sm font-medium text-[var(--text-secondary)]">
            Verifying administrative access...
          </p>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  if (user?.role !== "admin") {
    return <Navigate to="/403" replace />;
  }

  return <Outlet />;
};
