#!/usr/bin/env python3
"""
Setup script for Playwright Tableau Dashboard Agent
"""

import subprocess
import sys
import os

def install_playwright():
    """Install Playwright and its browsers"""
    print("🚀 Installing Playwright...")
    
    try:
        # Install playwright
        subprocess.check_call([sys.executable, "-m", "pip", "install", "playwright"])
        print("✅ Playwright installed successfully")
        
        # Install browsers
        print("🌐 Installing browser binaries...")
        subprocess.check_call([sys.executable, "-m", "playwright", "install", "chromium"])
        print("✅ Browser binaries installed successfully")
        
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Error installing Playwright: {e}")
        return False

def main():
    print("🎯 Setting up Playwright Tableau Dashboard Agent")
    print("=" * 50)
    
    if install_playwright():
        print("\n🎉 Setup completed successfully!")
        print("\n📋 Next steps:")
        print("1. Update your Tableau dashboard URL in config_AGENT.py")
        print("2. Run: python TableauDashboardAgent_Playwright.py")
        print("3. Ask questions about your Tableau dashboard!")
    else:
        print("\n❌ Setup failed. Please check the error messages above.")
        sys.exit(1)

if __name__ == "__main__":
    main()




