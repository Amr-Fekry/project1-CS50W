import os
import requests

from flask import Flask, session, render_template, redirect, url_for, request, jsonify, abort
from flask_session import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker
from werkzeug.security import check_password_hash, generate_password_hash
from functools import wraps

app = Flask(__name__)

# Check for environment variable
if not os.getenv("DATABASE_URL"):
    raise RuntimeError("DATABASE_URL is not set")

# Configure session to use filesystem
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Set up database
engine = create_engine(os.getenv("DATABASE_URL"))
db = scoped_session(sessionmaker(bind=engine))

def login_required(f):
    """
    Decorate routes to require login.

    http://flask.pocoo.org/docs/0.12/patterns/viewdecorators/
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function


@app.route("/")
@login_required
def index():
	firstname = session["username"].split(' ', 1)[0]
	return render_template("index.html", username=session["username"], firstname=firstname)

@app.route("/login", methods=["GET", "POST"])
def login():
	# if login form is submitted
	if request.method == "POST":
		# GET INPUTS
		username = request.form.get("username")
		password = request.form.get("password")

		# TEST INPUTS
		# if not username or not password:
		# 	return "One or more field is missing! Please try again"
		# (checked on frontend)

		user_exists = db.execute("SELECT * FROM users WHERE username=:username", {"username":username}).rowcount
		if not user_exists:
			# return "username doesn't exist!"
			return render_template("login.html", not_user=True)
			
		user_info = db.execute("SELECT * FROM users WHERE username=:username", {"username":username}).fetchone()
		if not check_password_hash(user_info.password, password):
			# return "password is not correct!"
			return render_template("login.html", wrong_password=True)
		
		# COOKIE USER
		session["user_id"] = user_info.id
		session["username"] = user_info.username

		return redirect(url_for("index"))

	# if login form is requested
	else:	
		return render_template("login.html")

@app.route("/logout")
def logout():
	"""Log user out"""

	# Forget any user_id
	session.clear()
	# Redirect user to login form
	return redirect("/")

@app.route("/register", methods=["GET", "POST"])
def register():
	# if registration form is submitted
	if request.method == "POST":
		# GET INPUTS
		username = request.form.get("username")
		email = request.form.get("email")
		password = request.form.get("password")
		password2 = request.form.get("password2")

		# TEST INPUTS
		# check all values are provided
		# if not username or not email or not password or not password2:
		# 	return "One or more field is missing! Please try again"
		# # check passwords match
		# if password != password2:
		# 	return "Passwords don't match! Please try again"
		# (checked on frontend)

		# check username and email are unique
		username_repeated = db.execute("SELECT * FROM users WHERE username = :username", {"username": username}).rowcount
		email_repeated = db.execute("SELECT * FROM users WHERE email = :email", {"email": email}).rowcount
		if username_repeated:
			# return "username already exists!"
			return render_template("register.html", username_repeated=True)
		if email_repeated:
			# return "email already exists!"
			return render_template("register.html", email_repeated=True)
		
		# HASH PASSWORD
		password = generate_password_hash(password)

		# ADD USER
		try:
			db.execute("""INSERT INTO users (username, email, password)
						  VALUES (:username, :email, :password)""",
						  {"username":username, "email":email, "password":password})
			db.commit()
		except:
			return "Failure"
		
		# COOKIE USER
		user_info = db.execute("SELECT * FROM users WHERE username=:username", {"username":username}).fetchone()
		session["user_id"] = user_info.id
		session["username"] = user_info.username

		return redirect(url_for("index"))

	# if registration form is requested
	else:
		return render_template("register.html")

@app.route("/search")
@login_required
def search():
	# get search text
	q1 = request.args.get("q")
	# if not q1:
	# 	return "Search field is empty!"
	# (checked on frontend)

	# make it partial
	q2 = f"%{q1}%"

	# query database enabling case-insensitivity
	# concatenate columns with separator to prevent results of words between two columns
	book_list = db.execute("""SELECT * FROM books 
		WHERE CONCAT_WS(' ', LOWER(isbn), LOWER(title), LOWER(author), year::text) LIKE LOWER(:q2)""", {"q2":q2}).fetchall()
	# also see COLLATE utf8_general_ci to fix case-insensitivity
	
	return render_template("index.html", q1=q1, book_list=book_list, username=session["username"])

@app.route("/clicksearch")
@login_required
def clicksearch():
	"""for search on click, so that a clicked on year doesn't yield isbn results"""

	# get search text
	q1 = request.args.get("q")
	# make it partial
	q2 = f"%{q1}%"
	
	# year clicked
	if len(q1) == 4:
		try:
			# confirm it is an integer
			is_it_integer = int(q1)
			book_list = db.execute("""SELECT * FROM books 
			WHERE year::text = :q1""", {"q1":q1}).fetchall()
		except: pass
	# author clicked
	else:
		book_list = db.execute("""SELECT * FROM books 
			WHERE LOWER(author) LIKE LOWER(:q2)""", {"q2":q2}).fetchall()
	
	return render_template("index.html", q1=q1, book_list=book_list, username=session["username"])

