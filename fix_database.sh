#!/bin/bash

# Clinical Records Service - Database Fix Script
# This script helps you choose between SQLite and PostgreSQL

echo "=========================================="
echo "Clinical Records Service - Database Fix"
echo "=========================================="
echo ""
echo "Current database configuration:"
echo "  Database: clinicalRecords"
echo "  User: postgres"
echo "  Password: admin"
echo ""
echo "Choose an option:"
echo "  1) Switch to SQLite (Quick & Easy - Recommended for testing)"
echo "  2) Fix PostgreSQL password"
echo "  3) Create new PostgreSQL database and user"
echo "  4) Exit"
echo ""
read -p "Enter your choice (1-4): " choice

case $choice in
    1)
        echo ""
        echo "Switching to SQLite..."
        
        # Backup current settings
        cp clinical_records_api/settings.py clinical_records_api/settings.py.backup
        
        # Update database configuration to SQLite
        cat > /tmp/db_config.txt << 'EOF'
# Database - SQLite Configuration (Development)
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}
EOF
        
        # Replace DATABASES configuration
        python3 << 'PYTHON_SCRIPT'
import re

# Read the settings file
with open('clinical_records_api/settings.py', 'r') as f:
    content = f.read()

# Replace DATABASES configuration
new_db_config = """# Database - SQLite Configuration (Development)
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}"""

# Use regex to replace DATABASES block
content = re.sub(
    r'# Database - PostgreSQL Configuration\nDATABASES = \{[^}]+\}',
    new_db_config,
    content,
    flags=re.DOTALL
)

# Write back
with open('clinical_records_api/settings.py', 'w') as f:
    f.write(content)

print("✓ Updated settings.py to use SQLite")
PYTHON_SCRIPT
        
        echo "✓ Backed up original settings to settings.py.backup"
        echo "✓ Switched to SQLite database"
        echo ""
        echo "Now run migrations:"
        echo "  source my_env/bin/activate"
        echo "  python manage.py migrate"
        echo "  python manage.py runserver 0.0.0.0:8001"
        ;;
        
    2)
        echo ""
        echo "Fixing PostgreSQL password..."
        echo ""
        
        # Check if PostgreSQL is installed
        if ! command -v psql &> /dev/null; then
            echo "❌ PostgreSQL is not installed!"
            echo "Install it with: sudo apt-get install postgresql postgresql-contrib"
            exit 1
        fi
        
        # Check if PostgreSQL is running
        if ! sudo systemctl is-active --quiet postgresql; then
            echo "Starting PostgreSQL..."
            sudo systemctl start postgresql
        fi
        
        echo "Setting postgres user password to 'admin'..."
        sudo -u postgres psql -c "ALTER USER postgres WITH PASSWORD 'admin';"
        
        echo "Creating database 'clinicalRecords'..."
        sudo -u postgres psql -c "DROP DATABASE IF EXISTS \"clinicalRecords\";"
        sudo -u postgres psql -c "CREATE DATABASE \"clinicalRecords\";"
        
        echo ""
        echo "✓ PostgreSQL password set to 'admin'"
        echo "✓ Database 'clinicalRecords' created"
        echo ""
        echo "Now run migrations:"
        echo "  source my_env/bin/activate"
        echo "  python manage.py migrate"
        echo "  python manage.py runserver 0.0.0.0:8001"
        ;;
        
    3)
        echo ""
        echo "Creating new PostgreSQL user and database..."
        
        read -p "Enter new database user name [clinical_user]: " db_user
        db_user=${db_user:-clinical_user}
        
        read -sp "Enter password for $db_user: " db_password
        echo ""
        
        read -p "Enter database name [clinical_records_db]: " db_name
        db_name=${db_name:-clinical_records_db}
        
        # Create user and database
        sudo -u postgres psql << EOF
CREATE USER $db_user WITH PASSWORD '$db_password';
CREATE DATABASE $db_name OWNER $db_user;
GRANT ALL PRIVILEGES ON DATABASE $db_name TO $db_user;
EOF
        
        # Update settings.py
        cat > .env << EOF
DB_NAME=$db_name
DB_USER=$db_user
DB_PASSWORD=$db_password
DB_HOST=localhost
DB_PORT=5432
EOF
        
        echo ""
        echo "✓ Created user: $db_user"
        echo "✓ Created database: $db_name"
        echo "✓ Created .env file with credentials"
        echo ""
        echo "Update your settings.py to use environment variables:"
        echo ""
        echo "  pip install python-dotenv"
        echo ""
        echo "Then add to settings.py:"
        echo "  from dotenv import load_dotenv"
        echo "  load_dotenv()"
        echo ""
        echo "  DATABASES = {"
        echo "      'default': {"
        echo "          'ENGINE': 'django.db.backends.postgresql',"
        echo "          'NAME': os.getenv('DB_NAME'),"
        echo "          'USER': os.getenv('DB_USER'),"
        echo "          'PASSWORD': os.getenv('DB_PASSWORD'),"
        echo "          'HOST': os.getenv('DB_HOST'),"
        echo "          'PORT': os.getenv('DB_PORT'),"
        echo "      }"
        echo "  }"
        ;;
        
    4)
        echo "Exiting..."
        exit 0
        ;;
        
    *)
        echo "Invalid choice. Exiting..."
        exit 1
        ;;
esac

echo ""
echo "=========================================="
echo "Fix complete!"
echo "=========================================="

