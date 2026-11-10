import sys
import subprocess
import os

def check_and_install_dependencies():
    req_file = os.path.join(os.path.dirname(__file__), "requirements.txt")
    if not os.path.exists(req_file):
        print("requirements.txt not found. Skipping dependency check.")
        return

    print("Checking dependencies...")
    
    # Simplified dependency installation: install all packages from requirements.txt
    print("Installing dependencies from requirements.txt...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", req_file])
        print("Dependencies installed successfully.")
    except subprocess.CalledProcessError as e:
        print(f"Failed to install dependencies: {e}")
        sys.exit(1)

if __name__ == "__main__":
    check_and_install_dependencies()
    
    # Once dependencies are confirmed, launch the main application
    print("Launching 3D Alignment Tool...")
    
    # Add src to Python path so it can import local modules
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "src")))
    
    try:
        from src.main_gui import main
        main()
    except Exception as e:
        print(f"Error launching application: {e}")
        import traceback
        traceback.print_exc()
        input("Press Enter to exit...")
