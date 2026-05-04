"""
Pytest configuration: adds backend/ to sys.path so all backend modules are importable.
"""
import sys
import os

# backend/ is the parent of this tests/ directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
