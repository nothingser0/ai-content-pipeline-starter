#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Prometheus metrics for content pipeline monitoring
Tracks generation performance, API calls, and quality scores
"""

import os
from typing import Optional

try:
    from prometheus_client import Counter, Histogram, Gauge, CollectorRegistry, REGISTRY
    METRICS_ENABLED = os.getenv("ENABLE_METRICS", "0") == "1"
except ImportError:
    METRICS_ENABLED = False
    Counter = None
    Histogram = None
    Gauge = None
    CollectorRegistry = None
    REGISTRY = None


class ContentMetrics:
    """Prometheus metrics for content pipeline"""
    
    def __init__(self, registry: Optional[object] = None):
        """Initialize metrics with optional custom registry"""
        if not METRICS_ENABLED:
            return
            
        self.registry = registry or REGISTRY
        
        # Counter: Total content generated
        self.content_generated_total = Counter(
            "content_generated_total",
            "Total content pieces generated",
            ["account", "format", "status"],
            registry=self.registry
        )
        
        # Histogram: Generation duration
        self.generation_duration_seconds = Histogram(
            "generation_duration_seconds",
            "Time taken to generate content",
            ["account", "format"],
            buckets=[1, 5, 10, 30, 60, 120, 300],
            registry=self.registry
        )
        
        # Histogram: API call duration
        self.api_call_duration_seconds = Histogram(
            "api_call_duration_seconds",
            "API call latency",
            ["service", "model"],
            buckets=[0.1, 0.5, 1, 2, 5, 10, 30, 60],
            registry=self.registry
        )
        
        # Gauge: QC score
        self.qc_score = Gauge(
            "qc_score",
            "Quality control score",
            ["account", "format"],
            registry=self.registry
        )
        
        # Counter: API errors
        self.api_errors_total = Counter(
            "api_errors_total",
            "Total API errors",
            ["service", "error_type"],
            registry=self.registry
        )
        
        # Gauge: Circuit breaker state (0=closed, 1=open, 2=half_open)
        self.circuit_breaker_state = Gauge(
            "circuit_breaker_state",
            "Circuit breaker state (0=closed, 1=open, 2=half_open)",
            registry=self.registry
        )
        
        # Counter: Circuit breaker state transitions
        self.circuit_breaker_transitions_total = Counter(
            "circuit_breaker_transitions_total",
            "Total circuit breaker state transitions",
            ["from_state", "to_state"],
            registry=self.registry
        )
        
        # Counter: Fallback cache hits
        self.fallback_cache_hits_total = Counter(
            "fallback_cache_hits_total",
            "Total fallback cache hits",
            registry=self.registry
        )
        
        # Gauge: Retry budget remaining per account
        self.retry_budget_remaining = Gauge(
            "retry_budget_remaining",
            "Remaining retry budget per account",
            ["account"],
            registry=self.registry
        )
        
        # Counter: Retry budget exhausted events
        self.retry_budget_exhausted_total = Counter(
            "retry_budget_exhausted_total",
            "Total retry budget exhausted events",
            ["account"],
            registry=self.registry
        )
        
        # Counter: Retry budget consumed
        self.retry_budget_consumed_total = Counter(
            "retry_budget_consumed_total",
            "Total retries consumed from budget",
            ["account"],
            registry=self.registry
        )


# Global metrics instance
_metrics: Optional[ContentMetrics] = None


def get_metrics() -> Optional[ContentMetrics]:
    """Get or create global metrics instance"""
    global _metrics
    if not METRICS_ENABLED:
        return None
    if _metrics is None:
        _metrics = ContentMetrics()
    return _metrics


def record_content_generated(account: str, format: str, status: str) -> None:
    """Record content generation event
    
    Args:
        account: Account ID
        format: Content format (Single Tweet, Thread, Poll, Image)
        status: Generation status (success, failed, qc_failed)
    """
    metrics = get_metrics()
    if metrics:
        metrics.content_generated_total.labels(
            account=account,
            format=format,
            status=status
        ).inc()


def record_generation_duration(account: str, format: str, duration: float) -> None:
    """Record content generation duration
    
    Args:
        account: Account ID
        format: Content format
        duration: Duration in seconds
    """
    metrics = get_metrics()
    if metrics:
        metrics.generation_duration_seconds.labels(
            account=account,
            format=format
        ).observe(duration)


def record_api_call_duration(service: str, model: str, duration: float) -> None:
    """Record API call duration
    
    Args:
        service: Service name (openai, anthropic, etc.)
        model: Model name
        duration: Duration in seconds
    """
    metrics = get_metrics()
    if metrics:
        metrics.api_call_duration_seconds.labels(
            service=service,
            model=model
        ).observe(duration)


def record_qc_score(account: str, format: str, score: float) -> None:
    """Record quality control score
    
    Args:
        account: Account ID
        format: Content format
        score: QC score (0-10)
    """
    metrics = get_metrics()
    if metrics:
        metrics.qc_score.labels(
            account=account,
            format=format
        ).set(score)


def record_api_error(service: str, error_type: str) -> None:
    """Record API error
    
    Args:
        service: Service name
        error_type: Error type (timeout, rate_limit, server_error, client_error)
    """
    metrics = get_metrics()
    if metrics:
        metrics.api_errors_total.labels(
            service=service,
            error_type=error_type
        ).inc()


def update_circuit_breaker_state(state: int) -> None:
    """Update circuit breaker state gauge
    
    Args:
        state: Circuit state (0=closed, 1=open, 2=half_open)
    """
    metrics = get_metrics()
    if metrics:
        metrics.circuit_breaker_state.set(state)


def record_circuit_breaker_transition(from_state: str, to_state: str) -> None:
    """Record circuit breaker state transition
    
    Args:
        from_state: Previous state name
        to_state: New state name
    """
    metrics = get_metrics()
    if metrics:
        metrics.circuit_breaker_transitions_total.labels(
            from_state=from_state,
            to_state=to_state
        ).inc()


def record_fallback_cache_hit() -> None:
    """Record fallback cache hit"""
    metrics = get_metrics()
    if metrics:
        metrics.fallback_cache_hits_total.inc()


def update_retry_budget_remaining(account: str, remaining: int) -> None:
    """Update retry budget remaining gauge
    
    Args:
        account: Account ID
        remaining: Remaining retry budget
    """
    metrics = get_metrics()
    if metrics:
        metrics.retry_budget_remaining.labels(account=account).set(remaining)


def record_retry_budget_exhausted(account: str) -> None:
    """Record retry budget exhausted event
    
    Args:
        account: Account ID
    """
    metrics = get_metrics()
    if metrics:
        metrics.retry_budget_exhausted_total.labels(account=account).inc()


def record_retry_budget_consumed(account: str) -> None:
    """Record retry consumed from budget
    
    Args:
        account: Account ID
    """
    metrics = get_metrics()
    if metrics:
        metrics.retry_budget_consumed_total.labels(account=account).inc()
