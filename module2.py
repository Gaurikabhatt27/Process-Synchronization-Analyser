import threading
import time
from collections import defaultdict
from typing import Dict, Set, List, Optional

class RuntimeMonitoringEngine:
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
        with self.engine_lock:
            self.thread_registry[thread_id] = thread_name

    def register_lock(self, lock_id: int, lock_identity: str) -> None:
        with self.engine_lock:
            self.lock_registry[lock_id] = lock_identity

    def pre_acquire(self, thread_id: int, lock_id: int) -> Optional[List[str]]:
        with self.engine_lock:
            if lock_id in self.lock_owners and self.lock_owners[lock_id] != thread_id:
                self.lock_graph[thread_id].add(lock_id)
                deadlock = self._check_deadlock(thread_id)
                if deadlock:
                    return deadlock
            return None

    def post_acquire(self, thread_id: int, lock_id: int) -> None:
        with self.engine_lock:
            self.lock_owners[lock_id] = thread_id
            if lock_id in self.lock_graph[thread_id]:
                self.lock_graph[thread_id].remove(lock_id)

    def release(self, thread_id: int, lock_id: int) -> None:
        with self.engine_lock:
            if lock_id in self.lock_owners and self.lock_owners[lock_id] == thread_id:
                del self.lock_owners[lock_id]

    def _check_deadlock(self, starting_thread: int) -> Optional[List[str]]:
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
                thread_name = self.thread_registry.get(thread_id, f"UnknownThread-{thread_id}")
                lock_name = self.lock_registry.get(connecting_lock, f"UnknownLock-{connecting_lock}")
                next_thread_name = self.thread_registry.get(next_thread_id, f"UnknownThread-{next_thread_id}")
                result.append(f"{thread_name} is waiting for {lock_name} held by {next_thread_name}")
        
        return result

    def get_current_dependencies(self) -> Dict[str, List[str]]:
        with self.engine_lock:
            graph = {}
            for thread_id, locks in self.lock_graph.items():
                if locks:
                    thread_name = self.thread_registry.get(thread_id, f"UnknownThread-{thread_id}")
                    deps = []
                    for lock_id in locks:
                        if lock_id in self.lock_owners:
                            owner_thread = self.lock_owners[lock_id]
                            owner_name = self.thread_registry.get(owner_thread, f"UnknownThread-{owner_thread}")
                            lock_name = self.lock_registry.get(lock_id, f"UnknownLock-{lock_id}")
                            deps.append(f"waiting for {lock_name} (held by {owner_name})")
                    if deps:
                        graph[thread_name] = deps
            return graph


class MonitoredLock:
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
        thread_id = threading.get_ident()
        thread_name = threading.current_thread().name
        self.monitor.register_thread(thread_id, thread_name)
        
        # Check for potential deadlock before acquiring
        deadlock = self.monitor.pre_acquire(thread_id, self.lock_id)
        if deadlock:
            print("\nDEADLOCK DETECTED!")
            for edge in deadlock:
                print(f"  - {edge}")
            print()
            if not blocking:
                return False
        
        # Actually attempt to acquire the lock
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
        thread_id = threading.get_ident()
        self.monitor.release(thread_id, self.lock_id)
        self.lock.release()

    def __enter__(self):
        return self.acquire()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()


def worker(lock1: MonitoredLock, lock2: MonitoredLock, name: str):
    print(f"{name} starting")
    if not lock1.acquire(blocking=True, timeout=5):
        print(f"{name} failed to acquire {lock1.name}")
        return
    
    try:
        print(f"{name} acquired {lock1.name}")
        time.sleep(1)  # Ensure deadlock occurs
        
        print(f"{name} attempting to acquire {lock2.name}")
        if not lock2.acquire(blocking=True, timeout=5):
            print(f"{name} failed to acquire {lock2.name}")
            return
            
        try:
            print(f"{name} acquired {lock2.name}")
            time.sleep(0.5)
        finally:
            lock2.release()
    finally:
        lock1.release()
    print(f"{name} finished")

def create_deadlock():
    lock_a = MonitoredLock("LockA")
    lock_b = MonitoredLock("LockB")
    
    t1 = threading.Thread(target=worker, args=(lock_a, lock_b, "Thread-1"), name="Thread-1")
    t2 = threading.Thread(target=worker, args=(lock_b, lock_a, "Thread-2"), name="Thread-2")
    
    t1.start()
    time.sleep(0.5)  # Ensure Thread-1 starts first
    t2.start()
    
    monitor = RuntimeMonitoringEngine()
    
    for i in range(5):
        time.sleep(1)
        print(f"\nStatus check {i+1}:")
        deps = monitor.get_current_dependencies()
        if deps:
            for thread, waits in deps.items():
                print(f"  {thread}:")
                for wait in waits:
                    print(f"    {wait}")
        else:
            print("  No waiting threads detected")
    
    t1.join(timeout=2)
    t2.join(timeout=2)
    print("\nExample completed")

if __name__ == "__main__":
    print("Starting deadlock example...")
    create_deadlock()