# Clinical Records Service - Database Connection Fix

## The Error You're Seeing

```
psycopg2.OperationalError: connection to server at "localhost" (127.0.0.1), port 5432 failed: 
FATAL: password authentication failed for user "postgres"
```

## Current Database Configuration

Your `settings.py` is configured for PostgreSQL:
- **Database Name:** `clinicalRecords`
- **User:** `postgres`
- **Password:** `admin`
- **Host:** `localhost`
- **Port:** `5432`

## Problem

PostgreSQL on your Ubuntu server either:
1. Doesn't have the user `postgres` with password `admin`
2. Isn't installed
3. Isn't running
4. Has different authentication settings

## Solutions

### 🚀 **Quick Fix: Switch to SQLite (Recommended)**

This is the **fastest way** to get your service running:

#### **On Your Ubuntu Server:**

```bash
cd ~/rxdoctor/ClinicalRecordsService
source my_env/bin/activate

# Option A: Use the Python script
python3 switch_to_sqlite.py

# Option B: Use the bash script (interactive)
chmod +x fix_database.sh
./fix_database.sh
# Choose option 1

# Run migrations
python manage.py migrate

# Start the service
python manage.py runserver 0.0.0.0:8001
```

#### **Manual Method:**

Edit `clinical_records_api/settings.py`:

```python
# Find this section (around line 67):
# Database - PostgreSQL Configuration
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'clinicalRecords',
        'USER': 'postgres',
        'PASSWORD': 'admin',
        'HOST': 'localhost',
        'PORT': '5432',
    }
}

# Replace with:
# Database - SQLite Configuration
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}
```

Then run:
```bash
python manage.py migrate
python manage.py runserver 0.0.0.0:8001
```

---

### 🐘 **Fix PostgreSQL (For Production)**

If you want to use PostgreSQL:

#### **Step 1: Install PostgreSQL (if not installed)**
```bash
sudo apt update
sudo apt install postgresql postgresql-contrib
sudo systemctl start postgresql
sudo systemctl enable postgresql
```

#### **Step 2: Set PostgreSQL Password**
```bash
# Switch to postgres user
sudo -i -u postgres

# Open PostgreSQL prompt
psql

# Set the password to match your settings.py (admin)
ALTER USER postgres WITH PASSWORD 'admin';

# Create the database
CREATE DATABASE "clinicalRecords";

# Exit PostgreSQL
\q

# Exit postgres user
exit
```

#### **Step 3: Test Connection**
```bash
# Test if you can connect with the password
psql -U postgres -h localhost -d clinicalRecords
# Enter password: admin

# If successful, you'll see the PostgreSQL prompt
\q
```

#### **Step 4: Run Migrations**
```bash
cd ~/rxdoctor/ClinicalRecordsService
source my_env/bin/activate
python manage.py migrate
python manage.py runserver 0.0.0.0:8001
```

---

### 🔒 **Secure PostgreSQL Setup (Recommended for Production)**

Instead of using the default `postgres` user:

```bash
# Create dedicated user
sudo -i -u postgres
createuser --interactive --pwprompt clinical_admin
# Enter a secure password
# Answer 'n' to all privilege questions

# Create database
createdb -O clinical_admin clinical_records

# Grant privileges
psql
GRANT ALL PRIVILEGES ON DATABASE clinical_records TO clinical_admin;
\q
exit
```

Then update `settings.py`:
```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'clinical_records',
        'USER': 'clinical_admin',
        'PASSWORD': 'your_secure_password',
        'HOST': 'localhost',
        'PORT': '5432',
    }
}
```

---

## Troubleshooting

### PostgreSQL Not Installed
```bash
# Install PostgreSQL
sudo apt update
sudo apt install postgresql postgresql-contrib libpq-dev
```

### PostgreSQL Not Running
```bash
# Check status
sudo systemctl status postgresql

# Start if not running
sudo systemctl start postgresql

# Enable auto-start on boot
sudo systemctl enable postgresql
```

