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
