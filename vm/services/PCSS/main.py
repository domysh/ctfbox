#!/usr/bin/env python3

import subprocess, secrets, os, jwt

banner = """
PCSS - Permanent Cat Storage Service

          /\\_/\\  
         ( o.o )    Meow!
          > ^ <   
        /       \\ 
      __|_______|__
     |             |
     |   WELCOME   |
     |_____________|

Meow! I'm a cat and I'm here to help you store your files.
A more secure, reliable and fun way to store your files, even better than S3 buckets!
"""

no_login_menu_text = """1. Create a new database
2. Access an existing database
3. Exit
"""

login_menu_text = """1. Read a file
2. Create a file
3. List files
4. Exit
"""

class ctx:
    loggined_db = None

SECRET_KEY = os.getenv("SECRET_KEY") #Correctly generated: it is different for each team

assert not SECRET_KEY is None

jwt_encoder = jwt.jwk.OctetJWK(SECRET_KEY.encode())

try:
    os.mkdir("./data")
except FileExistsError:
    pass

def int_input(prompt:str):
    while True:
        try:
            return int(input(prompt))
        except ValueError:
            print("Invalid input")

def sep():
    print("-"*50)

def generate_token(data:dict):
    return jwt.JWT().encode(data, jwt_encoder)

def decode_token(token:str):
    return jwt.JWT().decode(token, jwt_encoder)

def cmd(cmd:list):
    return subprocess.run(cmd)

def create_db():
    database_generated = secrets.token_hex(32)
    cmd(["mkdir", f"./data/{database_generated}"])
    print(f"Database generated: {database_generated}")
    print(f"Please keep this token safe to access again: {generate_token({'db': database_generated})}")
    ctx.loggined_db = database_generated
    sep()

def login_db():
    token = input("Please insert your token: ").strip()
    try:
        decoded = decode_token(token)
    except Exception:
        print("Invalid token")
        return
    
    if 'db' in decoded:
        if os.path.exists(f"./data/{decoded['db']}"):
            ctx.loggined_db = decoded['db']
            print("Logged in successfully")
        else:
            print("Database not found")
    else:
        print("Invalid token")
    

def read_file():
    file = input("Please insert the file name: ").strip()
    print("File content:")
    subprocess.run(["cat", f"./data/{ctx.loggined_db}/{file}"])
    print()
    sep()

def create_file():
    file = input("Please insert the file name: ").strip()
    content = input("Please insert the file content: ").strip()
    if os.path.exists(f"./data/{ctx.loggined_db}/{file}"): #This is an unmutable database, we can't overwrite files
        print("File already exists")
    else:
        with open(f"./data/{ctx.loggined_db}/{file}", "w") as f:
            f.write(content)
    sep()

def list_files():
    print("Files:")
    cmd(["ls", f"./data/{ctx.loggined_db}"])
    sep()


def no_login_menu():
    print(no_login_menu_text)
    choice = int_input("Insert your choice: ")
    if choice == 1:
        create_db()
    elif choice == 2:
        login_db()
    elif choice == 3:
        exit()
    else:
        print("Invalid choice")

def login_menu():
    print(login_menu_text)
    choice = int_input("Insert your choice: ")
    if choice == 1:
        read_file()
    elif choice == 2:
        create_file()
    elif choice == 3:
        list_files()
    elif choice == 4:
        exit()
    else:
        print("Invalid choice")


def main():
    try:
        print(banner)
        sep()
        while True:
            if ctx.loggined_db is None:
                no_login_menu()
            else:
                login_menu()
    except KeyboardInterrupt:
        print("\nBye!")


if __name__ == '__main__':
    main()
