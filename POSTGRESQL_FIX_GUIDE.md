# PostgreSQL Authentication Fix for Clinical Records Service

## Error
```
psycopg2.OperationalError: connection to server at "localhost" (127.0.0.1), port 5432 failed: 
FATAL: password authentication failed for user "postgres"
```

## Quick Fix Options

You have **3 options** to resolve this:

### **Option 1: Switch to SQLite (Recommended for Development/Testing)**

This is the fastest way to get the service running:

1. **Find your settings file:**
   ```bash
   cd ~/rxdoctor/ClinicalRecordsService
   nano clinical_records_api/settings.py
   # or
   nano clinical_records/settings.py
   ```

2. **Change the DATABASES configuration:**
   
   **Replace this:**
   ```python
   DATABASES = {
       'default': {
           'ENGINE': 'django.db.backends.postgresql',
           'NAME': 'clinical_records',
           'USER': 'postgres',
           'PASSWORD': 'your_password',
           'HOST': 'localhost',
           'PORT': '5432',
       }
   }
   ```

   **With this:**
   ```python
   DATABASES = {
       'default': {
           'ENGINE': 'django.db.backends.sqlite3',
           'NAME': BASE_DIR / 'db.sqlite3',
       }
   }
   ```

3. **Run migrations and start:**
   ```bash
   python manage.py migrate
   python manage.py runserver 0.0.0.0:8001
   ```

---

### **Option 2: Fix PostgreSQL Password**

If you want to use PostgreSQL:

#### Step 1: Check if PostgreSQL is installed and running
```bash
# Check if PostgreSQL is installed
psql --version

# Check if PostgreSQL is running
sudo systemctl status postgresql

# If not running, start it
sudo systemctl start postgresql
```

#### Step 2: Reset PostgreSQL password
```bash
# Switch to postgres user
sudo -i -u postgres

# Open PostgreSQL prompt
psql

# Change password
ALTER USER postgres WITH PASSWORD 'your_new_password';

# Exit
\q
exit
```

#### Step 3: Update your Django settings

**Option A: Using .env file (Recommended)**

Create or edit `.env` file:
```bash
cd ~/rxdoctor/ClinicalRecordsService
nano .env
```

Add these lines:
```env
DB_NAME=clinical_records
DB_USER=postgres
DB_PASSWORD=your_new_password
DB_HOST=localhost
DB_PORT=5432
```

Then in `settings.py`:
```python
import os
from dotenv import load_dotenv

load_dotenv()

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('DB_NAME', 'clinical_records'),
        'USER': os.getenv('DB_USER', 'postgres'),
        'PASSWORD': os.getenv('DB_PASSWORD', ''),
        'HOST': os.getenv('DB_HOST', 'localhost'),
        'PORT': os.getenv('DB_PORT', '5432'),
    }
}
```

**Option B: Direct in settings.py**
```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'clinical_records',
        'USER': 'postgres',
        'PASSWORD': 'your_new_password',  # Update this
        'HOST': 'localhost',
        'PORT': '5432',
    }
}
```

#### Step 4: Create the database
```bash
sudo -i -u postgres
createdb clinical_records
exit
```

#### Step 5: Test connection
```bash
# Test if you can connect
psql -U postgres -d clinical_records -h localhost

# If successful, exit
\q
```

#### Step 6: Run migrations
```bash
cd ~/rxdoctor/ClinicalRecordsService
source my_env/bin/activate
python manage.py migrate
python manage.py runserver 0.0.0.0:8001
```

---

### **Option 3: Create a New PostgreSQL User (Recommended for Production)**

Instead of using the default `postgres` user:

```bash
# Switch to postgres user
sudo -i -u postgres

# Create new database user
createuser --interactive --pwprompt clinical_user
# Enter password when prompted
# Answer 'n' to superuser, 'n' to create databases, 'n' to create roles

# Create database owned by new user
createdb -O clinical_user clinical_records

# Exit
exit
```

Update `settings.py`:
```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'clinical_records',
        'USER': 'clinical_user',
        'PASSWORD': 'password_you_set_above',
        'HOST': 'localhost',
        'PORT': '5432',
    }
}
```

---

## Troubleshooting

### Check PostgreSQL authentication method

```bash
sudo nano /etc/postgresql/*/main/pg_hba.conf
```

Look for this line:
```
# IPv4 local connections:
host    all             all             127.0.0.1/32            md5
```

If you see `peer` or `ident`, change it to `md5` and restart PostgreSQL:
```bash
sudo systemctl restart postgresql
```

### Check if PostgreSQL is listening

```bash
sudo netstat -tulpn | grep 5432
# or
sudo ss -tulpn | grep 5432
```

You should see:
```
tcp        0      0 127.0.0.1:5432          0.0.0.0:*               LISTEN
```

### Test PostgreSQL connection manually

```bash
psql -U postgres -h localhost -d postgres
```

If this asks for a password and accepts it, your PostgreSQL is configured correctly.

---

## Recommended Approach for Your Setup

Based on your error, here's what I recommend:

### **For Development/Testing:**
✅ **Use Option 1 (SQLite)** - Quickest to get running

### **For Production:**
✅ **Use Option 3 (New PostgreSQL User)** - More secure

---

## Quick Commands Summary

### Using SQLite (Fastest):
```bash
cd ~/rxdoctor/ClinicalRecordsService
# Edit settings.py to use SQLite (see Option 1 above)
python manage.py migrate
python manage.py runserver 0.0.0.0:8001
```

### Using PostgreSQL with correct password:
```bash
# Reset postgres password
sudo -i -u postgres
psql -c "ALTER USER postgres WITH PASSWORD 'newpassword';"
createdb clinical_records
exit

# Update settings.py with the new password
cd ~/rxdoctor/ClinicalRecordsService
nano clinical_records_api/settings.py  # or wherever your settings.py is

# Run migrations
python manage.py migrate
python manage.py runserver 0.0.0.0:8001
```

---

## After Fixing

Once you've fixed the database configuration:

```bash
# Run migrations
python manage.py migrate

# Create superuser (optional)
python manage.py createsuperuser

# Start the service
python manage.py runserver 0.0.0.0:8001

# Test in another terminal
curl http://localhost:8001/
```

---

## Environment Variables Method (Best Practice)

Create `.env` file:
```env
# Database Configuration
DB_ENGINE=django.db.backends.postgresql
# Or for SQLite: DB_ENGINE=django.db.backends.sqlite3

DB_NAME=clinical_records
DB_USER=postgres
DB_PASSWORD=your_secure_password
DB_HOST=localhost
DB_PORT=5432

# Django Settings
SECRET_KEY=your-secret-key
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1,your-server-ip
```

Install python-dotenv if not already:
```bash
pip install python-dotenv
```

Update `settings.py`:
```python
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

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

This way you can easily switch between SQLite and PostgreSQL by changing the `.env` file!

