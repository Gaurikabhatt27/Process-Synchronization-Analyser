import threading
import time
from collections import defaultdict
from typing import Dict, Set, List, Optional

class RuntimeMonitoringEngine:
    """
    A runtime monitor for detecting synchronization issues in multi-threaded applications.
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
                thread_name = self.thread_registry.get(thread_id, f"Thread-{thread_id}")
                lock_name = self.lock_registry.get(connecting_lock, f"Lock-{connecting_lock}")
                next_thread_name = self.thread_registry.get(next_thread_id, f"Thread-{next_thread_id}")
                result.append(f"{thread_name} → waiting for {lock_name} (held by {next_thread_name})")
        
        return result

    def visualize_dependencies(self) -> str:
        graph = self.get_wait_graph()
        if not graph:
            return "No waiting dependencies detected"
        
        output = ["Current Wait-For Graph:"]
        for thread, deps in graph.items():
            output.append(f"{thread}:")
            for dep in deps:
                output.append(f"  ├─ {dep}")
        return "\n".join(output)

    def get_wait_graph(self) -> Dict[str, List[str]]:
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


class MonitoredLock:
    _lock_counter = 0
    _counter_lock = threading.Lock()

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            self.release()
        except RuntimeError as e:
            if "release unlocked lock" in str(e):
                pass  # Ignore double-release attempts
            else:
                raise
    
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
        thread_id = threading.get_ident()
        self.monitor.release(thread_id, self.lock_id)
        self.lock.release()

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()


def print_status(monitor):
    print("\n" + "="*50)
    print(monitor.visualize_dependencies())
    print("="*50 + "\n")

def scenario_runner(scenario_func, scenario_name):
    print(f"\n{'#'*20} Running {scenario_name} {'#'*20}")
    monitor = RuntimeMonitoringEngine()
    scenario_func(monitor)

def test_normal_operation(monitor):
    lock1 = MonitoredLock("ResourceA")
    lock2 = MonitoredLock("ResourceB")

    def safe_worker(worker_id):
        with lock1:
            with lock2:
                print(f"Worker {worker_id} entered critical section")
                time.sleep(0.5)

    threads = []
    for i in range(2):
        t = threading.Thread(target=safe_worker, args=(i+1,))
        threads.append(t)
        t.start()

    time.sleep(1)
    print_status(monitor)

    for t in threads:
        t.join()

def test_deadlock(monitor):
    lock_a = MonitoredLock("LockA")
    lock_b = MonitoredLock("LockB")

    def worker1():
        with lock_a:
            print("Worker1 acquired LockA")
            time.sleep(1)  # Ensure deadlock occurs
            print("Worker1 attempting LockB")
            if not lock_b.acquire(timeout=3):  # Add timeout
                print("Worker1 failed to acquire LockB")
                return
            try:
                print("Worker1 completed")
            finally:
                lock_b.release()

    def worker2():
        with lock_b:
            print("Worker2 acquired LockB")
            time.sleep(1)
            print("Worker2 attempting LockA")
            if not lock_a.acquire(timeout=3):  # Add timeout
                print("Worker2 failed to acquire LockA")
                return
            try:
                print("Worker2 completed")
            finally:
                lock_a.release()

    # Create and start threads
    t1 = threading.Thread(target=worker1, name="Worker1")
    t2 = threading.Thread(target=worker2, name="Worker2")
    t1.start()
    t2.start()

    # Monitor the deadlock
    for i in range(3):
        time.sleep(1)
        print_status(monitor)

    # Clean up
    t1.join(timeout=5)
    t2.join(timeout=5)

    for i in range(3):
        time.sleep(1)
        print_status(monitor)

    t1.join(timeout=2)
    t2.join(timeout=2)

def test_visualization(monitor):
    lock_x = MonitoredLock("LockX")
    lock_y = MonitoredLock("LockY")
    lock_z = MonitoredLock("LockZ")

    def complex_worker():
        with lock_x:
            time.sleep(0.2)
            with lock_y:
                time.sleep(0.2)
                with lock_z:
                    time.sleep(0.5)

    def blocking_worker():
        with lock_z:
            time.sleep(2)

    t1 = threading.Thread(target=blocking_worker)
    t1.start()
    time.sleep(0.1)

    t2 = threading.Thread(target=complex_worker)
    t2.start()

    for i in range(1, 4):
        time.sleep(1)
        print(f"\nVisualization Snapshot {i}:")
        print_status(monitor)

    t1.join()
    t2.join()

if __name__ == "__main__":
    scenario_runner(test_normal_operation, "Normal Operation")
    scenario_runner(test_deadlock, "Deadlock Detection")
    scenario_runner(test_visualization, "Visualization")
    print("\nAll tests completed")