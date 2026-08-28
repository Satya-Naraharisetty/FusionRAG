import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { http, HttpResponse } from "msw";
import { AuthProvider } from "../context/AuthContext";
import { VerifyEmailPage } from "../pages/VerifyEmailPage";
import { server } from "./handlers";

describe("VerifyEmailPage", () => {
  it("renders 6 digit input boxes and email parameter from URL", () => {
    render(
      <MemoryRouter initialEntries={["/verify-email?email=user@example.com"]}>
        <AuthProvider>
          <Routes>
            <Route path="/verify-email" element={<VerifyEmailPage />} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    );

    expect(screen.getByText(/Verify your email/i)).toBeInTheDocument();
    expect(screen.getByText(/user@example.com/i)).toBeInTheDocument();

    const digitInputs = screen.getAllByRole("textbox", { name: /Digit/i });
    expect(digitInputs).toHaveLength(6);
  });

  it("submits 6-digit OTP code when all boxes are filled via paste or input", async () => {
    let verifyPayload: Record<string, unknown> | null = null;
    server.use(
      http.post("*/api/v1/auth/verify-email", async ({ request }) => {
        verifyPayload = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({
          access_token: "mock-verified-token",
          expires_in: 3600,
        });
      })
    );

    render(
      <MemoryRouter initialEntries={["/verify-email?email=otpuser@example.com"]}>
        <AuthProvider>
          <Routes>
            <Route path="/verify-email" element={<VerifyEmailPage />} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    );

    const digitInputs = screen.getAllByRole("textbox", { name: /Digit/i });

    // Paste 6 digits into the first box
    await act(async () => {
      fireEvent.paste(digitInputs[0], {
        clipboardData: {
          getData: () => "654321",
        },
      });
    });

    await waitFor(() => {
      expect(verifyPayload).not.toBeNull();
      expect(verifyPayload).toEqual({
        email: "otpuser@example.com",
        otp: "654321",
      });
    });
  });

  it("auto-verifies on load when token query parameter is present", async () => {
    let verifyPayload: Record<string, unknown> | null = null;
    server.use(
      http.post("*/api/v1/auth/verify-email", async ({ request }) => {
        verifyPayload = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({
          access_token: "mock-verified-token",
          expires_in: 3600,
        });
      })
    );

    render(
      <MemoryRouter initialEntries={["/verify-email?token=magic_link_token_123"]}>
        <AuthProvider>
          <Routes>
            <Route path="/verify-email" element={<VerifyEmailPage />} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(verifyPayload).toEqual({
        token: "magic_link_token_123",
      });
    });
  });

  it("triggers resend verification and starts cooldown timer", async () => {
    let resendCalled = false;
    server.use(
      http.post("*/api/v1/auth/resend-verification", () => {
        resendCalled = true;
        return HttpResponse.json({ message: "Dispatched" });
      })
    );

    render(
      <MemoryRouter initialEntries={["/verify-email?email=resenduser@example.com"]}>
        <AuthProvider>
          <Routes>
            <Route path="/verify-email" element={<VerifyEmailPage />} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    );

    const resendBtn = screen.getByRole("button", { name: /Resend Code/i });
    expect(resendBtn).not.toBeDisabled();

    await act(async () => {
      fireEvent.click(resendBtn);
    });

    expect(resendCalled).toBe(true);
    await waitFor(() => {
      expect(screen.getByText(/Resend available in/i)).toBeInTheDocument();
    });
  });
});
