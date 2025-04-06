from flask import Flask, request, session, send_file, send_from_directory
from werkzeug.security import safe_join
from flask_session import Session
from flask_cors import CORS, cross_origin
from sqlalchemy import text
from config import DOCKER, SECRET_KEY
from sqlalchemy.exc import IntegrityError
from utils import create_token, encode_with_words, log_lock, get_logged_user
from werkzeug.exceptions import HTTPException
from db import *
import os, bcrypt, subprocess
import random
import sqlite3

# Configurazione dell'app
app = Flask(__name__)



basedir = os.path.abspath(os.path.dirname(__file__))
frontend_folder = os.path.join(basedir, "frontend") if DOCKER else os.path.join(basedir, "../frontend/dist")
dbpath = os.path.join(basedir, 'db-data')
os.makedirs(dbpath, exist_ok=True)

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(dbpath, 'database.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SESSION_PERMANENT'] = False
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SECRET_KEY'] = SECRET_KEY

# Flask sessions
Session(app)
# DB init
dbref.init_app(app)

def getdbconn():
    return sqlite3.connect(f"file://{os.path.join(dbpath, 'database.db')}?mode=ro", uri=True)

if not DOCKER:
    CORS(app, supports_credentials=True, allow_headers=["Content-Type", "X-Requested-With", "X-Forwarded-For"])  # Enable CORS with credentials

with app.app_context():
    dbref.create_all()

@app.errorhandler(HTTPException)
def handle_http_exception(e: HTTPException):
    return { "message": str(e.description) }, e.code

# Rotte
@app.route('/api/articles', methods=['GET'])
def get_articles():
    user = get_logged_user()
    return [
        {
            **article.as_dict(),
            "purchased": article in user.articles,
            **({"secret": article.secret} if article in user.articles else {})
        }
        for article in Article.query.all()
    ]

@app.route('/api/register', methods=['POST'])
def register():
    
    username = request.json.get('username')
    password = request.json.get('password')
    email = request.json.get('email')
    
    if not email:
        return {"message": "Email is required"}, 400
    if not username or not password:
        return {"message": "Username and password are required"}, 400
    
    token = create_token(username)
    hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    
    try:
        new_user = User(username=username, password=hashed, token=token, email=email)
        dbref.session.add(new_user)
        dbref.session.commit()
    except IntegrityError:
        return {"message": "User already exists"}, 400
    
    session['user_id'] = new_user.id

    return {
        "message": "User registered successfully",
        "user": new_user.as_dict()
    }, 200

@app.route('/api/login', methods=['POST'])
@cross_origin(supports_credentials=True)
def login():
    username = request.json.get('username')
    password = request.json.get('password')

    if not username or not password:
        return {"message": "Username and password are required"}, 400

    try:
        dbconn = getdbconn()
        user = dbconn.execute(f"""
            SELECT id, password
            FROM user
            WHERE username = '{username}'
        """).fetchone()
    finally:
        dbconn.close()
    
    if user is None:
        return {"message": "Invalid credentials"}, 401

    session['user_id'] = user[0]

    return {
        "message": "Login successful",
        "user": get_logged_user().as_dict()
    }, 200

@app.route('/api/donate', methods=['POST'])
def donate():
    
    user = get_logged_user()
    amount = request.json.get('price')
    
    if not amount:
        return {"message": "Price is required"}, 400
    
    try:
        amount = float(amount)
    except Exception:
        return {"message": "Price must be a number."}, 400

    if user.wallet < amount:
        return {"message": "Insufficient funds"}, 400

    user.wallet -= amount
    dbref.session.commit()

    return {"message": "Donation successful"}, 200


@app.route('/api/sell', methods=['POST'])
def sell():
    
    user = get_logged_user()
    
    title = request.json.get('title')
    description = request.json.get('description')
    price = request.json.get('price')
    secret = request.json.get('secret')
    
    if any([x is None for x in [title, description, secret, price]]):
        return {"message": "Some fields are missing"}, 400
    
    try:
        price = abs(float(price))
    except Exception:
        return {"message": "Price must be a number."}, 400    

    new_article = Article(title=title, description=description, price=price, secret=secret, img=f"/imgs/art{random.randint(0, 9)}.jpg")
    dbref.session.add(new_article)
    user.articles.append(new_article)
    dbref.session.commit()
    
    with log_lock:
        with open('./db-data/log.txt', 'a') as file:
            file.write(f'[NEW] Article added! (id: {new_article.id}, {encode_with_words(secret, new_article.id)})\n')

    return {"message": "Article successfully added!", "article": new_article.as_dict()}, 201

@app.route('/api/store/<int:article_id>/buy', methods=['POST'])
def buy_article(article_id):
    
    user = get_logged_user()
    
    forwarded_for = request.headers.get('X-Forwarded-For')

    article = Article.query.filter_by(id=article_id).first()
    if article is None:
        return {"message": "Article not found"}, 404

    if forwarded_for == '127.0.0.1':

        user.articles.append(article)
        dbref.session.commit()

        return {
            "message": "Article purchased successfully",
            "article": article.as_dict()
        }, 200

    if user.wallet < article.price:
        return {"message": "Insufficient funds"}, 400

    user.wallet -= article.price
    user.articles.append(article)
    dbref.session.commit()

    return {
        "message": "Article purchased successfully",
        "article": article.as_dict()
    }, 200


@app.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    return {"message": "Logged out successfully"}

@app.route('/api/logs', methods=['GET'])
def read_file():
    if os.path.exists("./db-data/log.txt"):
        return send_file('./db-data/log.txt', mimetype='text/plain')
    else:
        return {"message": "Log file not found"}, 404

@app.route('/api/user', methods=['GET'])
def get_user():
    user = get_logged_user()
    return user.as_dict(), 200

@app.route('/api/login/token', methods=['POST'])
def login_token():
    token = request.json.get('token')

    if not token:
        return {"message": "Token required"}, 400

    user = User.query.filter_by(token=token).first()

    if user and token:
        session['user_id'] = user.id
        
        return {
            "message": "Login successful",
            "user": user.as_dict()
        }, 200
    
    return {"message": "Invalid credentials"}, 401

@app.route('/')
def index():
    return send_from_directory(frontend_folder, "index.html")

@app.route('/<path:path>')
def catch_all(path):
    final_path = safe_join(frontend_folder, path)
    if os.path.exists(final_path):
        return send_from_directory(frontend_folder, path)
    else:
        return send_from_directory(frontend_folder, "index.html")

if __name__ == "__main__":
    try:
        if not DOCKER:
            app.run(host='0.0.0.0', port=1234, debug=True)
        else:
            os.chdir(basedir)
            subprocess.Popen(["gunicorn", "--workers", "4", "--reuse-port", "--bind", "0.0.0.0:1234", "app:app"]).wait()
    except KeyboardInterrupt:
        pass
