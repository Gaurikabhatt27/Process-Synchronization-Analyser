shared_var = 0

def thread_func():
    global shared_var
    shared_var += 1  # No lock used

thread_func()