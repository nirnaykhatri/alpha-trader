"""
Test runner script for the trading bot.
This script provides convenient commands for running different types of tests.
"""

import subprocess
import sys
import os
from pathlib import Path
import argparse


def run_command(command, description):
    """Run a command and handle output."""
    print(f"\n{'='*60}")
    print(f"🔍 {description}")
    print(f"{'='*60}")
    print(f"Running: {' '.join(command)}")
    print(f"{'='*60}")
    
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Command failed with exit code {e.returncode}")
        print("STDOUT:", e.stdout)
        print("STDERR:", e.stderr)
        return False


def run_unit_tests():
    """Run unit tests only."""
    command = ["python", "-m", "pytest", "tests/unit/", "-v", "--tb=short"]
    return run_command(command, "Running Unit Tests")


def run_integration_tests():
    """Run integration tests only."""
    command = ["python", "-m", "pytest", "tests/integration/", "-v", "--tb=short"]
    return run_command(command, "Running Integration Tests")


def run_all_tests():
    """Run all tests."""
    command = ["python", "-m", "pytest", "tests/", "-v", "--tb=short"]
    return run_command(command, "Running All Tests")


def run_tests_with_coverage():
    """Run tests with coverage report."""
    command = [
        "python", "-m", "pytest", 
        "tests/", 
        "--cov=src", 
        "--cov-report=term-missing", 
        "--cov-report=html:htmlcov",
        "-v"
    ]
    return run_command(command, "Running Tests with Coverage")


def run_specific_test(test_path):
    """Run a specific test file or test function."""
    command = ["python", "-m", "pytest", test_path, "-v", "--tb=short"]
    return run_command(command, f"Running Specific Test: {test_path}")


def run_linting():
    """Run code linting."""
    commands = [
        (["python", "-m", "flake8", "src/", "tests/"], "Running Flake8 Linting"),
        (["python", "-m", "black", "--check", "src/", "tests/"], "Running Black Format Check"),
        (["python", "-m", "mypy", "src/"], "Running MyPy Type Checking")
    ]
    
    all_passed = True
    for command, description in commands:
        if not run_command(command, description):
            all_passed = False
    
    return all_passed


def run_formatting():
    """Run code formatting."""
    command = ["python", "-m", "black", "src/", "tests/"]
    return run_command(command, "Running Black Code Formatting")


def setup_test_environment():
    """Set up test environment."""
    print("\n🔧 Setting up test environment...")
    
    # Install test dependencies
    command = ["python", "-m", "pip", "install", "-r", "requirements.txt"]
    if not run_command(command, "Installing Requirements"):
        return False
    
    # Install development dependencies
    dev_packages = [
        "pytest", "pytest-asyncio", "pytest-cov", "pytest-mock",
        "black", "flake8", "mypy", "pre-commit"
    ]
    
    for package in dev_packages:
        command = ["python", "-m", "pip", "install", package]
        if not run_command(command, f"Installing {package}"):
            print(f"⚠️  Warning: Failed to install {package}")
    
    print("\n✅ Test environment setup complete!")
    return True


def clean_test_artifacts():
    """Clean up test artifacts."""
    print("\n🧹 Cleaning up test artifacts...")
    
    artifacts = [
        "htmlcov/",
        "coverage.xml",
        ".coverage",
        "test_trading_bot.db",
        "test_trading_bot.log",
        "__pycache__/",
        ".pytest_cache/",
        "*.pyc"
    ]
    
    for artifact in artifacts:
        if os.path.exists(artifact):
            if os.path.isdir(artifact):
                import shutil
                shutil.rmtree(artifact)
                print(f"🗑️  Removed directory: {artifact}")
            else:
                os.remove(artifact)
                print(f"🗑️  Removed file: {artifact}")
    
    print("✅ Cleanup complete!")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Trading Bot Test Runner")
    parser.add_argument(
        "command",
        choices=[
            "unit", "integration", "all", "coverage", 
            "lint", "format", "setup", "clean", "specific"
        ],
        help="Test command to run"
    )
    parser.add_argument(
        "--test-path",
        help="Specific test path for 'specific' command"
    )
    
    args = parser.parse_args()
    
    # Change to project root directory
    project_root = Path(__file__).parent
    os.chdir(project_root)
    
    print(f"🤖 Trading Bot Test Runner")
    print(f"📍 Working directory: {os.getcwd()}")
    
    success = True
    
    if args.command == "unit":
        success = run_unit_tests()
    elif args.command == "integration":
        success = run_integration_tests()
    elif args.command == "all":
        success = run_all_tests()
    elif args.command == "coverage":
        success = run_tests_with_coverage()
    elif args.command == "lint":
        success = run_linting()
    elif args.command == "format":
        success = run_formatting()
    elif args.command == "setup":
        success = setup_test_environment()
    elif args.command == "clean":
        clean_test_artifacts()
    elif args.command == "specific":
        if not args.test_path:
            print("❌ Error: --test-path required for 'specific' command")
            sys.exit(1)
        success = run_specific_test(args.test_path)
    
    if success:
        print(f"\n✅ Command '{args.command}' completed successfully!")
        sys.exit(0)
    else:
        print(f"\n❌ Command '{args.command}' failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()
