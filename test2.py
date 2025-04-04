import threading

lock = threading.Lock()

def thread_func():
    lock.acquire()  # No release

thread_func()