import argparse

from app.db import Base, SessionLocal, engine
from app.seed.seed import seed_all, seed_documents, seed_timetables


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the database with mock data")
    parser.add_argument("--reset", action="store_true", help="drop all tables first")
    parser.add_argument(
        "--timetables", action="store_true", help="also load the mock class timetables"
    )
    parser.add_argument(
        "--documents",
        action="store_true",
        help="also load the mock circulars and event reports (and embed them if Ollama is up)",
    )
    parser.add_argument(
        "--bookings",
        action="store_true",
        help="also add demo bookings, approvals, waitlist and equipment history for the reports",
    )
    parser.add_argument(
        "--embed",
        action="store_true",
        help="index documents for meaning-based search (Ollama must be running), and say why not",
    )
    args = parser.parse_args()
    if args.reset:
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)
    with SessionLocal() as db:
        print(seed_all(db))
        if args.timetables:
            print({"timetable_slots": seed_timetables(db)})
        if args.documents:
            print(seed_documents(db, progress=lambda m: print(m, flush=True)))
        if args.bookings:
            from app.seed.demo_bookings import seed_bookings

            print(seed_bookings(db))
        if args.embed:
            embed(db)


def embed(db) -> None:
    from sqlalchemy import func, select

    from app.models import DocChunk
    from app.services.documents import embed_missing, embedder_for

    embedder = embedder_for(db)
    if embedder is None:
        print("Embeddings are off (EMBEDDINGS=off in backend/.env): search uses keywords only.")
        return
    print(f"Indexing with {embedder.model} at {getattr(embedder, 'base_url', '?')}…", flush=True)
    done = embed_missing(db)
    db.commit()
    total = db.scalar(select(func.count(DocChunk.id)))
    indexed = db.scalar(select(func.count(DocChunk.id)).where(DocChunk.embedding.is_not(None)))
    print(f"Embedded {done} now; {indexed} of {total} documents are indexed by meaning.")
    if getattr(embedder, "last_error", None):
        print(f"Stopped: {embedder.last_error}.")


if __name__ == "__main__":
    main()