@app.route("/reviews")
@login_required
def reviews():
	# get current user reviews from my DB
	user_reviews = db.execute("SELECT isbn, title, author, year FROM reviews, users, books WHERE users.id = reviews.user_id AND books.id = reviews.book_id AND username=:username", {"username": session["username"]}).fetchall()
	return render_template("index.html", reviews_query=True, user_reviews=user_reviews[::-1], username=session["username"])


@app.route("/book/<string:isbn>", methods=["GET", "POST"])
@login_required
def book(isbn):

	# get book's basic info from my DB
	book_info = db.execute("SELECT * FROM books WHERE isbn=:isbn", {"isbn":isbn}).fetchone()
	
	if request.method == "GET":
		# get book's review info from goodreads
		response = requests.get("https://www.goodreads.com/book/review_counts.json", params={"key": "yLM7LLyUkFTyeElwIrzUDA", "isbns": isbn})
		goodreads_info = response.json()
		# get book's review info from my DB
		reviews = db.execute("SELECT rating, opinion, username FROM reviews JOIN users ON users.id = reviews.user_id WHERE book_id=:book_id", {"book_id": book_info.id}).fetchall()
		# check if current user submitted a review
		user_submitted_review = False
		for review in reviews:
			if review.username == session["username"]:
				user_submitted_review = True

		return render_template("book.html", book_info=book_info, goodreads_info=goodreads_info, reviews=reviews, user_submitted_review=user_submitted_review, username=session["username"])
	else:
		# get review data
		opinion = request.form.get("opinion")
		rating = request.form.get("rating")
		
		# get around the 'selected' rating option value
		# if rating not in ('1','2','3','4','5'): rating = None
		# fixed with value="" attribute

		# check data exist
		# if not opinion or not rating:
		# 	return "opinion or rating is missing!"
		# (checked on frontend)

		# ???? opinion shouldn't be a must, update DB

		# append <br> to \n so that new lines are translated 
		opinion = opinion.replace('\n','<br>\n')
		# nl2br. see https://stackoverflow.com/a/30593254
		# unescape html. see http://flask.pocoo.org/docs/1.0/quickstart/#rendering-templates
		
		# ADD REVIEW
		try:
			db.execute("""INSERT INTO reviews (book_id, user_id, rating, opinion)
						  VALUES (:book_id, :user_id, :rating, :opinion)""",
						  {"book_id": book_info.id, "user_id": session["user_id"], "rating": rating, "opinion": opinion})
			db.commit()
		except:
			return "Failure"

		return redirect(f"/book/{isbn}")


@app.route("/api")
def api_info():
	return render_template("api.html", username=session["username"])

@app.route("/api/<string:isbn>")
def api(isbn):
	
	# if isbn in DB
	try:
		# get book's basic info from my DB
		book_info = db.execute("SELECT * FROM books WHERE isbn=:isbn", {"isbn":isbn}).fetchone()

		# get ratings count
		review_count = db.execute("SELECT COUNT(rating) FROM reviews JOIN books ON books.id=reviews.book_id WHERE isbn=:isbn", {"isbn":isbn}).scalar()
		# get ratings average
		review_avg = db.execute("SELECT AVG(rating) FROM reviews JOIN books ON books.id=reviews.book_id WHERE isbn=:isbn", {"isbn":isbn}).scalar()
		# scalar() fetches first col of first row = fetchall()[0]

		# if no reviews, set avg to 0 instead of None
		if not review_avg:
			review_avg = 0

		# return f"{review_count}, {review_avg}" # testing
		return jsonify (
		    title=book_info.title,
		    author=book_info.author,
		    year=book_info.year,
		    isbn=isbn,
		    review_count=int(review_count),
		    average_score=float(review_avg)
		) # jsonify takes a dict or any json serializable

	# if isbn not in DB
	except:
		abort(404)


if __name__=="__main__":
	app.run()

