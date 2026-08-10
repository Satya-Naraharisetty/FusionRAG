import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import SettingsPage from "../pages/SettingsPage";
import { AuthProvider } from "../context/AuthContext";
import { ThemeProvider } from "../context/ThemeContext";
import { server } from "./handlers";

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
  it("requires typing the account email before deletion is allowed", async () => {
    await openDeleteDialog();

    const confirmButton = screen.getByRole("button", { name: /^Delete Account$/i });
    expect(confirmButton).toBeDisabled();

    const emailInput = screen.getByLabelText(/Type your email to confirm/i);

    fireEvent.change(emailInput, { target: { value: "wrong@example.com" } });
    expect(confirmButton).toBeDisabled();

    fireEvent.change(emailInput, { target: { value: "test@example.com" } });
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
