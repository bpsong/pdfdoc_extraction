"""Authentication utilities for a single-user setup.

This module provides:
  - Password verification using bcrypt directly (no passlib dependency for checking).
  - JWT access token creation and verification using jose.
  - Integration with project configuration for credentials and JWT settings.

Security notes:
  - Secret keys must be strong, random values; do not commit real secrets.
  - JWT algorithm is configurable (default: HS256). Ensure it matches issued tokens.
  - Tokens include 'sub', 'iat', and 'exp' claims and are validated on verification.
"""

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, ClassVar

import bcrypt
from jose import JWTError, jwt

from .config_protocol import ConfigProvider as ConfigManager


class AuthError(Exception):
    """Raised for authentication or authorization failures.

    Typical causes include invalid credentials, expired/invalid tokens, or
    configuration issues preventing secure operation.

    Troubleshooting:
        - Common Issue: Invalid credentials during login. Resolution: Verify username and password against configuration values.
        - Common Issue: Token signature mismatch. Resolution: Check that web.secret_key in config matches the key used to generate tokens.
        - Common Issue: Missing configuration values. Resolution: Ensure authentication.username, authentication.password_hash, and web.secret_key are properly set in config.yaml.
    """
    pass


class LoginRateLimitError(AuthError):
    """Raised when too many failed login attempts are made in a short window."""

    pass


