"""
Verify bypy authorization
Run this script in your terminal after completing bypy authorization
"""

import sys
import subprocess

def main():
    print("Verifying bypy authorization...")
    print("=" * 50)

    try:
        result = subprocess.run(
            [sys.executable, "-m", "bypy", "list"],
            capture_output=True,
            text=True,
            timeout=30
        )

        if "EOFError" in result.stderr or "Traceback" in result.stderr:
            print("❌ Authorization NOT completed!")
            print("\nPlease run the following command in your terminal:")
            print("  python -m bypy info")
            print("\nThen:")
            print("  1. Visit the authorization URL in browser")
            print("  2. Login to your Baidu account")
            print("  3. Paste the authorization code")
            return False

        print("✅ Authorization successful!")
        print("\nFile list from /apps/bypy/:")
        print(result.stdout)
        return True

    except Exception as e:
        print(f"Error: {e}")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
