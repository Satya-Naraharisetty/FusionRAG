import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { VerifyEmailPage } from "../pages/VerifyEmailPage";

const mockVerifyEmail = vi.fn();
const mockResendVerification = vi.fn();

vi.mock("../hooks/useAuth", () => ({
  useAuth: () => ({
    verifyEmail: mockVerifyEmail,
    resendVerification: mockResendVerification,
    isAuthenticated: false,
    user: null,
  }),
}));

describe("VerifyEmailPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockVerifyEmail.mockResolvedValue({
      access_token: "mock-verified-token",
      expires_in: 3600,
    });
    mockResendVerification.mockResolvedValue({ message: "Dispatched" });
  });

  it("renders 6 digit input boxes and email parameter from URL", () => {
    const { unmount } = render(
      <MemoryRouter initialEntries={["/verify-email?email=user@example.com"]}>
        <Routes>
          <Route path="/verify-email" element={<VerifyEmailPage />} />
        </Routes>
      </MemoryRouter>
    );

    expect(screen.getByText(/Verify your email/i)).toBeInTheDocument();
    expect(screen.getByText(/user@example.com/i)).toBeInTheDocument();

    const digitInputs = screen.getAllByRole("textbox", { name: /Digit/i });
    expect(digitInputs).toHaveLength(6);
    unmount();
  });

  it("submits 6-digit OTP code when all boxes are filled via paste or input", async () => {
    const { unmount } = render(
      <MemoryRouter initialEntries={["/verify-email?email=otpuser@example.com"]}>
        <Routes>
          <Route path="/verify-email" element={<VerifyEmailPage />} />
        </Routes>
      </MemoryRouter>
    );

    const digitInputs = screen.getAllByRole("textbox", { name: /Digit/i });

    // Paste 6 digits into the first box
    fireEvent.paste(digitInputs[0], {
      clipboardData: {
        getData: () => "654321",
      },
    });

    await waitFor(() => {
      expect(mockVerifyEmail).toHaveBeenCalledWith({
        email: "otpuser@example.com",
        otp: "654321",
      });
    });
    unmount();
  });

  it("auto-verifies on load when token query parameter is present", async () => {
    const { unmount } = render(
      <MemoryRouter initialEntries={["/verify-email?token=magic_link_token_123"]}>
        <Routes>
          <Route path="/verify-email" element={<VerifyEmailPage />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(mockVerifyEmail).toHaveBeenCalledWith({
        token: "magic_link_token_123",
      });
    });
    unmount();
  });

  it("triggers resend verification and starts cooldown timer", async () => {
    const { unmount } = render(
      <MemoryRouter initialEntries={["/verify-email?email=resenduser@example.com"]}>
        <Routes>
          <Route path="/verify-email" element={<VerifyEmailPage />} />
        </Routes>
      </MemoryRouter>
    );

    const resendBtn = screen.getByRole("button", { name: /Resend Code/i });
    expect(resendBtn).not.toBeDisabled();

    fireEvent.click(resendBtn);

    await waitFor(() => {
      expect(mockResendVerification).toHaveBeenCalledWith("resenduser@example.com");
      expect(screen.getByText(/Resend available in/i)).toBeInTheDocument();
    });
    unmount();
  });
});
