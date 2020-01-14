# coding: utf-8
import flask
from functools import wraps
#sqlalchemy
from flask_sqlalchemy import SQLAlchemy
#custom config
import config
#datetime
from datetime import datetime as dt
#from datetime import date, timedelta
#crypt for user's password
from flask_bcrypt import Bcrypt
#os for file processing
import os
from json import dumps as json_dumps
#image processings
#from PIL import Image as ProcessImage
#from PIL import ImageFont, ImageFilter, ImageDraw
#from resize_and_crop import resize_and_crop
#from random import randrange
#https connection
#from OpenSSL import SSL
#flask_admin
from flask_admin import Admin, AdminIndexView, expose
from flask_admin.contrib.sqla import ModelView

app = flask.Flask(__name__)

bcrypt = Bcrypt(app)
app.secret_key = config.secret_key

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + config.db_file
app.config['UPLOAD_FOLDER'] = config.UPLOAD_FOLDER
#app.config['SQLALCHEMY_ECHO'] = True
app.config['MAX_CONTENT_LENGTH'] = 80 * 1024 * 1024 #80mb max
db = SQLAlchemy(app)

#------------------------<databases classes>------------------------------

task_lists = db.Table('task_lists',
    db.Column('task_list_id', db.Integer, db.ForeignKey('task_list.id'), primary_key=True),
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True)
)

task_followers = db.Table('task_followers',
    db.Column('task_id', db.Integer, db.ForeignKey('task.id'), primary_key=True),
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True)
)

class User(db.Model):

	id = db.Column(db.Integer, primary_key=True, autoincrement=True)
	username = db.Column(db.String())
	email = db.Column(db.String())
	password = db.Column(db.String())
	#privileges = db.Column(db.Integer, db.ForeignKey("privilege.id"), nullable=False, default = 3)
	tasks = db.relationship('Task', backref='user', lazy=True)
	comments = db.relationship('Comment', backref='user', lazy=True)
	task_lists = db.relationship('Task_list', secondary=task_lists, lazy='subquery',
        backref=db.backref('users', lazy=True))
	task_following = db.relationship('Task', secondary=task_followers, lazy='subquery',
        backref=db.backref('followers', lazy=True))

	def __repr__(self):
		return self.username

class Task(db.Model):

	id = db.Column(db.Integer, primary_key=True, autoincrement=True)
	user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
	title = db.Column(db.String(), nullable=False)
	details = db.Column(db.String())
	date = db.Column(db.DateTime)
	parent_task_id = db.Column(db.Integer, db.ForeignKey('task.id'))
	parent_task = db.relationship('Task', remote_side=[id], backref="sub_task")
	task_list_id = db.Column(db.Integer, db.ForeignKey("task_list.id"), nullable=False)
	comments = db.relationship('Comment', backref='task', lazy=True)
	closed = db.Column(db.Boolean)
	#got_update = db.Column(db.Boolean)

	def follow(self, creator_id):
		for user in self.task_list.users:
			if user.id != creator_id:
				self.followers.append(user)
		if self.parent_task:
			self.parent_task.follow(creator_id)
		return True

	def unfollow(self, user):
		if user in self.followers: #if user unread the task
			has_unread = False
			for sub_task in self.sub_task: #list all negighbours for current task
				if sub_task in user.task_following: #if neighbour unread
					has_unread = True
			if not has_unread:
				self.followers.remove(user)
			if self.parent_task: #if task has parent task
				self.parent_task.unfollow(user)			
		return True

	def __repr__(self):
		return self.title

class File(db.Model):

	id = db.Column(db.Integer, primary_key=True, autoincrement=True)
	task_id = db.Column(db.Integer, db.ForeignKey("comment.id"), nullable=False)
	file_name = db.Column(db.String())

	def __repr__(self):
		return self.file_name

