from app.main import SessionLocal, Base, engine, seed_demo
# Use the API seed endpoint after starting the server: POST /api/dev/seed
print("Start the API, then POST http://localhost:8000/api/dev/seed to load demo users and sample items.")
