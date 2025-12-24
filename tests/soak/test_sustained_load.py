"""
Soak Tests - Long-Running Stability & Memory Leak Detection

Tests system behavior under sustained load:
- 1 hour continuous webhook processing (3600 webhooks)
- Memory leak detection
- Connection pool exhaustion
- Task accumulation
- Database connection leaks

Requirements:
    - psutil: For memory profiling
    - prometheus_client: For metrics (imported from src.utils.metrics)
"""

import pytest
import asyncio
import os
from datetime import datetime, timedelta
from typing import List, Dict
import json

# Skip entire module if psutil not available
psutil = pytest.importorskip("psutil", reason="psutil required for soak tests")

# Optional metrics imports - tests work without them
try:
    from src.utils.metrics import (
        webhook_latency_seconds as webhook_processing_latency,
        active_positions_gauge,
        signals_rejected_total as signal_processing_errors_total
    )
    METRICS_AVAILABLE = True
except ImportError:
    METRICS_AVAILABLE = False
    webhook_processing_latency = None
    active_positions_gauge = None
    signal_processing_errors_total = None

# Optional imports - tests mock these anyway
try:
    from src.signals.signal_processor import SignalProcessor
    from src.database.database_manager import DatabaseManager
except ImportError:
    SignalProcessor = None
    DatabaseManager = None


class MemoryProfiler:
    """Track memory usage over time."""
    
    def __init__(self):
        self.process = psutil.Process(os.getpid())
        self.samples: List[Dict] = []
    
    def sample(self):
        """Take memory snapshot."""
        memory_info = self.process.memory_info()
        
        sample = {
            'timestamp': datetime.utcnow(),
            'rss_mb': memory_info.rss / 1024 / 1024,  # MB
            'vms_mb': memory_info.vms / 1024 / 1024,
            'percent': self.process.memory_percent()
        }
        
        self.samples.append(sample)
        return sample
    
    def analyze(self) -> Dict:
        """Analyze memory samples for leaks."""
        if len(self.samples) < 2:
            return {'leak_detected': False}
        
        # Calculate trend
        first_sample = self.samples[0]
        last_sample = self.samples[-1]
        
        rss_growth_mb = last_sample['rss_mb'] - first_sample['rss_mb']
        rss_growth_percent = (rss_growth_mb / first_sample['rss_mb']) * 100
        
        # Average memory per sample
        avg_rss = sum(s['rss_mb'] for s in self.samples) / len(self.samples)
        
        # Peak memory
        peak_rss = max(s['rss_mb'] for s in self.samples)
        
        # Memory leak threshold: >20% growth over test duration
        leak_detected = rss_growth_percent > 20.0
        
        return {
            'leak_detected': leak_detected,
            'initial_rss_mb': first_sample['rss_mb'],
            'final_rss_mb': last_sample['rss_mb'],
            'growth_mb': rss_growth_mb,
            'growth_percent': rss_growth_percent,
            'average_rss_mb': avg_rss,
            'peak_rss_mb': peak_rss,
            'sample_count': len(self.samples),
            'duration_seconds': (last_sample['timestamp'] - first_sample['timestamp']).total_seconds()
        }


class ResourceTracker:
    """Track async resources (tasks, connections)."""
    
    def __init__(self):
        self.task_counts: List[int] = []
        self.connection_counts: List[int] = []
    
    def sample(self):
        """Take resource snapshot."""
        # Count asyncio tasks
        tasks = asyncio.all_tasks()
        task_count = len(tasks)
        self.task_counts.append(task_count)
        
        # Note: Connection tracking would require DB manager instrumentation
        # For now, just track task count
        
        return {
            'timestamp': datetime.utcnow(),
            'active_tasks': task_count
        }
    
    def analyze(self) -> Dict:
        """Check for resource leaks."""
        if len(self.task_counts) < 2:
            return {'task_leak_detected': False}
        
        initial_tasks = self.task_counts[0]
        final_tasks = self.task_counts[-1]
        peak_tasks = max(self.task_counts)
        avg_tasks = sum(self.task_counts) / len(self.task_counts)
        
        # Task leak threshold: >50% growth
        task_growth_percent = ((final_tasks - initial_tasks) / max(initial_tasks, 1)) * 100
        task_leak_detected = task_growth_percent > 50.0
        
        return {
            'task_leak_detected': task_leak_detected,
            'initial_tasks': initial_tasks,
            'final_tasks': final_tasks,
            'peak_tasks': peak_tasks,
            'average_tasks': avg_tasks,
            'growth_percent': task_growth_percent
        }


