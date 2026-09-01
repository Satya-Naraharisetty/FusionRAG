import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import SettingsPage from "../pages/SettingsPage";
import { AuthProvider } from "../context/AuthContext";
import { ThemeProvider } from "../context/ThemeContext";
import { setLocale } from "../lib/messages";
import { server } from "./handlers";

// The locale module is a process-wide singleton: reset the persisted choice
// and the active locale so tests stay order-independent (and never leak into
// the other settings tests, which expect English copy).
afterEach(() => {
  localStorage.clear();
  setLocale("en");
});

const renderSettings = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <ThemeProvider>
          <SettingsPage />
        </ThemeProvider>
      </AuthProvider>
    </QueryClientProvider>,
  );
};

const openDeleteDialog = async () => {
  renderSettings();
  // Wait for the /auth/me boot probe so user.email is populated
  await screen.findByText("test@example.com");
  fireEvent.click(screen.getByRole("button", { name: /Data & Privacy/i }));
  fireEvent.click(screen.getByRole("button", { name: /^Delete$/i }));
  expect(screen.getByText(/Delete Account\?/i)).toBeInTheDocument();
};

describe("SettingsPage — Delete Account", () => {
  it("requires the matching email AND a password before deletion is allowed", async () => {
    await openDeleteDialog();

    const confirmButton = screen.getByRole("button", { name: /^Delete Account$/i });
    expect(confirmButton).toBeDisabled();

    const emailInput = screen.getByLabelText(/Type your email to confirm/i);

    fireEvent.change(emailInput, { target: { value: "wrong@example.com" } });
    expect(confirmButton).toBeDisabled();

    fireEvent.change(emailInput, { target: { value: "test@example.com" } });
    // Matching email alone is not enough — the re-entered password is required.
    expect(confirmButton).toBeDisabled();

    fireEvent.change(screen.getByLabelText(/Re-enter your password/i), {
      target: { value: "SecurePassword123!" },
    });
    expect(confirmButton).toBeEnabled();
  });

  it("calls DELETE /auth/account when confirmed", async () => {
    let deleteCalled = false;
    server.use(
      http.delete("*/api/v1/auth/account", () => {
        deleteCalled = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );

    await openDeleteDialog();

    fireEvent.change(screen.getByLabelText(/Type your email to confirm/i), {
      target: { value: "test@example.com" },
    });
    fireEvent.change(screen.getByLabelText(/Re-enter your password/i), {
      target: { value: "SecurePassword123!" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^Delete Account$/i }));

    await waitFor(() => expect(deleteCalled).toBe(true));
  });

  it("does not fire the request when the email does not match", async () => {
    let deleteCalled = false;
    server.use(
      http.delete("*/api/v1/auth/account", () => {
        deleteCalled = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );

    await openDeleteDialog();

    fireEvent.change(screen.getByLabelText(/Type your email to confirm/i), {
      target: { value: "someone-else@example.com" },
    });
    const confirmButton = screen.getByRole("button", { name: /^Delete Account$/i });
    expect(confirmButton).toBeDisabled();
    fireEvent.click(confirmButton);

    // Allow a tick for any (wrong) request to propagate
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(deleteCalled).toBe(false);
  });
});

describe("SettingsPage — Language switcher", () => {
  it("keeps English active and opens Coming Soon dialog when clicking other languages", async () => {
    renderSettings();

    fireEvent.click(screen.getByRole("button", { name: /Appearance/i }));
    expect(screen.getByText("Language")).toBeInTheDocument();

    // English button is active
    const englishBtn = screen.getByRole("button", { name: /English/i });
    expect(englishBtn).toHaveAttribute("data-active", "true");

    // Clicking French opens Coming Soon dialog
    const frenchBtn = screen.getByRole("button", { name: /Français/i });
    fireEvent.click(frenchBtn);

    expect(screen.getByText(/Coming Soon · In Development/i)).toBeInTheDocument();
    expect(screen.getByText(/Full localization for French/i)).toBeInTheDocument();

    // Clicking "Got it" dismisses the modal
    const gotItBtn = screen.getByRole("button", { name: /^Got it$/i });
    fireEvent.click(gotItBtn);

    expect(screen.queryByText(/Coming Soon · In Development/i)).not.toBeInTheDocument();
    expect(englishBtn).toHaveAttribute("data-active", "true");
  });
});

describe("SettingsPage — Password Management", () => {
  it("renders Change Password button when user already has a password", async () => {
    renderSettings();
    await screen.findByText("test@example.com");

    expect(screen.getByText("Account Password")).toBeInTheDocument();
    const changeBtn = screen.getByRole("button", { name: /^Change Password$/i });
    expect(changeBtn).toBeInTheDocument();

    fireEvent.click(changeBtn);
    expect(screen.getByLabelText(/Current Password/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^New Password/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Confirm New Password/i)).toBeInTheDocument();
  });

  it("renders Set Password for OAuth user without a password", async () => {
    server.use(
      http.get("*/api/v1/auth/me", () => {
        return HttpResponse.json({
          id: "oauth-user-123",
          email: "oauth@example.com",
          role: "user",
          is_active: true,
          is_verified: true,
          oauth_provider: "google",
          has_password: false,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        });
      }),
    );

    renderSettings();
    await screen.findByText("oauth@example.com");

    expect(screen.getByText("Set Account Password")).toBeInTheDocument();
    expect(screen.getByText(/You signed in via Google/i)).toBeInTheDocument();

    const setBtn = screen.getByRole("button", { name: /^Set Password$/i });
    fireEvent.click(setBtn);

    // Should NOT ask for Current Password since OAuth user has none
    expect(screen.queryByLabelText(/Current Password/i)).not.toBeInTheDocument();
    expect(screen.getByLabelText(/^Password/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Confirm New Password/i)).toBeInTheDocument();
  });

  it("submits password update successfully", async () => {
    let passwordUpdated = false;
    server.use(
      http.post("*/api/v1/auth/password", async ({ request }) => {
        const body = (await request.json()) as { new_password?: string };
        if (body.new_password === "NewSecurePass123!") {
          passwordUpdated = true;
        }
        return HttpResponse.json({ message: "Password updated successfully" });
      }),
    );

    renderSettings();
    await screen.findByText("test@example.com");

    fireEvent.click(screen.getByRole("button", { name: /^Change Password$/i }));

    fireEvent.change(screen.getByLabelText(/Current Password/i), {
      target: { value: "OldPassword123!" },
    });
    fireEvent.change(screen.getByLabelText(/^New Password/i), {
      target: { value: "NewSecurePass123!" },
    });
    fireEvent.change(screen.getByLabelText(/Confirm New Password/i), {
      target: { value: "NewSecurePass123!" },
    });

    const updateBtn = screen.getByRole("button", { name: /^Update Password$/i });
    expect(updateBtn).toBeEnabled();
    fireEvent.click(updateBtn);

    await waitFor(() => expect(passwordUpdated).toBe(true));
  });
});
