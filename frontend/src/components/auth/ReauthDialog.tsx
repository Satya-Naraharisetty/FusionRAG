import React, { useEffect, useRef, useState } from "react";
import toast from "react-hot-toast";
import { Button } from "../ui/Button";
import { Input } from "../ui/Input";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../ui/Modal";

/**
 * Reusable password re-entry gate for sensitive account actions (delete
 * account today; change password, export-all-data, etc. in the future).
 *
 * The confirm button stays disabled until the user types their password —
 * and, when `requireEmail` is set, their exact account email as well. On
 * failure the dialog stays open and the error is surfaced per-code
 * (wrong password clears the field for a retry; a 429 rate-limit keeps it).
 * On success it closes itself and fires the optional `onSuccess` callback.
 *
 * The error shape matches the backend's `format_error_response` contract,
 * as surfaced by the API client (`ApiError` with `status` + `data.error.code`).
 */
export interface ReauthDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Dialog header title, e.g. "Delete Account?" */
  title: string;
  /** Body copy rendered under the title (may include the account email). */
  description: React.ReactNode;
  /** Icon shown next to the title, e.g. a destructive action icon. */
  icon?: React.ReactNode;
  /**
   * The account email. When `requireEmail` is true it must be typed exactly
   * (case-insensitive, trimmed) before the action can be confirmed.
   */
  accountEmail?: string;
  /** Require typing the account email in addition to the password. */
  requireEmail?: boolean;
  /** Require typing the account password. Default is true. Set to false for OAuth-only users without a password. */
  requirePassword?: boolean;
  /** Label of the confirm (destructive) button. */
  confirmLabel?: string;
  /** Label of the confirm button while the action is in flight. */
  submittingLabel?: string;
  /** Success toast shown after the action resolves. Omit for no toast. */
  successMessage?: string;
  /** Runs with the re-entered password (or undefined if requirePassword is false); reject to keep the dialog open. */
  onConfirm: (password?: string) => Promise<void>;
  /** Extra behavior after a successful confirmation (e.g. navigation). */
  onSuccess?: () => void;
  /** Per-error-code toast message overrides. */
  errorMessages?: Partial<Record<"INVALID_CREDENTIALS" | "RATE_LIMITED" | "UNKNOWN", string>>;
  /** Stable input ids (defaults keep label association + e2e selectors). */
  emailInputId?: string;
  passwordInputId?: string;
}

const DEFAULT_ERROR_MESSAGES = {
  INVALID_CREDENTIALS: "Incorrect password. Please try again.",
  RATE_LIMITED: "Too many attempts. Please try again in a minute.",
  UNKNOWN: "Action failed. Please try again.",
} as const;

const ReauthDialog: React.FC<ReauthDialogProps> = ({
  open,
  onOpenChange,
  title,
  description,
  icon,
  accountEmail,
  requireEmail = true,
  requirePassword = true,
  confirmLabel = "Confirm",
  submittingLabel = "Submitting…",
  successMessage,
  onConfirm,
  onSuccess,
  errorMessages,
  emailInputId = "reauth-confirm-email",
  passwordInputId = "reauth-confirm-password",
}) => {
  const [confirmEmail, setConfirmEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const emailRef = useRef<HTMLInputElement>(null);
  const passwordRef = useRef<HTMLInputElement>(null);

  const messages = { ...DEFAULT_ERROR_MESSAGES, ...errorMessages };

  // On open, focus the first gate field (keyboard-first UX); on close, reset
  // the gate so stale input never carries into a later invocation of the same
  // sensitive action.
  useEffect(() => {
    if (open) {
      const target = requireEmail ? emailRef.current : requirePassword ? passwordRef.current : null;
      target?.focus();
    } else {
      setConfirmEmail("");
      setPassword("");
    }
  }, [open, requireEmail, requirePassword]);

  const emailMatches =
    !requireEmail ||
    Boolean(accountEmail && confirmEmail.trim().toLowerCase() === accountEmail.toLowerCase());

  const canConfirm = !isSubmitting && emailMatches && (!requirePassword || password.length > 0);

  const handleClose = () => {
    if (!isSubmitting) onOpenChange(false);
  };

  const handleConfirm = async () => {
    if (!canConfirm) return;
    setIsSubmitting(true);
    try {
      await onConfirm(requirePassword ? password : undefined);
      setConfirmEmail("");
      setPassword("");
      onOpenChange(false);
      if (successMessage) toast.success(successMessage);
      onSuccess?.();
    } catch (err) {
      const e = err as { data?: { error?: { code?: string } }; status?: number };
      if (e.data?.error?.code === "INVALID_CREDENTIALS") {
        // Wrong password — clear the field so the user can retry immediately.
        setPassword("");
        toast.error(messages.INVALID_CREDENTIALS);
      } else if (e.status === 429) {
        // Rate-limited — keep the typed password; the user must wait a minute.
        toast.error(messages.RATE_LIMITED);
      } else {
        toast.error(messages.UNKNOWN);
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(next) => (next ? onOpenChange(true) : handleClose())}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-sm">
            {icon}
            {title}
          </DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            handleConfirm();
          }}
        >
          {requireEmail && (
            <Input
              id={emailInputId}
              ref={emailRef}
              value={confirmEmail}
              onChange={(e) => setConfirmEmail(e.target.value)}
              placeholder={accountEmail}
              label="Type your email to confirm"
              autoComplete="off"
              className="mt-1"
            />
          )}
          {requirePassword && (
            <Input
              id={passwordInputId}
              ref={passwordRef}
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              label="Re-enter your password"
              autoComplete="current-password"
              className="mt-1"
            />
          )}
          <DialogFooter className="gap-2">
            <Button
              type="button"
              variant="secondary"
              size="sm"
              onClick={handleClose}
              disabled={isSubmitting}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              variant="destructive"
              size="sm"
              disabled={!canConfirm}
              loading={isSubmitting}
            >
              {isSubmitting ? submittingLabel : confirmLabel}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
};

export default ReauthDialog;
