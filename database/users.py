"""
Account administration from the command line. Roles: user, moderator (handles reports),
admin (also names / removes moderators on the site). Making someone an admin is only possible
here, on purpose: nobody can give themselves that on the site.

    python -m database.users role Barbaaz admin        # admin / moderator / user
    python -m database.users list                      # accounts, newest first
"""
import argparse

from sqlalchemy import select

from app.models import ROLES, User
from db import session


def set_role(username, role):
    if role not in ROLES:
        raise SystemExit(f"Role must be one of: {', '.join(ROLES)}")
    with session() as s:
        user = s.scalars(select(User).where(User.username == username)).first()
        if not user:
            raise SystemExit(f"No user called {username!r}")
        user.role = role
        return user.username


def list_users():
    with session() as s:
        for u in s.scalars(select(User).order_by(User.created_at.desc())):
            flags = " ".join(f for f, on in ((u.role, u.role != "user"), ("BLOCKED", not u.is_active)) if on)
            print(f"{u.id:5}  {u.username or '-':20} {u.email:35} {u.created_at:%Y-%m-%d}  {flags}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    role = sub.add_parser("role", help="set a user's role")
    role.add_argument("username")
    role.add_argument("role", choices=ROLES)
    sub.add_parser("list", help="list the accounts")
    args = parser.parse_args()
    if args.command == "role":
        print(f"{set_role(args.username, args.role)} is now: {args.role}")
    else:
        list_users()