### Connection Still Failing
```bash
# Check PostgreSQL authentication config
sudo nano /etc/postgresql/*/main/pg_hba.conf

# Look for this line and make sure it says 'md5' or 'scram-sha-256':
# local   all             postgres                                peer
# Change 'peer' to 'md5':
# local   all             postgres                                md5

# Also check IPv4 connections:
# host    all             all             127.0.0.1/32            md5

# Restart PostgreSQL after changes
sudo systemctl restart postgresql
```

### Test PostgreSQL Installation
```bash
# Check if PostgreSQL is listening
sudo ss -tulpn | grep 5432

# Should show:
# tcp   LISTEN  0  128  127.0.0.1:5432  0.0.0.0:*
```

---

## Files Provided to Help You

1. **`POSTGRESQL_FIX_GUIDE.md`** - Detailed guide with all options
2. **`switch_to_sqlite.py`** - Python script to automatically switch to SQLite
3. **`fix_database.sh`** - Interactive bash script with multiple options
4. **`DATABASE_FIX_SUMMARY.md`** - This file

---

## Recommended Approach

### For Testing/Development:
✅ **Use SQLite** - Run `python3 switch_to_sqlite.py`

### For Production:
✅ **Use PostgreSQL with dedicated user** - More secure
✅ **Use environment variables** - Keep credentials out of code

---

## Using Environment Variables (Best Practice)

Create `.env` file in ClinicalRecordsService directory:

```env
# Database Configuration
DB_ENGINE=django.db.backends.postgresql
DB_NAME=clinical_records
DB_USER=clinical_admin
DB_PASSWORD=your_secure_password
DB_HOST=localhost
DB_PORT=5432

# Django
SECRET_KEY=your-secret-key-here
DEBUG=False
ALLOWED_HOSTS=localhost,127.0.0.1,your-server-ip
```

Install python-dotenv:
```bash
pip install python-dotenv
```

Update `settings.py`:
```python
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-fallback-key')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.getenv('DEBUG', 'False') == 'True'

ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', 'localhost').split(',')

# Database
DATABASES = {
    'default': {
        'ENGINE': os.getenv('DB_ENGINE', 'django.db.backends.sqlite3'),
        'NAME': os.getenv('DB_NAME', BASE_DIR / 'db.sqlite3'),
        'USER': os.getenv('DB_USER', ''),
        'PASSWORD': os.getenv('DB_PASSWORD', ''),
        'HOST': os.getenv('DB_HOST', ''),
        'PORT': os.getenv('DB_PORT', ''),
    }
}
```

Now you can switch between SQLite and PostgreSQL by just changing `.env`!

---

## Quick Start Commands

### Switch to SQLite and Run:
```bash
cd ~/rxdoctor/ClinicalRecordsService
source my_env/bin/activate
python3 switch_to_sqlite.py
python manage.py migrate
python manage.py createsuperuser  # Optional
python manage.py runserver 0.0.0.0:8001
```

### Fix PostgreSQL and Run:
```bash
# Fix PostgreSQL password
sudo -i -u postgres
psql -c "ALTER USER postgres WITH PASSWORD 'admin';"
psql -c "CREATE DATABASE \"clinicalRecords\";"
exit

# Run migrations
cd ~/rxdoctor/ClinicalRecordsService
source my_env/bin/activate
python manage.py migrate
python manage.py runserver 0.0.0.0:8001
```

---

## After the Fix

Once your service is running, test it:

```bash
# In another terminal, test the service
curl http://localhost:8001/

# Check if it's accessible from your main backend
curl http://localhost:8001/api/health/
```

Your main RxBackend application should now be able to connect to the Clinical Records Service!

---

**Choose the solution that works best for your needs and follow the steps above.** The SQLite option is quickest for getting started, while PostgreSQL is better for production use.

