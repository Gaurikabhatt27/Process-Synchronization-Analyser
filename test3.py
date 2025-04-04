import threading

lock1 = threading.Lock()
lock2 = threading.Lock()

def thread1():
    lock1.acquire()
    lock2.acquire()
    lock2.release()
    lock1.release()

def thread2():
    lock2.acquire()
    lock1.acquire()
    lock1.release()
    lock2.release()