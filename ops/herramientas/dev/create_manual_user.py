#!/usr/bin/env python3
import sys
import os

# Add code/sistema_gestion to path
sys.path.append("/srv/monstruo_dev/code/sistema_gestion")

import nucleo

def main():
    username = "admin_test"
    password = "test1234"
    role = "admin"
    print(f"Creating user {username}...")
    try:
        nucleo.create_user(username, password, role)
        print("User created successfully.")
    except Exception as e:
        print(f"Error creating user: {e}")

if __name__ == "__main__":
    main()
