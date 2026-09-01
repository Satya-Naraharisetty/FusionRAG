import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import toast from "react-hot-toast";
import ReauthDialog from "../components/auth/ReauthDialog";

vi.mock("react-hot-toast", () => ({
  default: { success: vi.fn(), error: vi.fn(), loading: vi.fn() },
}));

const renderDialog = (props: Record<string, unknown> = {}) => {
  const defaults = {
    open: true,
    onOpenChange: vi.fn(),
    title: "Delete Account?",
    description: "This permanently deletes your account.",
    accountEmail: "test@example.com",
    onConfirm: vi.fn().mockResolvedValue(undefined),
  };
  return render(<ReauthDialog {...defaults} {...props} />);
};

describe("ReauthDialog", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("gates the confirm button on matching email AND non-empty password", () => {
    renderDialog();

    const confirm = screen.getByRole("button", { name: /^Confirm$/i });
    expect(confirm).toBeDisabled();

    // Wrong email: still disabled
    fireEvent.change(screen.getByLabelText(/Type your email to confirm/i), {
      target: { value: "wrong@example.com" },
    });
    expect(confirm).toBeDisabled();

    // Matching email but no password: still disabled
    fireEvent.change(screen.getByLabelText(/Type your email to confirm/i), {
      target: { value: "test@example.com" },
    });
    expect(confirm).toBeDisabled();

    // Matching email + password: enabled
    fireEvent.change(screen.getByLabelText(/Re-enter your password/i), {
      target: { value: "password123" },
    });
    expect(confirm).toBeEnabled();
  });

  it("skips the email input when requireEmail is false", () => {
    renderDialog({ requireEmail: false });

    expect(screen.queryByLabelText(/Type your email to confirm/i)).toBeNull();

    const confirm = screen.getByRole("button", { name: /^Confirm$/i });
    expect(confirm).toBeDisabled();

    fireEvent.change(screen.getByLabelText(/Re-enter your password/i), {
      target: { value: "password123" },
    });
    expect(confirm).toBeEnabled();
  });

  it("calls onConfirm with the password and closes on success", async () => {
    const onConfirm = vi.fn().mockResolvedValue(undefined);
    const onOpenChange = vi.fn();
    const onSuccess = vi.fn();
    renderDialog({
      onConfirm,
      onOpenChange,
      onSuccess,
      successMessage: "Your account has been deleted.",
    });

    fireEvent.change(screen.getByLabelText(/Type your email to confirm/i), {
      target: { value: "test@example.com" },
    });
    fireEvent.change(screen.getByLabelText(/Re-enter your password/i), {
      target: { value: "password123" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^Confirm$/i }));

    await vi.waitFor(() => expect(onConfirm).toHaveBeenCalledWith("password123"));
    expect(onOpenChange).toHaveBeenCalledWith(false);
    expect(onSuccess).toHaveBeenCalled();
    expect(toast.success).toHaveBeenCalledWith("Your account has been deleted.");
  });

  it("submits via Enter in the password field", async () => {
    const onConfirm = vi.fn().mockResolvedValue(undefined);
    renderDialog({ onConfirm });

    fireEvent.change(screen.getByLabelText(/Type your email to confirm/i), {
      target: { value: "test@example.com" },
    });
    fireEvent.change(screen.getByLabelText(/Re-enter your password/i), {
      target: { value: "password123" },
    });
    const form = screen.getByLabelText(/Re-enter your password/i).closest("form");
    expect(form).not.toBeNull();
    fireEvent.submit(form!);

    await vi.waitFor(() => expect(onConfirm).toHaveBeenCalledWith("password123"));
  });

  it("keeps the dialog open and clears the password on INVALID_CREDENTIALS", async () => {
    const onConfirm = vi.fn().mockRejectedValue({
      data: { error: { code: "INVALID_CREDENTIALS" } },
      status: 401,
    });
    const onOpenChange = vi.fn();
    renderDialog({ onConfirm, onOpenChange });

    fireEvent.change(screen.getByLabelText(/Type your email to confirm/i), {
      target: { value: "test@example.com" },
    });
    const passwordInput = screen.getByLabelText(/Re-enter your password/i);
    fireEvent.change(passwordInput, { target: { value: "wrong-password" } });
    fireEvent.click(screen.getByRole("button", { name: /^Confirm$/i }));

    await vi.waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith("Incorrect password. Please try again."),
    );
    expect(onOpenChange).not.toHaveBeenCalledWith(false);
    expect((passwordInput as HTMLInputElement).value).toBe("");
  });

  it("keeps the dialog open and preserves the password on rate-limit (429)", async () => {
    const onConfirm = vi.fn().mockRejectedValue({ status: 429 });
    const onOpenChange = vi.fn();
    renderDialog({ onConfirm, onOpenChange });

    fireEvent.change(screen.getByLabelText(/Type your email to confirm/i), {
      target: { value: "test@example.com" },
    });
    const passwordInput = screen.getByLabelText(/Re-enter your password/i);
    fireEvent.change(passwordInput, { target: { value: "password123" } });
    fireEvent.click(screen.getByRole("button", { name: /^Confirm$/i }));

    await vi.waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith("Too many attempts. Please try again in a minute."),
    );
    expect(onOpenChange).not.toHaveBeenCalledWith(false);
    expect((passwordInput as HTMLInputElement).value).toBe("password123");
  });

  it("resets the gate when the dialog closes", () => {
    const { rerender } = renderDialog();
    fireEvent.change(screen.getByLabelText(/Type your email to confirm/i), {
      target: { value: "test@example.com" },
    });
    fireEvent.change(screen.getByLabelText(/Re-enter your password/i), {
      target: { value: "password123" },
    });

    rerender(
      <ReauthDialog
        open={false}
        onOpenChange={vi.fn()}
        title="Delete Account?"
        description="d"
        accountEmail="test@example.com"
        onConfirm={vi.fn()}
      />,
    );
    rerender(
      <ReauthDialog
        open={true}
        onOpenChange={vi.fn()}
        title="Delete Account?"
        description="d"
        accountEmail="test@example.com"
        onConfirm={vi.fn()}
      />,
    );

    expect(screen.getByLabelText(/Type your email to confirm/i)).toHaveValue("");
    expect(screen.getByLabelText(/Re-enter your password/i)).toHaveValue("");
  });

  it("skips the password input and gates on email only when requirePassword is false", async () => {
    const onConfirm = vi.fn().mockResolvedValue(undefined);
    renderDialog({ requirePassword: false, onConfirm });

    expect(screen.queryByLabelText(/Re-enter your password/i)).toBeNull();

    const confirm = screen.getByRole("button", { name: /^Confirm$/i });
    expect(confirm).toBeDisabled();

    fireEvent.change(screen.getByLabelText(/Type your email to confirm/i), {
      target: { value: "test@example.com" },
    });
    expect(confirm).toBeEnabled();

    fireEvent.click(confirm);
    await vi.waitFor(() => expect(onConfirm).toHaveBeenCalledWith(undefined));
  });
});
