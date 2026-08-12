import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import SettingsPage from "../pages/SettingsPage";
import { AuthProvider } from "../context/AuthContext";
import { ThemeProvider } from "../context/ThemeContext";
import { getLocale, setLocale } from "../lib/messages";
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
    </QueryClientProvider>
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
      })
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
      })
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
  it("switches and persists the locale from the Appearance tab", async () => {
    renderSettings();

    fireEvent.click(screen.getByRole("button", { name: /Appearance/i }));
    // English default label before switching.
    expect(screen.getByText("Language")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /^Français$/i }));

    // The choice is applied to the i18n module and persisted to localStorage.
    expect(localStorage.getItem("locale")).toBe("fr");
    expect(getLocale()).toBe("fr");
    // The section label flips to the chosen locale immediately.
    expect(screen.getByText("Langue")).toBeInTheDocument();
  });

  it("reflects the current locale when the page mounts", async () => {
    // Simulate a persisted French choice (what the module holds after reload).
    setLocale("fr");
    renderSettings();

    fireEvent.click(screen.getByRole("button", { name: /Appearance/i }));
    expect(screen.getByText("Langue")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /^Français$/i })
    ).toHaveAttribute("data-active", "true");
    expect(
      screen.getByRole("button", { name: /^English$/i })
    ).toHaveAttribute("data-active", "false");
  });
});
