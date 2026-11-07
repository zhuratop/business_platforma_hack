"""Create a local service account without exposing passwords in shell history."""
import argparse
import getpass
from backend.app.storage import meta


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('username')
    args = parser.parse_args()
    password = getpass.getpass('Password (at least 8 characters): ')
    if password != getpass.getpass('Repeat password: '):
        parser.error('Passwords do not match')
    meta.init()
    try:
        meta.create_user(args.username,password)
    except ValueError as exc:
        parser.error(str(exc))
    print(f'User {args.username} created')


if __name__=='__main__':
    main()
