import { act, render, renderHook, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { http, HttpResponse } from "msw";
import { LoginForm } from "../components/auth/LoginForm";
import { AuthProvider } from "../context/AuthContext";
import { useAuth } from "../hooks/useAuth";
import { BrowserRouter } from "react-router-dom";
import { server } from "./handlers";

describe("Login Flow Integration", () => {
  it("renders login form components correctly", () => {
    render(
      <BrowserRouter>
        <AuthProvider>
          <LoginForm />
        </AuthProvider>
      </BrowserRouter>
    );
    expect(screen.getByPlaceholderText(/Email address/i)).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/Password/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Continue/i })).toBeInTheDocument();
  });
});

describe("deleteAccount", () => {
  it("calls DELETE /auth/account and clears session state", async () => {
    let deleteCalled = false;
    server.use(
      http.delete("*/api/v1/auth/account", () => {
        deleteCalled = true;
        return new HttpResponse(null, { status: 204 });
      })
    );

    const wrapper = ({ children }: { children: ReactNode }) => (
      <AuthProvider>{children}</AuthProvider>
    );

    const { result } = renderHook(() => useAuth(), { wrapper });

    // Wait for the initial refresh + /me boot probe to complete
    await waitFor(() => {
      expect(result.current.isAuthenticated).toBe(true);
      expect(result.current.user?.email).toBe("test@example.com");
    });

    await act(async () => {
      await result.current.deleteAccount("password");
    });

    expect(deleteCalled).toBe(true);
    expect(result.current.isAuthenticated).toBe(false);
    expect(result.current.user).toBeNull();
    expect(result.current.accessToken).toBeNull();
  });
});