class Task_list(db.Model):

	id = db.Column(db.Integer, primary_key=True, autoincrement=True)
	name = db.Column(db.String())
	tasks = db.relationship('Task', backref='task_list', lazy=True)
	task_order = db.Column(db.String())

	def get_order(self):
		if self.task_order:
			return self.task_order.split(',')
		else:
			l = []
			for task in self.tasks:
				l.append(task.id)
			return l

	def set_order(self, new_order):
		self.task_order = ','.join(map(str, new_order))
		return True

	def add_to_order(self, task_id):
		order = self.get_order()
		order.append(task_id)
		self.set_order(order)
		return True

	def rem_from_order(self, task_id):
		order = self.get_order()
		while str(task_id) in order:
			order.pop(order.index(str(task_id)))
		self.set_order(order)
		return True

	def __repr__(self):
		return self.name

class Comment(db.Model):

	id = db.Column(db.Integer, primary_key=True, autoincrement=True)
	task_id = db.Column(db.Integer, db.ForeignKey("task.id"), nullable=False)
	user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
	date = db.Column(db.DateTime)
	text = db.Column(db.String())
	files = db.relationship('File', backref='comment', lazy=True)

	def __repr__(self):
		return self.text

db.create_all()

#------------------/database classes/---------------------------

#-------------------<tool functions>---------------------------

#decorator to check if user logged in
def is_logged(func):
	@wraps(func)
	def wrapper(*args, **kwargs):
		if 'logged' in flask.session:
			return func(*args, **kwargs)
		else:
			return flask.redirect(flask.url_for("login"))
	return wrapper

def user_allowed(func): # check if user in task_list
	@wraps(func)
	def wrapper(*args, **kwargs):
		user = User.query.get(flask.session['user_id'])

		if not user:
			return page_not_found(404)

		if len(user.task_lists) > 0:
			list_id = flask.request.args.get('list_id', default = user.task_lists[-1].id, type = int)
			try:
				if user in Task_list.query.get(list_id).users:
					return func(*args, **kwargs)
				else:
					flask.flash("Sorry, you have no access to the task list you requested")
					return flask.redirect(flask.url_for("index"))
			except Exception as e:
				return page_not_found(e)
		else:
			return flask.render_template("new_user.html", user=user)
	return wrapper

#------------------/tool functions/---------------------------

#------------------<flask_admin>--------------------------------

#restict access to /admin index
class MyAdminIndexView(AdminIndexView):

	def is_visible(self):
		return False

#list of users in admin
class UserView(ModelView):
	column_display_pk = True

class TaskView(ModelView):
	column_display_pk = True

class TaskListView(ModelView):
	column_display_pk = True

#initialize admin views
admin = Admin(app, name='admin', template_mode='bootstrap3', index_view=MyAdminIndexView(), url='/')
admin.add_view(UserView(User, db.session, 'Пользователи', url='/admin/user'))
admin.add_view(TaskView(Task, db.session, 'Tasks', url='/admin/tasks'))
admin.add_view(TaskListView(Task_list, db.session, 'Task lists', url='/admin/lists'))

#---------------------/flask_admin/---------------------

#-----------------<paths for static files>-------------------

@app.route('/fonts/<path:path>')
def send_fonts(path):
	return flask.send_from_directory('fonts', path)

@app.route('/uploads/<path:path>')
def send_uploads(path):
	return flask.send_from_directory('uploads', path)

#------------------/paths for static files/------------------

#--------------------<session control>----------------------

@app.route("/login", methods=['GET', 'POST'])
def login():
	if flask.request.method == 'POST':
		#get data from form
		login = flask.request.form["login"] 
		password = flask.request.form["password"]
		user_data = User.query.filter_by(username = login).first()
		if user_data is not None:
			if bcrypt.check_password_hash(user_data.password, str(password)): #compare user input and password hash from db
				#set session info in crypted session cookie
				flask.session['logged'] = "yes"
				flask.session['user_id'] = user_data.id
				return flask.redirect(flask.url_for("index"))
			else:
				flask.flash("Wrong password. Try again")
		else:
			flask.flash("Wrong Login. Try again")
	return flask.render_template("login.html")

