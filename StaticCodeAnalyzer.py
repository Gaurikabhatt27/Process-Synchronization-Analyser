import ast
import os
import sys
from collections import defaultdict

class SyncIssueDetector(ast.NodeVisitor):
    def __init__(self):
        self.shared_resources = defaultdict(list)  # {variable_name: [access_locations]}
        self.locks = set()
        self.lock_acquires = defaultdict(list)  # {lock_name: [locations]}
        self.lock_releases = defaultdict(list)  # {lock_name: [locations]}
        self.deadlock_pairs = set()
        self.locked_vars = set()
        self.current_locks = set()
    
    def visit_Assign(self, node):
        if isinstance(node.targets[0], ast.Name):
            var_name = node.targets[0].id
            if not self.current_locks:  # If no lock is held
                self.shared_resources[var_name].append((node.lineno, node.col_offset))
        self.generic_visit(node)

    def visit_Call(self, node):
        if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
            func_name = node.func.attr
            obj_name = node.func.value.id
            
            if func_name == 'acquire':
                self.locks.add(obj_name)
                self.lock_acquires[obj_name].append((node.lineno, node.col_offset))
                self.current_locks.add(obj_name)
                self.detect_deadlock(obj_name)
            elif func_name == 'release':
                self.lock_releases[obj_name].append((node.lineno, node.col_offset))
                self.current_locks.discard(obj_name)
        self.generic_visit(node)
    
    def detect_deadlock(self, lock_name):
        for acquired_lock in self.locks:
            if acquired_lock != lock_name:
                self.deadlock_pairs.add((acquired_lock, lock_name))
    
    def report_issues(self):
        print("Potential Synchronization Issues Detected:")
        
        for var, accesses in self.shared_resources.items():
            if len(accesses) >= 1:
                print(f"- Shared resource '{var}' accessed at {accesses} without synchronization.")
        
        for lock, locations in self.lock_acquires.items():
            if lock not in self.lock_releases:
                print(f"- Lock '{lock}' acquired but never released at {locations}.")
        
        if self.deadlock_pairs:
            print("- Potential Deadlocks Detected: Circular wait conditions found:")
            for pair in self.deadlock_pairs:
                print(f"  - {pair}")


def analyze_code(file_path):
    with open(file_path, "r") as source_file:
        tree = ast.parse(source_file.read())
    detector = SyncIssueDetector()
    detector.visit(tree)
    detector.report_issues()

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python static_code_analyzer.py <source_code.py>")
        sys.exit(1)
    analyze_code(sys.argv[1])