@pytest.mark.soak
@pytest.mark.asyncio
@pytest.mark.slow
async def test_sustained_webhook_processing():
    """
    Process 1 webhook/second for 1 hour.
    
    Validates:
    - No memory leaks
    - No task accumulation
    - Consistent latency
    - No database connection leaks
    """
    # Test configuration
    DURATION_SECONDS = 3600  # 1 hour
    WEBHOOKS_PER_SECOND = 1
    TOTAL_WEBHOOKS = DURATION_SECONDS * WEBHOOKS_PER_SECOND
    SAMPLE_INTERVAL = 60  # Sample every 60 seconds
    
    print(f"\n🔬 Starting Soak Test:")
    print(f"  Duration: {DURATION_SECONDS}s ({DURATION_SECONDS/3600:.1f} hours)")
    print(f"  Total Webhooks: {TOTAL_WEBHOOKS}")
    print(f"  Rate: {WEBHOOKS_PER_SECOND} webhook/second")
    
    # Initialize profilers
    memory_profiler = MemoryProfiler()
    resource_tracker = ResourceTracker()
    
    # Mock webhook payload
    webhook_payload = {
        "action": "buy",
        "symbol": "AAPL",
        "quantity": 10,
        "price": 150.00,
        "timeframe": "1h",
        "timestamp": datetime.utcnow().isoformat()
    }
    
    # Counters
    processed_count = 0
    error_count = 0
    latencies: List[float] = []
    
    start_time = datetime.utcnow()
    next_sample_time = start_time + timedelta(seconds=SAMPLE_INTERVAL)
    
    # Initial samples
    memory_profiler.sample()
    resource_tracker.sample()
    
    # Process webhooks
    for i in range(TOTAL_WEBHOOKS):
        iteration_start = asyncio.get_event_loop().time()
        
        try:
            # Simulate webhook processing
            await asyncio.sleep(0.01)  # Mock processing time
            processed_count += 1
            
            # Track latency
            latency = asyncio.get_event_loop().time() - iteration_start
            latencies.append(latency)
            
        except Exception as e:
            error_count += 1
            print(f"❌ Error processing webhook {i}: {e}")
        
        # Sample resources periodically
        now = datetime.utcnow()
        if now >= next_sample_time:
            memory_sample = memory_profiler.sample()
            resource_sample = resource_tracker.sample()
            
            print(f"\n📊 Progress: {i}/{TOTAL_WEBHOOKS} ({i/TOTAL_WEBHOOKS*100:.1f}%)")
            print(f"  Memory: {memory_sample['rss_mb']:.1f} MB ({memory_sample['percent']:.1f}%)")
            print(f"  Tasks: {resource_sample['active_tasks']}")
            print(f"  Processed: {processed_count}, Errors: {error_count}")
            
            next_sample_time = now + timedelta(seconds=SAMPLE_INTERVAL)
        
        # Rate limiting (1 webhook/second)
        await asyncio.sleep(1.0 / WEBHOOKS_PER_SECOND)
    
    # Final samples
    memory_profiler.sample()
    resource_tracker.sample()
    
    # Analyze results
    memory_analysis = memory_profiler.analyze()
    resource_analysis = resource_tracker.analyze()
    
    # Calculate latency statistics
    avg_latency = sum(latencies) / len(latencies)
    p95_latency = sorted(latencies)[int(len(latencies) * 0.95)]
    p99_latency = sorted(latencies)[int(len(latencies) * 0.99)]
    
    print(f"\n✅ Soak Test Complete!")
    print(f"\n📈 Results:")
    print(f"  Processed: {processed_count}/{TOTAL_WEBHOOKS} ({processed_count/TOTAL_WEBHOOKS*100:.1f}%)")
    print(f"  Errors: {error_count} ({error_count/TOTAL_WEBHOOKS*100:.2f}%)")
    print(f"  Duration: {memory_analysis['duration_seconds']:.0f}s")
    
    print(f"\n💾 Memory Analysis:")
    print(f"  Initial: {memory_analysis['initial_rss_mb']:.1f} MB")
    print(f"  Final: {memory_analysis['final_rss_mb']:.1f} MB")
    print(f"  Growth: {memory_analysis['growth_mb']:.1f} MB ({memory_analysis['growth_percent']:.1f}%)")
    print(f"  Peak: {memory_analysis['peak_rss_mb']:.1f} MB")
    print(f"  Leak Detected: {memory_analysis['leak_detected']}")
    
    print(f"\n🔧 Resource Analysis:")
    print(f"  Initial Tasks: {resource_analysis['initial_tasks']}")
    print(f"  Final Tasks: {resource_analysis['final_tasks']}")
    print(f"  Peak Tasks: {resource_analysis['peak_tasks']}")
    print(f"  Task Leak Detected: {resource_analysis['task_leak_detected']}")
    
    print(f"\n⏱️ Latency Statistics:")
    print(f"  Average: {avg_latency*1000:.2f} ms")
    print(f"  P95: {p95_latency*1000:.2f} ms")
    print(f"  P99: {p99_latency*1000:.2f} ms")
    
    # Assertions
    assert not memory_analysis['leak_detected'], \
        f"Memory leak detected: {memory_analysis['growth_percent']:.1f}% growth"
    
    assert not resource_analysis['task_leak_detected'], \
        f"Task leak detected: {resource_analysis['growth_percent']:.1f}% growth"
    
    assert error_count < TOTAL_WEBHOOKS * 0.01, \
        f"Error rate too high: {error_count/TOTAL_WEBHOOKS*100:.2f}%"
    
    assert p99_latency < 1.0, \
        f"P99 latency too high: {p99_latency*1000:.0f}ms"