@app.route("/register", methods=['GET', 'POST'])
def register():
	if flask.request.method == 'POST':
		f = flask.request.form.to_dict(flat=False) #get data from form
	
		if [''] in f.values(): #if there's any empty field
			flask.flash("Не все поля заполнены")
			return flask.redirect(flask.url_for("register"))
		elif f['password'][0] != f['password_check'][0]: #if passwords doesn't match
			flask.flash("Пароли не совпадают")
			return flask.redirect(flask.url_for("register"))
		else:
			#check if username already in db
			if User.query.filter_by(username = f["login"][0]).first():
				flask.flash("Пользователь с таким именем уже существует")
				return flask.redirect(flask.url_for("register"))
			else:
				#create new user
				new_user = User(username = f["login"][0],email=f["email"][0], password = bcrypt.generate_password_hash(str(f["password"][0])))
				db.session.add(new_user)
				db.session.commit()

		return flask.redirect(flask.url_for("login"))
	else:
		return flask.render_template("register.html")

@app.route("/edit_user", methods=['POST']) #edit user profile
@is_logged
def edit_user():
	f = flask.request.form.to_dict(flat=False) #get data from form
	user = User.query.filter_by(username = flask.request.args.get('username', type = str)).first() #find user in db

	if f['new_password'] == ['']: #if password fields was filled
		if user:
			user.username = f["new_username"][0]
			user.email = f["new_email"][0]
			db.session.commit()
	elif f['new_password'][0] != f['new_password_repeat'][0]: #if passwords doesn't match
		flask.flash("Passwords doesn't match")
	else:
		#check if username in db
		if user:
			user.username = f["new_username"][0]
			user.email = f["new_email"][0]
			user.password = bcrypt.generate_password_hash(str(f["new_password"][0]))
			db.session.commit()
			flask.flash("Info successfully updated")
		else:
			flask.flash("User not found")

	return flask.redirect(flask.url_for("index"))

@app.route("/exit", methods=["GET"])
def exit():
	flask.session.clear() #clear session when user log out
	return flask.redirect(flask.url_for("login"))

#---------------------/session control/--------------------------

#
#All info about current position (task_list and task) are stored in url arguments
#

@app.route('/update_order', methods=["GET","POST"])
def update_order():
	list_id = flask.request.args.get('list_id', default = User.query.get(flask.session['user_id']).task_lists[-1].id, type = int)

	task_list = Task_list.query.get(list_id)
	task_list.task_order = str(flask.request.json)
	db.session.commit()
	return json_dumps({'success': True}), 200, {'ContentType':'application/json'} 

@app.errorhandler(404)
def page_not_found(error):
	return flask.render_template('404.html', title = '404', error = error), 404

@app.route("/", methods=["GET"])
@is_logged
@user_allowed
def index():
	#fetch opened task_list and task
	list_id = flask.request.args.get('list_id', default = User.query.get(flask.session['user_id']).task_lists[-1].id, type = int)
	task_id = flask.request.args.get('task_id', default = None, type = int)

	if task_id:
		task = Task.query.get(task_id)
		if task:
			task.unfollow(User.query.get(flask.session['user_id']))
			db.session.commit()
	else:
		task = None

	return flask.render_template("task.html", 
		task_list = Task_list.query.get(list_id),
		task = task,
		user = User.query.get(flask.session['user_id']))

@app.route("/new_comment", methods=["POST"])
@is_logged
@user_allowed
def new_comment():

	task_id = flask.request.args.get('task_id', default = None, type = int)

	new_comment = Comment(user_id = flask.session['user_id'],
		task_id = task_id,
		text = flask.request.form['comment'],
		date = dt.now())
	db.session.add(new_comment)

	task = Task.query.get(task_id)
	task.follow(flask.session['user_id']) #mark task as unread

	if 'file' not in flask.request.files:
		flask.flash('File not found.')
		return flask.redirect(flask.request.url)

	files = flask.request.files.getlist("file")
	if not files[0].filename == '': # if filename is empty
		db.session.flush()

		for file in files: #save every file
			file.save(os.path.join(config.UPLOAD_FOLDER, file.filename)) #save this file
			new_file = File(task_id = new_comment.id, file_name = file.filename)
			db.session.add(new_file)

	db.session.commit()
	return flask.redirect(flask.url_for("index", task_id = task_id))


