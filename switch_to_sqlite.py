#!/usr/bin/env python3
"""
Quick script to switch Clinical Records Service from PostgreSQL to SQLite
Run this on your Ubuntu server to quickly fix the database connection issue.

Usage:
    python3 switch_to_sqlite.py
"""

import os
import shutil
from pathlib import Path

def main():
    print("=" * 60)
    print("Clinical Records Service - Switch to SQLite")
    print("=" * 60)
    print()
    
    # Find settings file
    settings_file = Path("clinical_records_api/settings.py")
    
    if not settings_file.exists():
        print("❌ Error: Could not find settings.py")
        print("   Make sure you're running this from the ClinicalRecordsService directory")
        return
    
    # Backup current settings
    backup_file = Path("clinical_records_api/settings.py.backup")
    shutil.copy(settings_file, backup_file)
    print(f"✓ Backed up settings.py to {backup_file}")
    
    # Read current settings
    with open(settings_file, 'r') as f:
        content = f.read()
    
    # Check if already using SQLite
    if 'sqlite3' in content and 'postgresql' not in content:
        print("✓ Already using SQLite database")
        return
    
    # Replace PostgreSQL configuration with SQLite
    new_db_config = """# Database - SQLite Configuration (Development)
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}"""
    
    # Find and replace DATABASES configuration
    import re
    
    # Pattern to match the DATABASES block
    pattern = r'# Database.*?DATABASES\s*=\s*\{[^}]*\{[^}]*\}[^}]*\}'
    
    if re.search(pattern, content, re.DOTALL):
        content = re.sub(pattern, new_db_config, content, flags=re.DOTALL)
        
        # Write back
        with open(settings_file, 'w') as f:
            f.write(content)
        
        print("✓ Updated settings.py to use SQLite")
        print()
        print("=" * 60)
        print("Next steps:")
        print("=" * 60)
        print("1. Run migrations:")
        print("   python manage.py migrate")
        print()
        print("2. Create superuser (optional):")
        print("   python manage.py createsuperuser")
        print()
        print("3. Start the server:")
        print("   python manage.py runserver 0.0.0.0:8001")
        print()
        print("To revert to PostgreSQL, restore the backup:")
        print(f"   cp {backup_file} {settings_file}")
        print("=" * 60)
    else:
        print("❌ Could not find DATABASES configuration in settings.py")
        print("   Please update manually")

if __name__ == "__main__":
    main()

