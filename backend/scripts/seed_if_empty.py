"""Seeds the demo world only if the database is currently empty -- safe to
call on every startup rather than once by hand.

Exists for hosting platforms with an ephemeral filesystem (Render's free
tier wipes local disk on every redeploy, and possibly on a wake from sleep
too): unconditionally re-running scripts/seed_demo_world.py would hit
unique-constraint errors against already-seeded data, and running it only
once by hand doesn't survive whatever wiped the disk. Checking "is there
already a client" and skipping if so makes this the same one command
whether it's the very first boot or the hundredth.
"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.db.session import SessionLocal, create_all_tables  # noqa: E402
from app.models.client import Client  # noqa: E402


def main() -> None:
    create_all_tables()
    with SessionLocal() as db:
        already_seeded = db.execute(select(Client.id).limit(1)).scalar_one_or_none() is not None

    if already_seeded:
        print("seed_if_empty: database already has data -- skipping seed.")
        return

    print("seed_if_empty: database is empty -- seeding the demo world.")
    subprocess.run(
        [sys.executable, str(Path(__file__).with_name("seed_demo_world.py")), "--run"],
        check=True,
    )


if __name__ == "__main__":
    main()
