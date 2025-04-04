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
            
            # Deadlock attempt
            with self.lock:
                thread_data['links'].append({
                    'source': f'T{thread_id}',
                    'target': f'R{second_res+1}',
                    'type': 'waiting',
                    'deadlock': True
                })
                thread_data['timeline'].append({
                    'event': f'T{thread_id} waiting for R{second_res+1} (DEADLOCK)',
                    'time': time.time()
                })
                
                if not thread_data['deadlocks']:
                    thread_data['deadlocks'].append({
                        'description': f'Circular wait between {min(thread_count, resource_count)} threads/resources',
                        'solution': 'Implement consistent lock ordering',
                        'code': '''# Safe locking pattern:
resources = sorted([resource_a, resource_b], key=id)
for res in resources:
    res.acquire()'''
                    })
            
            resources[second_res].acquire()  # This will block
            resources[second_res].release()
            resources[first_res].release()

        # Start threads
        for i in range(thread_count):
            threading.Thread(target=worker, args=(i+1,)).start()

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        thread_count = int(request.form['thread_count'])
        resource_count = int(request.form['resource_count'])
        DeadlockSimulator().simulate_deadlock(thread_count, resource_count)
    return render_template('dashboard.html')

@app.route('/data')
def get_data():
    return jsonify(thread_data)

if __name__ == '__main__':
    app.run(port=5000, debug=True)
    