@app.route("/remove_list", methods=["POST"])
@is_logged
@user_allowed
def remove_list():

	task_list = Task_list.query.get(flask.request.args.get('list_id', type = int))

	for task in task_list.tasks:
		db.session.delete(Task.query.get(task.id))
	db.session.delete(task_list)
	db.session.commit()

	return flask.redirect(flask.url_for('index'))


@app.route("/close_task", methods=["POST"])
@is_logged
@user_allowed
def close_task():
	#print(flask.request.args.get("backurl"))

	task = Task.query.get(flask.request.args.get("target", type=int))

	if task.parent_task: #if task has a parent then mark it as unread for all users except current user
		task.follow(flask.session['user_id'])

	task.closed = True
	Task_list.query.get(task.task_list_id).rem_from_order(task.id)
	for child in task.sub_task:
		child.closed = True
	db.session.commit()

	return flask.redirect(flask.url_for("index", list_id = flask.request.args.get('list_id', type = int), task_id = task.parent_task_id))


@app.route("/remove_task", methods=["POST"])
@is_logged
@user_allowed
def remove_task():

	task = Task.query.get(flask.request.args.get("target", type=int))

	Task_list.query.get(task.task_list_id).rem_from_order(task.id)
	for comment in task.comments:
		db.session.delete(Comment.query.get(comment.id))
	for sub_task in task.sub_task:
		db.session.delete(sub_task)
	db.session.delete(task)
	db.session.commit()

	return flask.redirect(flask.url_for("index", list_id = flask.request.args.get('list_id', type = int), task_id = flask.request.args.get('task_id', type = int)))


@app.route("/new_task", methods=["GET","POST"])
@is_logged
@user_allowed
def new_task():

	list_id = flask.request.args.get('list_id', default = User.query.get(flask.session['user_id']).task_lists[-1].id, type = int)

	if flask.request.method == "POST":

		if flask.request.form['time_input'] == '':
			time = None
		else:
			time = dt.strptime(flask.request.form['time_input'], "%Y-%m-%d %H:%M")

		if flask.request.form['parent_task'] == '':
			parent_task_id = flask.request.args.get('parent_id', default=None, type=int)
		else:
			parent_task_id = flask.request.form['parent_task']

		new_task = Task(user_id = flask.request.form['task_executor'], 
			title = flask.request.form['title'], 
			details = flask.request.form['details'], 
			task_list_id = flask.request.form['task_list_task'],
			date = time,
			parent_task_id = parent_task_id)
		db.session.add(new_task)
		db.session.flush()

		if not parent_task_id: #if task doesn't have a parent
			Task_list.query.get(list_id).add_to_order(new_task.id) #then add it to orderlist
			new_task.follow(flask.session['user_id'])
		else: #if task has a parent then mark it as unread for users
			new_task.follow(flask.session['user_id'])  

		db.session.commit()

		return flask.redirect(flask.url_for("index", list_id = list_id, task_id = new_task.id))
	else:
		
		return flask.render_template("new_task.html", 
			user = User.query.get(flask.session['user_id']), 
			task_list = Task_list.query.get(list_id))


@app.route("/edit_task", methods=["GET","POST"])
@is_logged
@user_allowed
def edit_task():

	list_id = flask.request.args.get('list_id', default = User.query.get(flask.session['user_id']).task_lists[-1].id, type = int)
	task_id = flask.request.args.get('parent_id', type = int)

	if flask.request.method == "POST":

		if flask.request.form['time_input'] == '':
			time = None
		else:
			time = dt.strptime(flask.request.form['time_input'], "%Y-%m-%d %H:%M")

		if flask.request.form['parent_task'] == '':
			parent_task_id = None
		else:
			parent_task_id = flask.request.form['parent_task']

		if flask.request.form['task_executor'] == '':
			task_executor = flask.session['user_id']
		else:
			task_executor = flask.request.form['task_executor']

		edit_task = Task.query.get(task_id)
		edit_task.user_id = task_executor
		edit_task.title = flask.request.form['title']
		edit_task.details = flask.request.form['details']
		edit_task.date = time
		edit_task.task_list_id = flask.request.form['task_list_task']
		edit_task.parent_task_id = parent_task_id
		db.session.commit()

		return flask.redirect(flask.url_for("index", list_id = list_id, task_id = edit_task.id))
	else:
		
		return flask.render_template("new_task.html", 
			user = User.query.get(flask.session['user_id']), 
			task_list = Task_list.query.get(list_id),
			edit = Task.query.get(task_id))


