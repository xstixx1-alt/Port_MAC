import sys, os, traceback

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)
sys.path.insert(0, BASE_DIR)

try:
    import main
except Exception as e:
    print(f"ERROR: {e}")
    traceback.print_exc()
