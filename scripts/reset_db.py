"""Start again with an empty database.

    python -m scripts.reset_db

Backs up the current database first. The do-not-contact list is NOT lost:
it is kept in suppression/do_not_contact.csv and restored automatically.
Stop the app before running this.
"""
from app import config
from app.backup import run_backup


def main() -> None:
    print(f"This deletes all businesses, emails and replies in {config.DATABASE_PATH.name}.")
    print("The do-not-contact list is kept, and a backup is made first.")
    if input("Type RESET to continue: ").strip() != "RESET":
        print("Cancelled.")
        return
    folder = run_backup(force=True)
    if not folder:
        print("Backup failed (see logs/app.log), so nothing was deleted.")
        return
    print(f"Backup saved in {folder}")
    for suffix in ("", "-wal", "-shm"):
        p = config.DATABASE_PATH.with_name(config.DATABASE_PATH.name + suffix)
        if p.exists():
            p.unlink()
    print("Database deleted. Start the app again and an empty one will be created.")


if __name__ == "__main__":
    main()
