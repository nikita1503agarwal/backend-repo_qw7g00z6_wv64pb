import os
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

from database import create_document, db

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class CountryRatingIn(BaseModel):
    country_slug: str = Field(..., description="kebab-case country slug, e.g., united-states")
    rating: float = Field(..., ge=0, le=5)
    user_id: Optional[str] = Field(None, description="Optional user identifier")
    comment: Optional[str] = Field(None, description="Optional comment")

    @field_validator("country_slug")
    @classmethod
    def validate_slug(cls, v: str):
        sv = v.strip().lower()
        if not sv or any(ch for ch in sv if not (ch.isalnum() or ch in ["-"] )):
            raise ValueError("country_slug must be kebab-case, alphanumeric with hyphens")
        return sv


class RatingCreateResponse(BaseModel):
    id: str
    ok: bool = True


class CountryRatingStats(BaseModel):
    country_slug: str
    count: int
    avg: float


@app.get("/")
def read_root():
    return {"message": "Hello from FastAPI Backend!"}


@app.get("/api/hello")
def hello():
    return {"message": "Hello from the backend API!"}


@app.get("/test")
def test_database():
    """Test endpoint to check if database is available and accessible"""
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }

    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Configured"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"

            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]  # Show first 10 collections
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"

    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    # Check environment variables
    response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"

    return response


# Ratings API
@app.post("/api/ratings", response_model=RatingCreateResponse)
def create_rating(payload: CountryRatingIn):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")
    try:
        doc_id = create_document("countryrating", payload)
        return {"id": doc_id, "ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/ratings/summary", response_model=List[CountryRatingStats])
def ratings_summary(limit: Optional[int] = None):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")

    pipeline = [
        {"$group": {"_id": "$country_slug", "count": {"$sum": 1}, "avg": {"$avg": "$rating"}}},
        {"$project": {"_id": 0, "country_slug": "$_id", "count": 1, "avg": {"$round": ["$avg", 3]}}},
        {"$sort": {"avg": -1}},
    ]
    if limit and isinstance(limit, int) and limit > 0:
        pipeline.append({"$limit": int(limit)})

    try:
        results = list(db["countryrating"].aggregate(pipeline))
        return [CountryRatingStats(**r) for r in results]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/ratings/{country_slug}", response_model=CountryRatingStats)
def country_rating_stats(country_slug: str):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")

    try:
        agg = list(db["countryrating"].aggregate([
            {"$match": {"country_slug": country_slug}},
            {"$group": {"_id": "$country_slug", "count": {"$sum": 1}, "avg": {"$avg": "$rating"}}},
            {"$project": {"_id": 0, "country_slug": "$_id", "count": 1, "avg": {"$round": ["$avg", 3]}}},
        ]))
        if not agg:
            return CountryRatingStats(country_slug=country_slug, count=0, avg=0.0)
        return CountryRatingStats(**agg[0])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
