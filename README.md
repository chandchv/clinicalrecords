# Clinical Records Service

A separate Django service for handling clinical records functionality, accessible via REST API.

## Setup

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Run migrations:**
   ```bash
   python manage.py migrate
   ```

3. **Start the service:**
   ```bash
   python start_service.py
   ```
   
   Or using Django manage.py:
   ```bash
   python manage.py runserver 0.0.0.0:8001
   ```

## API Endpoints

The service runs on port 8001 and provides the following endpoints:

- **Widget API:** `GET /api/widget/` - Returns clinical records widget data
- **Records API:** `GET /api/records/` - List clinical records
- **Documents API:** `GET /api/documents/` - List clinical documents
- **Admin Interface:** `http://localhost:8001/admin/` - Django admin

## Configuration

- **Database:** SQLite (default) - can be changed to PostgreSQL in settings
- **CORS:** Configured to allow requests from RxBackend (localhost:8000)
- **Authentication:** Session and Token authentication supported

## Integration with RxBackend

The main RxBackend application communicates with this service via the `clinical_records_api_client.py` module.

## Development

- **Port:** 8001 (different from main RxBackend on 8000)
- **Debug:** Enabled by default
- **Logging:** Console logging configured