class AuthUtils:
    """Single-user authentication and JWT utilities.

    Responsibilities:
        - Validate credentials against config (username/password_hash).
        - Create JWT access tokens with exp/iat/sub claims.
        - Verify and decode JWT tokens and validate their subject.

    Usage:
        config = ConfigManager(...)
        auth = AuthUtils(config)
        token = auth.login("user", "password")
        username = auth.get_current_user(token)

    Security notes:
        - Ensure ConfigManager provides strong secret_key and intended algorithm.
        - Only a single configured username is accepted.

    Troubleshooting:
        - Common Issue: Configuration validation fails during initialization. Resolution: Verify all required config values (authentication.username, authentication.password_hash, web.secret_key) are present and properly formatted.
        - Common Issue: Password verification consistently fails. Resolution: Ensure password_hash in config is a valid bcrypt hash generated with sufficient rounds (minimum 12 recommended).
        - Common Issue: JWT algorithm mismatch. Resolution: Confirm web.jwt_algorithm in config matches the algorithm used when tokens were created.
    """

    _failed_login_attempts: ClassVar[dict[str, list[float]]] = {}
    _locked_login_keys: ClassVar[dict[str, float]] = {}

    def __init__(self, config: ConfigManager):
        """Initialize utilities from configuration.

        Args:
            config: Configuration provider used to load authentication and JWT settings.

        Raises:
            AuthError: If required configuration values are missing.
        """
        self.logger = logging.getLogger("AuthUtils")
        
        # Load values from config.yaml with safe type conversion
        username_val = config.get("authentication.username")
        password_hash_val = config.get("authentication.password_hash")
        secret_key_val = config.get("web.secret_key")
        algorithm_val = config.get("web.jwt_algorithm", "HS256") or "HS256"
        token_exp_val = config.get("web.token_exp_minutes", 30)
        rate_limit_enabled_val = config.get("auth.login_rate_limit_enabled", True)
        max_attempts_val = config.get("auth.login_max_failed_attempts", 5)
        window_seconds_val = config.get("auth.login_window_seconds", 600)
        cooldown_seconds_val = config.get("auth.login_cooldown_seconds", 600)
        
        # Ensure string types
        self.username = str(username_val) if username_val is not None else ""
        self.password_hash = str(password_hash_val) if password_hash_val is not None else ""
        self.secret_key = str(secret_key_val) if secret_key_val is not None else ""
        self.algorithm = str(algorithm_val)
        
        try:
            self.token_exp_minutes = int(token_exp_val) if token_exp_val is not None else 30
        except (TypeError, ValueError):
            self.token_exp_minutes = 30

        self.login_rate_limit_enabled = self._config_bool(rate_limit_enabled_val, True)
        self.login_max_failed_attempts = self._positive_int(max_attempts_val, 5)
        self.login_window_seconds = self._positive_int(window_seconds_val, 600)
        self.login_cooldown_seconds = self._positive_int(cooldown_seconds_val, 600)
            
        # Validate required configuration
        if not self.username or not self.password_hash:
            raise AuthError("authentication.username and authentication.password_hash must be set in config")
        if not self.secret_key:
            raise AuthError("web.secret_key must be set in config")
            
        self.logger.info(f"Configured username: {self.username}")
        self.logger.debug("Password hash configured")
        self.logger.debug(f"Using JWT algorithm: {self.algorithm}")
        self.logger.debug(f"Token expiration: {self.token_exp_minutes} minutes")
        self.logger.debug(
            "Login rate limit enabled=%s max_attempts=%s window_seconds=%s cooldown_seconds=%s",
            self.login_rate_limit_enabled,
            self.login_max_failed_attempts,
            self.login_window_seconds,
            self.login_cooldown_seconds,
        )

    @staticmethod
    def _config_bool(value: Any, default: bool) -> bool:
        """Parse a boolean-like configuration value."""

        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"1", "true", "yes", "on"}:
                return True
            if lowered in {"0", "false", "no", "off"}:
                return False
        return default

    @staticmethod
    def _positive_int(value: Any, default: int) -> int:
        """Parse a positive integer configuration value."""

        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return default
        return parsed if parsed > 0 else default

    @classmethod
    def reset_login_rate_limits(cls) -> None:
        """Clear in-memory login throttling state.

        This is intended for tests and controlled maintenance actions.
        """

        cls._failed_login_attempts.clear()
        cls._locked_login_keys.clear()

    def _login_rate_limit_key(self, username: str, client_id: str | None) -> str:
        """Return the throttling key for a username and client identifier."""

        safe_username = (username or "").strip().lower() or "<blank>"
        safe_client = (client_id or "unknown").strip().lower() or "unknown"
        return f"{safe_client}:{safe_username}"

    def _ensure_login_not_rate_limited(self, username: str, client_id: str | None) -> str:
        """Raise when the username/client pair is temporarily blocked."""

        key = self._login_rate_limit_key(username, client_id)
        if not self.login_rate_limit_enabled:
            return key

        now = time.monotonic()
        locked_until = self._locked_login_keys.get(key)
        if locked_until is not None:
            if locked_until > now:
                retry_after = max(1, int(locked_until - now))
                raise LoginRateLimitError(f"Too many failed login attempts. Try again in {retry_after} seconds.")
            self._locked_login_keys.pop(key, None)

        window_start = now - self.login_window_seconds
        attempts = [
            timestamp
            for timestamp in self._failed_login_attempts.get(key, [])
            if timestamp >= window_start
        ]
        self._failed_login_attempts[key] = attempts
        return key

    def _record_failed_login(self, key: str) -> None:
        """Record a failed login and lock the key when the threshold is reached."""

        if not self.login_rate_limit_enabled:
            return

        now = time.monotonic()
        window_start = now - self.login_window_seconds
        attempts = [
            timestamp
            for timestamp in self._failed_login_attempts.get(key, [])
            if timestamp >= window_start
        ]
        attempts.append(now)
        if len(attempts) >= self.login_max_failed_attempts:
            self._locked_login_keys[key] = now + self.login_cooldown_seconds
            self._failed_login_attempts[key] = []
            self.logger.warning("Login temporarily rate limited for key '%s'", key)
            return
        self._failed_login_attempts[key] = attempts

    def _record_successful_login(self, key: str) -> None:
        """Clear failed login state after successful authentication."""

        self._failed_login_attempts.pop(key, None)
        self._locked_login_keys.pop(key, None)

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a plaintext password against a bcrypt hash using bcrypt.checkpw.

        Args:
            plain_password: The plaintext password to verify.
            hashed_password: The bcrypt hash to verify against.

        Returns:
            True if the password matches the hash; False otherwise.

        Notes:
            - bcrypt has a hard 72-byte limit on input; longer passwords will raise ValueError.
        """
        if plain_password is None or hashed_password is None:
            self.logger.warning("Password verification failed: missing input")
            return False

        self.logger.debug(f"Verifying password (length={len(plain_password)})")
        try:
            return bcrypt.checkpw(
                plain_password.encode("utf-8"),
                hashed_password.encode("utf-8"),
            )
        except ValueError as exc:
            # Raised by bcrypt when the candidate exceeds the 72-byte limit
            self.logger.error(f"Password verification failed: {exc}")
            return False
        except Exception as exc:
            self.logger.error(f"Password verification failed: {exc}")
            return False

    def create_access_token(self, data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
        """Create a signed JWT access token.

        Args:
            data: The data to encode in the token (must include 'sub' for subject).
            expires_delta: Optional expiration time override. If None, uses token_exp_minutes.

        Returns:
            A JWT string signed with the configured secret and algorithm.
        """
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.now(timezone.utc) + expires_delta
        else:
            expire = datetime.now(timezone.utc) + timedelta(minutes=self.token_exp_minutes)
            
        to_encode.update({"exp": expire})
        self.logger.debug(f"Creating token for subject='{data.get('sub')}', expires at {expire}")
        
        encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
        return encoded_jwt

    def decode_token(self, token: str) -> Dict[str, Any]:
        """Decode and validate a JWT token.

        Args:
            token: The JWT string to verify and decode.

        Returns:
            The decoded payload as a dictionary if the token is valid.

        Raises:
            AuthError: If the token is expired, has invalid signature/structure,
                or contains an invalid subject.

        Troubleshooting:
            - Common Issue: "Invalid token: Signature has expired" - Resolution: Check token expiration time and implement token refresh mechanism if needed.
            - Common Issue: "Invalid token: Signature verification failed" - Resolution: Verify web.secret_key in config matches the key used to sign the token.
            - Common Issue: "Invalid token: Not enough segments" - Resolution: Ensure token is properly formatted with header.payload.signature structure.
            - Common Issue: "Invalid token: Algorithm not supported" - Resolution: Confirm web.jwt_algorithm in config matches the algorithm specified in the token header.
        """
        self.logger.debug(f"Decoding token (length={len(token) if token else 0})")
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            self.logger.debug(f"Token decoded successfully")
            return payload
        except JWTError as e:
            self.logger.warning(f"Token decode failed: {e}")
            raise AuthError(f"Invalid token: {e}")

    def login(self, username: str, password: str, client_id: str | None = None) -> str:
        """Validate credentials and return a JWT access token.

        Args:
            username: The provided username to authenticate.
            password: The plaintext password to verify.
            client_id: Optional client identifier, typically the request IP,
                used with username for in-memory failed-login throttling.

        Returns:
            A signed JWT access token for the configured user.

        Raises:
            AuthError: If the username does not match the configured user or
                the password verification fails.

        Troubleshooting:
            - Common Issue: "Invalid credentials" for correct username/password. Resolution: Verify authentication.username and authentication.password_hash in config.yaml match expected values.
            - Common Issue: Login succeeds but token validation fails immediately. Resolution: Ensure web.token_exp_minutes is set to a reasonable value (default 30 minutes).
            - Common Issue: Password hash format incompatibility. Resolution: Regenerate password hash using bcrypt with rounds=12 if using different bcrypt implementation.
        """
        self.logger.info(f"Login attempt for username: {username}")
        rate_limit_key = self._ensure_login_not_rate_limited(username, client_id)
        
        # Verify username
        if username != self.username:
            self.logger.warning(f"Login failed: User '{username}' not found")
            self._record_failed_login(rate_limit_key)
            raise AuthError("Invalid credentials")
            
        # Verify password
        self.logger.debug(f"Verifying password for user '{username}'")
        is_valid_password = self.verify_password(password, self.password_hash)
        
        if not is_valid_password:
            self.logger.warning(f"Login failed: Invalid password for user '{username}'")
            self._record_failed_login(rate_limit_key)
            raise AuthError("Invalid credentials")
            
        # Create token
        self.logger.info(f"Login successful for user: {username}")
        self._record_successful_login(rate_limit_key)
        access_token_expires = timedelta(minutes=self.token_exp_minutes)
        return self.create_access_token(
            data={"sub": username},
            expires_delta=access_token_expires
        )

    def get_current_user(self, token: str) -> str:
        """Return the subject (username) from a verified JWT.

        Args:
            token: The JWT string to verify and decode.

        Returns:
            The username extracted from the 'sub' claim after successful verification.

        Raises:
            AuthError: If token verification fails or the subject is invalid.

        Troubleshooting:
            - Common Issue: "Invalid token: missing subject" - Resolution: Ensure token was created with 'sub' claim containing the username.
            - Common Issue: "Invalid token subject" - Resolution: Verify the token's subject matches the configured authentication.username in config.yaml.
            - Common Issue: "Token validation error" - Resolution: Check token format and ensure it hasn't been tampered with or corrupted during transmission.
        """
        try:
            payload = self.decode_token(token)
            username = payload.get("sub")
            
            if username is None:
                self.logger.warning("Token missing 'sub' claim")
                raise AuthError("Invalid token: missing subject")
                
            if username != self.username:
                self.logger.warning(f"Token has invalid subject: {username}")
                raise AuthError("Invalid token subject")
                
            return username
            
        except AuthError:
            # Re-raise AuthError with original message
            raise
        except Exception as e:
            self.logger.error(f"Unexpected error in get_current_user: {e}", exc_info=True)
            raise AuthError(f"Token validation error: {e}")
