import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.seed import seed_development_data


if __name__ == "__main__":
    seed_development_data()
