from flask_sqlalchemy import SQLAlchemy

dbref = SQLAlchemy()

# Modelli
user_articles = dbref.Table('user_articles',
    dbref.Column('user_id', dbref.Integer, dbref.ForeignKey('user.id'), primary_key=True),
    dbref.Column('article_id', dbref.Integer, dbref.ForeignKey('article.id'), primary_key=True)
)

class User(dbref.Model):
    id = dbref.Column(dbref.Integer, primary_key=True)
    created_at = dbref.Column(dbref.DateTime(timezone=True), server_default=dbref.func.now())
    password = dbref.Column(dbref.String(72), nullable=False)
    wallet = dbref.Column(dbref.Float, nullable=False, default=100.00)
    articles = dbref.relationship('Article', secondary=user_articles, backref='buyers')
    token = dbref.Column(dbref.String(100), nullable=False)
    email = dbref.Column(dbref.String(100), nullable=False)
    username = dbref.Column(dbref.String(100), unique=True, nullable=False)

    def as_dict(self):
        exclude_keys = ['password', 'articles']
        return {c.name: getattr(self, c.name) for c in self.__table__.columns if not c.name in exclude_keys}

class Article(dbref.Model):
    id = dbref.Column(dbref.Integer, primary_key=True)
    title = dbref.Column(dbref.String(80), nullable=False)
    description = dbref.Column(dbref.String(100), nullable=False, default="")
    price = dbref.Column(dbref.Float, nullable=False)
    secret = dbref.Column(dbref.String(200), default="")
    img = dbref.Column(dbref.String(100), nullable=False, default="")
    
    def as_dict(self):
        exclude_keys = ['secret']
        return {c.name: getattr(self, c.name) for c in self.__table__.columns if not c.name in exclude_keys}
    
    def as_dict_with_secret(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}