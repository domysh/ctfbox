import os
import sqlite3, hashlib, uuid

from flask import Flask, g, render_template, request, redirect, abort

app = Flask(__name__)

NOTE_ID_PREFIX = 'note_'

def get_db() -> sqlite3.Connection:
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(os.getenv('DB_PATH'))
    return db


@app.teardown_appcontext
def close_db_conn(_exc):
    db = getattr(g, '_database', None)
    if db is not None:
        db.commit()
        db.close()


@app.route('/')
def index():
    cur = get_db().execute('select id, title from notes where private = 0')
    cur.row_factory = lambda _, x: {'id': x[0], 'title': x[1]}
    notes = cur.fetchall()

    return render_template('index.html', notes=notes)


@app.route('/view/<note_id>')
def view_note(note_id: str):
    cur = get_db().execute('select title, content, uuid from notes where id = ?', (note_id,))
    cur.row_factory = lambda _, x: {'title': x[0], 'content': x[1], 'uuid': x[2]}

    try:
        note = next(cur)
    except StopIteration:
        return abort(404)

    return render_template('view.html', note=note)


@app.route('/new', methods=['GET', 'POST'])
def new_note():
    if request.method == 'POST':
        title = request.form.get('title')
        if not title:
            return abort(400)

        content = request.form.get('content')
        if not content:
            return abort(400)

        private = 1 if 'private' in request.form else 0


        uuid_str = request.form.get('uuid')
        if not uuid_str:
            uuid_str = str(uuid.uuid4())
        
        db = get_db()
        
        cur = db.execute('select id from notes where uuid = ?', (uuid_str,))
        cur.row_factory = lambda _, x: {'id': x[0]}

        try:
            note = next(cur)
            return redirect(f'/view/{note["id"]}') # note already exists, redirect to it
        except StopIteration:
            pass # That's fine, we can create a new note
            
        note_id = hashlib.md5((NOTE_ID_PREFIX+uuid_str).encode()).hexdigest()
        cur = db.execute(
            f"insert into notes (private, title, content, id, uuid) values (?, ?, ?, ?, ?)",
            (private, title, content, note_id, uuid_str)
        )
        return redirect(f'/view/{note_id}')

    return render_template('new.html')


def create_app():
    with app.app_context():
        get_db().execute("""
        create table if not exists notes (
            id varchar(32) primary key,
            uuid varchar(36),
            private integer, 
            title text, 
            content text
        )""")

    return app


if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=5000)
