#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Circuit Breaker Pattern - Prevent cascade failures
3 states: CLOSED (normal), OPEN (failing), HALF_OPEN (testing recovery)
"""

import asyncio
import time
from enum import Enum
from typing import Optional

from infrastructure.logging.logger import setup_logger

logger = setup_logger(__name__)


class CircuitState(Enum):
    """Circuit breaker states"""
    CLOSED = 0      # Normal operation
    OPEN = 1        # Failing, reject requests
    HALF_OPEN = 2   # Testing recovery


class CircuitBreaker:
    """
    Circuit breaker with 3-state FSM
    
    Thresholds:
    - 3 consecutive failures → OPEN for 5 minutes
    - After 5 minutes: HALF_OPEN (allow 1 test request)
    - If test succeeds: CLOSED, if fails: OPEN again
    
    Thread-safe using asyncio.Lock
    """
    
    # Singleton instance (shared across all APIClient instances)
    _instance: Optional['CircuitBreaker'] = None
    _lock = asyncio.Lock()
    
    def __new__(cls, *args, **kwargs):
        """Singleton pattern"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(
        self,
        failure_threshold: int = 3,
        recovery_timeout: float = 300.0,  # 5 minutes
        success_threshold: int = 1,
    ):
        """
        Initialize circuit breaker
        
        Args:
            failure_threshold: Consecutive failures to open circuit
            recovery_timeout: Seconds to wait before testing recovery
            success_threshold: Consecutive successes to close circuit
        """
        # Only initialize once (singleton)
        if hasattr(self, '_initialized'):
            return
            
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: Optional[float] = None
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._success_threshold = success_threshold
        self._state_lock = asyncio.Lock()
        self._initialized = True
        
        logger.info(
            f"Circuit breaker initialized: "
            f"failure_threshold={failure_threshold}, "
            f"recovery_timeout={recovery_timeout}s"
        )
    
    async def get_state(self) -> CircuitState:
        """Get current circuit state (thread-safe)"""
        async with self._state_lock:
            return self._state
    
    async def is_open(self) -> bool:
        """Check if circuit is open (rejecting requests)"""
        async with self._state_lock:
            # If OPEN, check if recovery timeout elapsed
            if self._state == CircuitState.OPEN:
                if self._last_failure_time is None:
                    return True
                    
                elapsed = time.time() - self._last_failure_time
                if elapsed >= self._recovery_timeout:
                    # Transition to HALF_OPEN
                    await self._transition_to(CircuitState.HALF_OPEN)
                    return False
                return True
            
            return False
    
    async def record_success(self) -> None:
        """Record successful API call"""
        async with self._state_lock:
            if self._state == CircuitState.HALF_OPEN:
                # Test request succeeded, close circuit
                self._success_count += 1
                if self._success_count >= self._success_threshold:
                    await self._transition_to(CircuitState.CLOSED)
                    self._failure_count = 0
                    self._success_count = 0
                    logger.info("Circuit breaker closed after successful test")
            
            elif self._state == CircuitState.CLOSED:
                # Reset failure count on success
                self._failure_count = 0
    
    async def record_failure(self) -> None:
        """Record failed API call"""
        async with self._state_lock:
            self._last_failure_time = time.time()
            
            if self._state == CircuitState.HALF_OPEN:
                # Test request failed, reopen circuit
                await self._transition_to(CircuitState.OPEN)
                self._success_count = 0
                logger.warning("Circuit breaker reopened after failed test")
            
            elif self._state == CircuitState.CLOSED:
                # Increment failure count
                self._failure_count += 1
                if self._failure_count >= self._failure_threshold:
                    await self._transition_to(CircuitState.OPEN)
                    logger.warning(
                        f"Circuit breaker opened after {self._failure_count} failures"
                    )
    
    async def _transition_to(self, new_state: CircuitState) -> None:
        """Transition to new state (must hold lock)"""
        old_state = self._state
        self._state = new_state
        
        # Record state transition metric
        try:
            from infrastructure.monitoring.metrics import record_circuit_breaker_transition
            record_circuit_breaker_transition(old_state.name, new_state.name)
        except ImportError:
            pass
        
        # Update state gauge
        try:
            from infrastructure.monitoring.metrics import update_circuit_breaker_state
            update_circuit_breaker_state(new_state.value)
        except ImportError:
            pass
        
        logger.info(f"Circuit breaker: {old_state.name} → {new_state.name}")
    
    async def reset(self) -> None:
        """Reset circuit breaker to CLOSED state (for testing)"""
        async with self._state_lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._success_count = 0
            self._last_failure_time = None
            logger.info("Circuit breaker reset to CLOSED")


# Global singleton instance
def get_circuit_breaker() -> CircuitBreaker:
    """Get global circuit breaker instance"""
    return CircuitBreaker()
