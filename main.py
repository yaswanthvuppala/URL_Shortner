import os
import string
import random
import redis
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.responses import RedirectResponse, FileResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel, HttpUrl

from database import engine, Base, get_db
import models

# Create database tables
Base.metadata.create_all(bind=engine)

app = FastAPI(title="URL Shortener API")

@app.get("/")
def read_root():
    return FileResponse("static/index.html")

# Initialize Redis connection
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
redis_client = redis.from_url(REDIS_URL, decode_responses=True)

class URLCreate(BaseModel):
    long_url: HttpUrl

def generate_short_code(length: int = 6) -> str:
    """Generate a random base62 string."""
    characters = string.ascii_letters + string.digits
    return ''.join(random.choice(characters) for _ in range(length))

@app.post("/shorten", status_code=status.HTTP_201_CREATED)
def shorten_url(url_data: URLCreate, db: Session = Depends(get_db)):
    # Generate unique short code
    # Real-world app would need a collision check/retry loop
    for _ in range(10): # try 10 times to avoid collision
        short_code = generate_short_code()
        existing = db.query(models.URLMapping).filter(models.URLMapping.short_code == short_code).first()
        if not existing:
            break
    else:
        raise HTTPException(status_code=500, detail="Could not generate unique short code")

    # Save to SQLite
    db_mapping = models.URLMapping(
        short_code=short_code,
        long_url=str(url_data.long_url)
    )
    db.add(db_mapping)
    db.commit()
    db.refresh(db_mapping)

    # Cache in Redis with 24-hour TTL (86400 seconds)
    redis_client.setex(short_code, 86400, db_mapping.long_url)

    BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
    return {"short_url": f"{BASE_URL}/{short_code}"}

@app.get("/{short_code}")
def redirect_to_long_url(short_code: str, db: Session = Depends(get_db)):
    # 1. Try Redis first (Cache Hit)
    cached_url = redis_client.get(short_code)
    
    if cached_url:
        # Increment click count asynchronously or in DB (for simplicity doing it directly in DB)
        # Note: In high traffic, incrementing stats should be decoupled
        mapping = db.query(models.URLMapping).filter(models.URLMapping.short_code == short_code).first()
        if mapping:
            mapping.clicks += 1
            db.commit()
        return RedirectResponse(url=cached_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
    
    # 2. Cache Miss: check SQLite
    mapping = db.query(models.URLMapping).filter(models.URLMapping.short_code == short_code).first()
    if not mapping:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Short URL not found")
    
    # Found in DB -> populate cache
    redis_client.setex(short_code, 86400, mapping.long_url)
    
    # Increment click count
    mapping.clicks += 1
    db.commit()

    return RedirectResponse(url=mapping.long_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)

@app.get("/analytics/{short_code}")
def get_analytics(short_code: str, db: Session = Depends(get_db)):
    mapping = db.query(models.URLMapping).filter(models.URLMapping.short_code == short_code).first()
    if not mapping:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Short URL not found")
    
    return {
        "short_code": mapping.short_code,
        "long_url": mapping.long_url,
        "clicks": mapping.clicks,
        "created_at": mapping.created_at
    }