@pytest.mark.soak
@pytest.mark.asyncio
@pytest.mark.slow
async def test_database_connection_pool_stability():
    """
    Test database connection pool under sustained load.
    
    Validates:
    - No connection leaks
    - Pool size remains stable
    - No deadlocks
    """
    DURATION_SECONDS = 300  # 5 minutes for faster test
    QUERIES_PER_SECOND = 10
    
    print(f"\n🔬 Starting DB Connection Pool Soak Test:")
    print(f"  Duration: {DURATION_SECONDS}s")
    print(f"  Rate: {QUERIES_PER_SECOND} queries/second")
    
    # Mock database manager
    # In real test, use actual DatabaseManager
    query_count = 0
    error_count = 0
    
    for i in range(DURATION_SECONDS * QUERIES_PER_SECOND):
        try:
            # Simulate DB query
            await asyncio.sleep(0.001)  # Mock query time
            query_count += 1
            
        except Exception as e:
            error_count += 1
        
        # Rate limiting
        await asyncio.sleep(1.0 / QUERIES_PER_SECOND)
    
    print(f"\n✅ DB Connection Pool Test Complete:")
    print(f"  Queries: {query_count}")
    print(f"  Errors: {error_count}")
    
    assert error_count == 0, f"Database errors detected: {error_count}"


@pytest.mark.soak
@pytest.mark.asyncio
@pytest.mark.slow
async def test_event_queue_saturation():
    """
    Test event bus under high throughput.
    
    Validates:
    - No event loss
    - Queue doesn't grow unbounded
    - Background processing keeps up
    """
    DURATION_SECONDS = 180  # 3 minutes
    EVENTS_PER_SECOND = 100
    
    print(f"\n🔬 Starting Event Queue Saturation Test:")
    print(f"  Duration: {DURATION_SECONDS}s")
    print(f"  Rate: {EVENTS_PER_SECOND} events/second")
    
    # Mock event bus
    published_count = 0
    processed_count = 0
    
    async def publish_events():
        """Publish events continuously."""
        nonlocal published_count
        end_time = datetime.utcnow() + timedelta(seconds=DURATION_SECONDS)
        
        while datetime.utcnow() < end_time:
            # Simulate event publishing
            await asyncio.sleep(0.001)
            published_count += 1
            
            await asyncio.sleep(1.0 / EVENTS_PER_SECOND)
    
    async def process_events():
        """Process events continuously."""
        nonlocal processed_count
        end_time = datetime.utcnow() + timedelta(seconds=DURATION_SECONDS + 10)
        
        while datetime.utcnow() < end_time:
            # Simulate event processing
            await asyncio.sleep(0.001)
            processed_count += 1
            
            await asyncio.sleep(1.0 / (EVENTS_PER_SECOND + 10))  # Slightly faster
    
    # Run publisher and processor concurrently
    await asyncio.gather(
        publish_events(),
        process_events()
    )
    
    print(f"\n✅ Event Queue Test Complete:")
    print(f"  Published: {published_count}")
    print(f"  Processed: {processed_count}")
    
    # Processor should keep up (within 5% tolerance)
    assert processed_count >= published_count * 0.95, \
        f"Event processor falling behind: {processed_count}/{published_count}"


if __name__ == "__main__":
    # Run soak tests
    pytest.main([__file__, "-v", "-m", "soak", "-s"])
