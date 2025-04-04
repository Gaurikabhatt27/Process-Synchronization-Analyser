import threading
import time
from collections import defaultdict
from typing import Dict, Set, List, Optional

class RuntimeMonitoringEngine:
    """
    A runtime monitor for detecting synchronization issues in multi-threaded applications.
    Tracks:
    - Thread creation/termination
    - Lock acquisition/release sequences
    - Deadlocks in real-time
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if not self._initialized:
            self.thread_registry: Dict[int, str] = {}
            self.lock_registry: Dict[int, str] = {}
            self.lock_graph: Dict[int, Set[int]] = defaultdict(set)
            self.lock_owners: Dict[int, int] = {}
            self.engine_lock = threading.Lock()
            self._initialized = True

    def register_thread(self, thread_id: int, thread_name: str) -> None:
        """Register a thread with the monitoring system"""
        with self.engine_lock:
            self.thread_registry[thread_id] = thread_name

    def register_lock(self, lock_id: int, lock_identity: str) -> None:
        """Register a lock with the monitoring system"""
        with self.engine_lock:
            self.lock_registry[lock_id] = lock_identity

    def pre_acquire(self, thread_id: int, lock_id: int) -> Optional[List[str]]:
        """
        Called before a thread attempts to acquire a lock.
        Returns deadlock information if detected.
        """
        with self.engine_lock:
            if lock_id in self.lock_owners and self.lock_owners[lock_id] != thread_id:
                self.lock_graph[thread_id].add(lock_id)
                deadlock = self._check_deadlock(thread_id)
                if deadlock:
                    return deadlock
            return None

    def post_acquire(self, thread_id: int, lock_id: int) -> None:
        """Called after a thread successfully acquires a lock"""
        with self.engine_lock:
            self.lock_owners[lock_id] = thread_id
            if lock_id in self.lock_graph[thread_id]:
                self.lock_graph[thread_id].remove(lock_id)

    def release(self, thread_id: int, lock_id: int) -> None:
        """Called when a thread releases a lock"""
        with self.engine_lock:
            if lock_id in self.lock_owners and self.lock_owners[lock_id] == thread_id:
                del self.lock_owners[lock_id]

    def _check_deadlock(self, starting_thread: int) -> Optional[List[str]]:
        """Detect deadlocks using cycle detection in the wait-for graph"""
        visited = set()
        stack = []
        cycle = []
        
        def dfs(thread_id):
            nonlocal cycle
            if thread_id in stack:
                cycle = stack[stack.index(thread_id):] + [thread_id]
                return True
            if thread_id in visited:
                return False
                
            visited.add(thread_id)
            stack.append(thread_id)
            
            for lock_id in self.lock_graph.get(thread_id, set()):
                if lock_id in self.lock_owners:
                    owner_thread = self.lock_owners[lock_id]
                    if dfs(owner_thread):
                        return True
                        
            stack.pop()
            return False
            
        if dfs(starting_thread):
            return self._format_cycle(cycle)
        return None

    def _format_cycle(self, cycle: List[int]) -> List[str]:
        """Format deadlock cycle into human-readable strings"""
        result = []
        for i in range(len(cycle) - 1):
            thread_id = cycle[i]
            next_thread_id = cycle[i+1]
            
            connecting_lock = None
            for lock_id in self.lock_graph.get(thread_id, set()):
                if lock_id in self.lock_owners and self.lock_owners[lock_id] == next_thread_id:
                    connecting_lock = lock_id
                    break
            
            if connecting_lock:
                thread_name = self.thread_registry.get(thread_id, f"Thread-{thread_id}")
                lock_name = self.lock_registry.get(connecting_lock, f"Lock-{connecting_lock}")
                next_thread_name = self.thread_registry.get(next_thread_id, f"Thread-{next_thread_id}")
                result.append(f"{thread_name} → waiting for {lock_name} (held by {next_thread_name})")
        
        return result

    def get_wait_graph(self) -> Dict[str, List[str]]:
        """
        Get current wait-for graph as {thread: [dependencies]}
        Example output:
        {
            "Thread-1": ["waiting for LockB (held by Thread-2)"],
            "Thread-2": ["waiting for LockA (held by Thread-1)"]
        }
        """
        with self.engine_lock:
            graph = {}
            for thread_id, locks in self.lock_graph.items():
                if locks:
                    thread_name = self.thread_registry.get(thread_id, f"Thread-{thread_id}")
                    deps = []
                    for lock_id in locks:
                        if lock_id in self.lock_owners:
                            owner_thread = self.lock_owners[lock_id]
                            owner_name = self.thread_registry.get(owner_thread, f"Thread-{owner_thread}")
                            lock_name = self.lock_registry.get(lock_id, f"Lock-{lock_id}")
                            deps.append(f"waiting for {lock_name} (held by {owner_name})")
                    if deps:
                        graph[thread_name] = deps
            return graph

    def visualize_dependencies(self) -> str:
        """Generate a text visualization of the current wait-for graph"""
        graph = self.get_wait_graph()
        if not graph:
            return "No waiting dependencies detected"
        
        output = ["Current Wait-For Graph:"]
        for thread, deps in graph.items():
            output.append(f"{thread}:")
            for dep in deps:
                output.append(f"  ├─ {dep}")
        return "\n".join(output)


class MonitoredLock:
    """
    Threading lock with built-in monitoring capabilities.
    Usage:
    lock = MonitoredLock("DescriptiveName")
    with lock:
        # critical section
    """
    
    _lock_counter = 0
    _counter_lock = threading.Lock()
    
    def __init__(self, name: str):
        self.lock = threading.Lock()
        self.name = name
        self.monitor = RuntimeMonitoringEngine()
        with MonitoredLock._counter_lock:
            MonitoredLock._lock_counter += 1
            self.lock_id = MonitoredLock._lock_counter
        self.monitor.register_lock(self.lock_id, self.name)

    def acquire(self, blocking=True, timeout=None) -> bool:
        """Acquire the lock with deadlock detection"""
        thread_id = threading.get_ident()
        thread_name = threading.current_thread().name
        self.monitor.register_thread(thread_id, thread_name)
        
        deadlock = self.monitor.pre_acquire(thread_id, self.lock_id)
        if deadlock:
            if blocking:
                print("\nDEADLOCK DETECTED!")
                for edge in deadlock:
                    print(f"  - {edge}")
                print()
            return False
        
        acquired = False
        try:
            if timeout is not None:
                acquired = self.lock.acquire(blocking=blocking, timeout=timeout)
            else:
                acquired = self.lock.acquire(blocking=blocking)
        except Exception as e:
            print(f"Lock acquisition error: {e}")
            return False
            
        if acquired:
            self.monitor.post_acquire(thread_id, self.lock_id)
        return acquired

    def release(self) -> None:
        """Release the lock"""
        thread_id = threading.get_ident()
        self.monitor.release(thread_id, self.lock_id)
        self.lock.release()

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()



