# App Backend

FastAPI-based backend for PGM (Platinum/Palladium/Rhodium) calculator & converter.

Quick start:
1. Copy `.env.example` to `.env` and fill values (SECRET_KEY, DATABASE_URL, Cloudinary creds, Firebase creds path etc).
2. Create & activate a Python virtualenv:
   ```bash
   python -m venv .venv
   source .venv/bin/activate   # mac/linux
   .venv\Scripts\activate      # windows
   ```
3. Install deps:
   ```bash
   pip install -r requirements.txt
   ```
4. Run app:
   ```bash
   uvicorn app.main:app --reload --port 8000
   ```
Notes:
- Provide `firebase_credentials.json` file at project root for FCM (or disable scheduler/init).
- Set secure `SECRET_KEY` in `.env`.
- If using PostgreSQL on Render/Neon, ensure `DATABASE_URL` uses `postgresql://`.
