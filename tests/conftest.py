"""
Pytest configuration and shared fixtures for the Finance DCF Agent test suite.
"""
import sys
import os
import pytest

# Ensure project root is on the path for all tests
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
