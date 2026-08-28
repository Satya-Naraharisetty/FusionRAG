class AuthException(Exception):
    """
    Base exception for authentication errors.
    """

    pass


class DuplicateAccountException(AuthException):
    """
    Raised when registering an email that already exists.
    """

    pass


class InvalidCredentialsException(AuthException):
    """
    Raised on incorrect login credentials.
    """

    pass


class AccountDisabledException(AuthException):
    """
    Raised when a deactivated user tries to login or refresh.
    """

    pass


class InvalidSessionException(AuthException):
    """
    Raised when a refresh token is invalid, expired, or revoked.
    """

    pass


class UserNotFoundException(AuthException):
    """
    Raised when an operation targets a user account that no longer exists.
    """

    pass


class EmailNotVerifiedException(AuthException):
    """
    Raised when an unverified user attempts to log in.
    """

    pass


class InvalidVerificationTokenException(AuthException):
    """
    Raised when a verification token or OTP is invalid or not found.
    """

    pass


class ExpiredVerificationTokenException(AuthException):
    """
    Raised when a verification token or OTP has expired.
    """

    pass


class MaxVerificationAttemptsException(AuthException):
    """
    Raised when the maximum number of failed OTP verification attempts is exceeded.
    """

    pass
