#!/usr/bin/env python3
"""Reset or create the admin user.

Usage:
    python scripts/reset_admin.py                     # interactive prompt
    python scripts/reset_admin.py admin newpassword   # non-interactive

Run from the project root directory.
"""

import sys
from pathlib import Path

# Add project root to path so app imports work
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.database import SessionLocal, init_db
from app.db.models import User
from app.services.user_service import user_service


def main() -> None:
    init_db()

    # Get username and password from args or prompt
    if len(sys.argv) == 3:
        username = sys.argv[1]
        password = sys.argv[2]
    else:
        username = input("Admin username [admin]: ").strip() or "admin"
        import getpass

        password = getpass.getpass("New password: ")
        confirm = getpass.getpass("Confirm password: ")
        if password != confirm:
            print("ERROR: Passwords do not match.")
            sys.exit(1)

    if not password:
        print("ERROR: Password must not be empty.")
        sys.exit(1)

    with SessionLocal() as db:
        user = db.query(User).filter(User.username == username).first()

    if user:
        # Reset password for existing user
        ok = user_service.set_password(user.id, password)
        if ok:
            print(f"Password reset for user '{username}' (id={user.id}).")
        else:
            print(f"ERROR: Could not reset password for '{username}'.")
            sys.exit(1)
    else:
        # Create new admin user
        try:
            new_user = user_service.create_user(
                username=username,
                password=password,
                is_admin=True,
            )
            print(f"Admin user '{username}' created (id={new_user.id}).")
        except ValueError as e:
            print(f"ERROR: {e}")
            sys.exit(1)


if __name__ == "__main__":
    main()
