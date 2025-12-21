"""
Secret Rotation Service

Manages graceful rotation of secrets with zero downtime:
- Dual-credential mode during rotation
- Expiry tracking and alerting
- Automatic credential validation
- Rollback support
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, Dict, Callable
from enum import Enum
import logging

from src.utils.metrics import Counter, Gauge

logger = logging.getLogger(__name__)


class CredentialStatus(Enum):
    """Credential lifecycle states."""
    ACTIVE = "active"
    ROTATING = "rotating"
    EXPIRED = "expired"
    REVOKED = "revoked"


@dataclass
class Credential:
    """
    Represents a secret credential.
    
    Attributes:
        name: Credential identifier (e.g., 'alpaca_api_key')
        value: Secret value (encrypted in production)
        created_at: Creation timestamp
        expires_at: Expiration timestamp
        status: Current lifecycle status
        rotation_scheduled_at: When rotation will occur
        metadata: Additional credential metadata
    """
    name: str
    value: str
    created_at: datetime
    expires_at: Optional[datetime] = None
    status: CredentialStatus = CredentialStatus.ACTIVE
    rotation_scheduled_at: Optional[datetime] = None
    metadata: Dict = field(default_factory=dict)
    
    def is_expired(self) -> bool:
        """Check if credential has expired."""
        if self.expires_at is None:
            return False
        return datetime.utcnow() >= self.expires_at
    
    def is_expiring_soon(self, threshold_days: int = 7) -> bool:
        """Check if credential expires within threshold."""
        if self.expires_at is None:
            return False
        threshold_time = datetime.utcnow() + timedelta(days=threshold_days)
        return self.expires_at <= threshold_time
    
    def time_until_expiry(self) -> Optional[timedelta]:
        """Calculate time remaining until expiry."""
        if self.expires_at is None:
            return None
        return self.expires_at - datetime.utcnow()


class SecretRotationService:
    """
    Manages graceful secret rotation with zero downtime.
    
    Features:
    - Dual-credential mode during rotation
    - Automatic expiry detection and alerting
    - Validation of new credentials before switching
    - Rollback on validation failure
    
    Usage:
        service = SecretRotationService()
        
        # Register credential
        service.register_credential(
            name='alpaca_api_key',
            value='CURRENT_KEY',
            expires_at=datetime.utcnow() + timedelta(days=90)
        )
        
        # Rotate credential
        await service.rotate_credential(
            name='alpaca_api_key',
            new_value='NEW_KEY',
            validator=validate_alpaca_key
        )
    """
    
    def __init__(
        self,
        rotation_window_hours: int = 24,
        expiry_warning_days: int = 7,
        validation_timeout: int = 30
    ):
        """
        Initialize secret rotation service.
        
        Args:
            rotation_window_hours: Duration to keep both credentials active
            expiry_warning_days: Days before expiry to trigger warning
            validation_timeout: Seconds to wait for validation
        """
        self.credentials: Dict[str, Credential] = {}
        self.rotation_window_hours = rotation_window_hours
        self.expiry_warning_days = expiry_warning_days
        self.validation_timeout = validation_timeout
        
        # Metrics
        self.rotation_total = Counter(
            'trading_bot_secret_rotations_total',
            'Total secret rotations performed',
            ['credential_name', 'status']
        )
        self.expiry_warnings = Counter(
            'trading_bot_secret_expiry_warnings_total',
            'Total expiry warnings generated',
            ['credential_name']
        )
        self.credential_age_gauge = Gauge(
            'trading_bot_credential_age_days',
            'Age of credentials in days',
            ['credential_name']
        )
        
        # Background monitoring task
        self._monitoring_task: Optional[asyncio.Task] = None
        self._running = False
        
        logger.info(
            "SecretRotationService initialized",
            rotation_window_hours=rotation_window_hours,
            expiry_warning_days=expiry_warning_days
        )
    
    def register_credential(
        self,
        name: str,
        value: str,
        expires_at: Optional[datetime] = None,
        metadata: Optional[Dict] = None
    ):
        """
        Register a credential for rotation management.
        
        Args:
            name: Credential identifier
            value: Secret value
            expires_at: Optional expiration timestamp
            metadata: Additional metadata
        """
        credential = Credential(
            name=name,
            value=value,
            created_at=datetime.utcnow(),
            expires_at=expires_at,
            metadata=metadata or {}
        )
        
        self.credentials[name] = credential
        
        logger.info(
            f"Registered credential: {name}",
            expires_at=expires_at,
            has_expiry=expires_at is not None
        )
    
    async def rotate_credential(
        self,
        name: str,
        new_value: str,
        validator: Optional[Callable[[str], bool]] = None,
        new_expires_at: Optional[datetime] = None
    ) -> bool:
        """
        Rotate a credential with zero downtime.
        
        Process:
        1. Validate new credential (if validator provided)
        2. Enter dual-credential mode (both old and new active)
        3. Wait rotation_window_hours
        4. Deactivate old credential
        
        Args:
            name: Credential to rotate
            new_value: New secret value
            validator: Optional validation function
            new_expires_at: New expiration timestamp
        
        Returns:
            True if rotation successful, False otherwise
        """
        if name not in self.credentials:
            logger.error(f"Credential not found: {name}")
            return False
        
        old_credential = self.credentials[name]
        
        logger.info(f"🔄 Starting rotation for: {name}")
        
        # Step 1: Validate new credential
        if validator:
            try:
                validation_task = asyncio.create_task(
                    asyncio.to_thread(validator, new_value)
                )
                is_valid = await asyncio.wait_for(
                    validation_task,
                    timeout=self.validation_timeout
                )
                
                if not is_valid:
                    logger.error(f"❌ Validation failed for new credential: {name}")
                    self.rotation_total.labels(
                        credential_name=name,
                        status='validation_failed'
                    ).inc()
                    return False
                
                logger.info(f"✅ New credential validated: {name}")
                
            except asyncio.TimeoutError:
                logger.error(f"⏱️ Validation timeout for: {name}")
                self.rotation_total.labels(
                    credential_name=name,
                    status='timeout'
                ).inc()
                return False
            except Exception as e:
                logger.error(f"❌ Validation error for {name}: {e}")
                self.rotation_total.labels(
                    credential_name=name,
                    status='error'
                ).inc()
                return False
        
        # Step 2: Enter dual-credential mode
        old_credential.status = CredentialStatus.ROTATING
        old_credential.rotation_scheduled_at = datetime.utcnow() + timedelta(
            hours=self.rotation_window_hours
        )
        
        # Create new credential
        new_credential = Credential(
            name=f"{name}_new",
            value=new_value,
            created_at=datetime.utcnow(),
            expires_at=new_expires_at,
            status=CredentialStatus.ACTIVE,
            metadata=old_credential.metadata.copy()
        )
        
        self.credentials[f"{name}_new"] = new_credential
        
        logger.info(
            f"⏳ Dual-credential mode active for: {name}",
            rotation_window_hours=self.rotation_window_hours
        )
        
        # Step 3: Wait rotation window
        await asyncio.sleep(self.rotation_window_hours * 3600)
        
        # Step 4: Deactivate old credential
        old_credential.status = CredentialStatus.REVOKED
        
        # Replace old credential with new
        del self.credentials[name]
        self.credentials[name] = new_credential
        new_credential.name = name  # Remove "_new" suffix
        
        # Remove temporary "_new" entry
        if f"{name}_new" in self.credentials:
            del self.credentials[f"{name}_new"]
        
        logger.info(f"✅ Rotation complete for: {name}")
        self.rotation_total.labels(
            credential_name=name,
            status='success'
        ).inc()
        
        return True
    
    async def start_monitoring(self):
        """Start background monitoring for expiring credentials."""
        if self._running:
            logger.warning("Monitoring already running")
            return
        
        self._running = True
        self._monitoring_task = asyncio.create_task(self._monitor_expiry())
        logger.info("Started credential expiry monitoring")
    
    async def stop_monitoring(self):
        """Stop background monitoring."""
        self._running = False
        
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Stopped credential expiry monitoring")
    
    async def _monitor_expiry(self):
        """Background task to monitor credential expiry."""
        while self._running:
            try:
                for name, credential in self.credentials.items():
                    # Update age metric
                    age_days = (datetime.utcnow() - credential.created_at).days
                    self.credential_age_gauge.labels(
                        credential_name=name
                    ).set(age_days)
                    
                    # Check expiry
                    if credential.is_expired():
                        logger.critical(
                            f"🚨 CREDENTIAL EXPIRED: {name}",
                            expired_at=credential.expires_at
                        )
                        credential.status = CredentialStatus.EXPIRED
                    
                    elif credential.is_expiring_soon(self.expiry_warning_days):
                        time_remaining = credential.time_until_expiry()
                        logger.warning(
                            f"⚠️ Credential expiring soon: {name}",
                            expires_at=credential.expires_at,
                            days_remaining=time_remaining.days if time_remaining else None
                        )
                        self.expiry_warnings.labels(
                            credential_name=name
                        ).inc()
                
                # Check every hour
                await asyncio.sleep(3600)
                
            except Exception as e:
                logger.error(f"Error in expiry monitoring: {e}")
                await asyncio.sleep(60)  # Back off on error
    
    def get_credential(self, name: str) -> Optional[str]:
        """
        Get current active credential value.
        
        Args:
            name: Credential name
        
        Returns:
            Credential value if active, None otherwise
        """
        credential = self.credentials.get(name)
        
        if credential is None:
            return None
        
        if credential.status != CredentialStatus.ACTIVE:
            logger.warning(
                f"Credential not active: {name}",
                status=credential.status.value
            )
            return None
        
        if credential.is_expired():
            logger.error(f"Credential expired: {name}")
            return None
        
        return credential.value
    
    def get_status(self) -> Dict:
        """
        Get rotation service status.
        
        Returns:
            Dictionary with service status and credential summary
        """
        credential_summary = []
        
        for name, cred in self.credentials.items():
            time_remaining = cred.time_until_expiry()
            
            credential_summary.append({
                'name': name,
                'status': cred.status.value,
                'created_at': cred.created_at.isoformat(),
                'expires_at': cred.expires_at.isoformat() if cred.expires_at else None,
                'days_until_expiry': time_remaining.days if time_remaining else None,
                'is_expiring_soon': cred.is_expiring_soon(self.expiry_warning_days)
            })
        
        return {
            'monitoring_active': self._running,
            'total_credentials': len(self.credentials),
            'credentials': credential_summary
        }


# Singleton instance
_rotation_service: Optional[SecretRotationService] = None


def get_rotation_service() -> SecretRotationService:
    """Get global rotation service instance."""
    global _rotation_service
    
    if _rotation_service is None:
        _rotation_service = SecretRotationService()
    
    return _rotation_service