@app.route("/closed", methods=["GET", "POST"])
@is_logged
@user_allowed
def closed():

	list_id = flask.request.args.get('list_id', default = User.query.get(flask.session['user_id']).task_lists[-1].id, type = int)
	task_id = flask.request.args.get('task_id', default = None, type = int)

	if flask.request.method == "POST":
		task = Task.query.get(flask.request.args.get("target"))
		task.closed = False

		task.follow(flask.session['user_id'])  
		Task_list.query.get(list_id).add_to_order(task.id)

		db.session.commit()

		return flask.redirect(flask.url_for("index", list_id = list_id, task_id = task_id))
	else:
		if task_id:
			task = Task.query.get(task_id)
		else:
			task = None
	
		return flask.render_template("task.html", 
			task_list = Task_list.query.get(list_id),
			task = task,
			user = User.query.get(flask.session['user_id']))


@app.route("/new_list", methods=["POST"])
@is_logged
def new_list():
	task_list = Task_list(name = flask.request.form["new_task_name"])
	task_list.users.append(User.query.get(flask.session['user_id']))
	db.session.add(task_list)
	db.session.commit()

	return flask.redirect(flask.url_for("index", list_id = task_list.id))


@app.route("/edit_list", methods=["POST"])
@is_logged
@user_allowed
def edit_list():
	task_list = Task_list.query.get(flask.request.args.get('task_list_id', type = int))
	task_list.name = flask.request.form["edit_task_name"]
	db.session.commit()

	return flask.redirect(flask.url_for("index", list_id = task_list.id))

@app.route("/add_user", methods=["POST"])
@is_logged
@user_allowed
def add_user():
	user = User.query.filter_by(username = flask.request.form['username']).first()
	task_list = Task_list.query.get(flask.request.args.get('task_list_id', type = int))

	if user:
		if user in task_list.users:
			flask.flash("User is already in this task list")
		else:
			task_list.users.append(user)
			db.session.commit()
			flask.flash("User " + user.username + " successfully added!")
	else:
		flask.flash("User not found!")

	return flask.redirect(flask.url_for("index", list_id = task_list.id))

@app.route("/remove_user", methods=["GET"])
@is_logged
@user_allowed
def remove_user():
	user = User.query.get(flask.request.args.get('user', type = int))
	task_list = Task_list.query.get(flask.request.args.get('task_list_id', type = int))
	if len(task_list.users) == 1:
		flask.flash('Task list must have at least one user left')
	else:
		if user:
			if user in task_list.users:
				task_list.users.remove(user)
				db.session.commit()
				flask.flash("User " + user.username + " successfully deleted from " + task_list.name +"!")
			else:
				flask.flash("User " + user.username + " not found in this list!")
		else:
			flask.flash("User not found!")

	return flask.redirect(flask.url_for("index", list_id = task_list.id))


@app.route('/cal') #page with calendar
@is_logged
def calendar():
	return flask.render_template("cal.html", user = User.query.get(flask.session['user_id']))

@app.route('/data') #send JSON events to calendar
@is_logged
def return_data():
	json = []
	tasks = []
	for task_list in User.query.get(flask.session['user_id']).task_lists:
		for task in task_list.tasks:
			if not task.closed:
				tasks.append(task)
	for data in tasks:
		json.append({"id":str(data.id),"title":str(data.title),"url":"/?task_id="+str(data.id)+"&list_id=" + str(data.task_list_id),"start":str(data.date).replace(" ","T")})
	return flask.jsonify(json)

#run only if started standalone, not imported
if __name__ == "__main__":
	app.run(host=config.host, port=config.port)#, ssl_context='adhoc')
