"""Custom exception classes."""

from typing import Any, Dict, Optional


class AppException(Exception):
    """Base application exception."""

    def __init__(
        self,
        message: str,
        status_code: int = 500,
        details: Optional[Dict[str, Any]] = None,
    ):
        """Initialize exception.

        Args:
            message: Error message.
            status_code: HTTP status code.
            details: Additional error details.
        """
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)


class ConfigurationError(AppException):
    """Configuration error."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        """Initialize configuration error."""
        super().__init__(message, status_code=500, details=details)


class AuthenticationError(AppException):
    """Authentication error."""

    def __init__(self, message: str = "Authentication failed", details: Optional[Dict[str, Any]] = None):
        """Initialize authentication error."""
        super().__init__(message, status_code=401, details=details)


class ValidationError(AppException):
    """Validation error."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        """Initialize validation error."""
        super().__init__(message, status_code=400, details=details)


class ServiceError(AppException):
    """External service error."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        """Initialize service error."""
        super().__init__(message, status_code=503, details=details)

