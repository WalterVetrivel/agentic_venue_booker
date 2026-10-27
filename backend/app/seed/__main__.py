import argparse

from app.db import Base, SessionLocal, engine
from app.seed.seed import seed_all, seed_timetables


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the database with mock data")
    parser.add_argument("--reset", action="store_true", help="drop all tables first")
    parser.add_argument(
        "--timetables", action="store_true", help="also load the mock class timetables"
    )
    args = parser.parse_args()
    if args.reset:
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)
    with SessionLocal() as db:
        print(seed_all(db))
        if args.timetables:
            print({"timetable_slots": seed_timetables(db)})


if __name__ == "__main__":
    main()
