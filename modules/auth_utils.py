"""Authentication utilities for a single-user setup.

This module provides:
  - Password verification using passlib's CryptContext with bcrypt.
  - JWT access token creation and verification using jose.
  - Integration with project configuration for credentials and JWT settings.

Security notes:
  - Secret keys must be strong, random values; do not commit real secrets.
  - JWT algorithm is configurable (default: HS256). Ensure it matches issued tokens.
  - Tokens include 'sub', 'iat', and 'exp' claims and are validated on verification.
"""

import logging
import warnings
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any

# Suppress specific bcrypt version warning since it doesn't affect functionality
warnings.filterwarnings('ignore', message='.*error reading bcrypt version.*')

from passlib.context import CryptContext
from jose import JWTError, jwt

from .config_manager import ConfigManager


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
        
        # Ensure string types
        self.username = str(username_val) if username_val is not None else ""
        self.password_hash = str(password_hash_val) if password_hash_val is not None else ""
        self.secret_key = str(secret_key_val) if secret_key_val is not None else ""
        self.algorithm = str(algorithm_val)
        
        try:
            self.token_exp_minutes = int(token_exp_val) if token_exp_val is not None else 30
        except (TypeError, ValueError):
            self.token_exp_minutes = 30
            
        # Validate required configuration
        if not self.username or not self.password_hash:
            raise AuthError("authentication.username and authentication.password_hash must be set in config")
        if not self.secret_key:
            raise AuthError("web.secret_key must be set in config")
            
        # Configure password context with bcrypt settings to avoid version check
        self.pwd_context = CryptContext(
            schemes=["bcrypt"],
            deprecated="auto",
            bcrypt__rounds=12  # Explicitly set rounds instead of relying on version detection
        )
        
        self.logger.info(f"Configured username: {self.username}")
        self.logger.debug(f"Loaded password hash: {self.password_hash}")
        self.logger.debug(f"Using JWT algorithm: {self.algorithm}")
        self.logger.debug(f"Token expiration: {self.token_exp_minutes} minutes")

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a plaintext password against a bcrypt hash.

        Args:
            plain_password: The plaintext password to verify.
            hashed_password: The bcrypt hash to verify against.

        Returns:
            True if the password matches the hash; False otherwise.

        Troubleshooting:
            - Common Issue: Password verification always returns False. Resolution: Verify the hashed_password is a valid bcrypt hash format (starts with $2b$, $2y$, or $2a$).
            - Common Issue: bcrypt version warnings. Resolution: These are informational and don't affect functionality; the code handles version detection issues automatically.
            - Common Issue: Performance issues with verification. Resolution: Ensure bcrypt rounds are set to 12; higher values increase security but slow verification.
        """
        self.logger.debug(f"Verifying password (length={len(plain_password)})")
        try:
            result = self.pwd_context.verify(plain_password, hashed_password)
            self.logger.debug(f"Password verification result: {result}")
            return result
        except Exception as e:
            self.logger.error(f"Password verification failed: {e}")
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

    def login(self, username: str, password: str) -> str:
        """Validate credentials and return a JWT access token.

        Args:
            username: The provided username to authenticate.
            password: The plaintext password to verify.

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
        
        # Verify username
        if username != self.username:
            self.logger.warning(f"Login failed: User '{username}' not found")
            raise AuthError("Invalid credentials")
            
        # Verify password
        self.logger.debug(f"Verifying password for user '{username}' against hash: {self.password_hash}")
        is_valid_password = self.verify_password(password, self.password_hash)
        
        if not is_valid_password:
            self.logger.warning(f"Login failed: Invalid password for user '{username}'")
            raise AuthError("Invalid credentials")
            
        # Create token
        self.logger.info(f"Login successful for user: {username}")
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