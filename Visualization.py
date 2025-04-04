from flask import Flask, render_template, request, jsonify
import threading
import time
from collections import defaultdict

app = Flask(__name__)

thread_data = {
    'graph': {'nodes': [], 'links': []},
    'timeline': [],
    'deadlocks': []
}

class DeadlockSimulator:
    def __init__(self):
        self.lock = threading.Lock()
        
    def simulate_deadlock(self, thread_count, resource_count):
        resources = [threading.Lock() for _ in range(resource_count)]
        
        with self.lock:
            thread_data['graph']['nodes'] = [
                *[{'id': f'T{i+1}', 'type': 'thread'} for i in range(thread_count)],
                *[{'id': f'R{i+1}', 'type': 'resource'} for i in range(resource_count)]
            ]
            thread_data['links'] = []
            thread_data['timeline'] = []
            thread_data['deadlocks'] = []

        def worker(thread_id):
            # Each thread tries to acquire two different resources
            first_res = thread_id % resource_count
            second_res = (thread_id + 1) % resource_count  # Circular pattern
            
            # First acquisition
            with self.lock:
                thread_data['links'].append({
                    'source': f'T{thread_id}',
                    'target': f'R{first_res+1}',
                    'type': 'acquire',
                    'deadlock': False
                })
                thread_data['timeline'].append({
                    'event': f'T{thread_id} acquired R{first_res+1}',
                    'time': time.time()
                })
            
            resources[first_res].acquire()
            time.sleep(0.5)
            
           