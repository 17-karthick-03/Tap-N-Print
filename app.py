from flask import Flask, render_template, request, jsonify, session, redirect
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import timedelta
import os
import sqlite3
import uuid
import random
from werkzeug.utils import secure_filename
from PyPDF2 import PdfReader
from pdf2image import convert_from_path
import razorpay
from flask_mail import Mail, Message
from dotenv import load_dotenv
import datetime
import subprocess
import qrcode
import threading
import time
import base64
from io import BytesIO

load_dotenv()

app = Flask(__name__)

app.secret_key = "super_secret_key"
app.permanent_session_lifetime = timedelta(days=30)

UPLOAD_FOLDER = "uploads"
PREVIEW_FOLDER = "static/previews"
PROFILE_FOLDER = "static/profile_pics"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(PREVIEW_FOLDER, exist_ok=True)
os.makedirs(PROFILE_FOLDER, exist_ok=True)

# ---------- Razorpay ----------
razorpay_client = razorpay.Client(
    auth=(os.getenv("RAZORPAY_KEY_ID"), os.getenv("RAZORPAY_KEY_SECRET"))
)

# ---------- Mail ----------
app.config.update(
    MAIL_SERVER="smtp.gmail.com",
    MAIL_PORT=587,
    MAIL_USE_TLS=True,
    MAIL_USERNAME=os.getenv("MAIL_USERNAME"),
    MAIL_PASSWORD=os.getenv("MAIL_PASSWORD"),
)

mail = Mail(app)

# ---------- DATABASE ----------
def init_db():
    with sqlite3.connect("kiosk.db") as c:

        # USERS
        c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            email TEXT UNIQUE,
            password TEXT,
            photo TEXT
        )
        """)

        # JOBS
        c.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY,
            name TEXT,
            email TEXT,
            file TEXT,
            pages INTEGER,
            amount REAL,
            code TEXT,
            status TEXT,
            bw TEXT DEFAULT 'bw',
            copies INTEGER DEFAULT 1,
            mode TEXT DEFAULT 'normal'
        )
        """)

        # PAGE SETTINGS
        c.execute("""
        CREATE TABLE IF NOT EXISTS page_settings (
            job_id TEXT,
            page_number INTEGER,
            color_mode TEXT,
            PRIMARY KEY (job_id,page_number)
        )
        """)

def init_kiosk_done_db():
    with sqlite3.connect("kiosk_done.db") as c:
        c.execute("""
        CREATE TABLE IF NOT EXISTS printed_jobs (
            code TEXT PRIMARY KEY,
            printed_at TEXT
        )
        """)

init_db()
init_kiosk_done_db()

# ---------- AUTH ----------
@app.route("/signup", methods=["GET","POST"])
def signup():

    if request.method == "POST":

        name = request.form["name"]
        email = request.form["email"]
        password = generate_password_hash(request.form["password"])

        try:
            with sqlite3.connect("kiosk.db") as c:
                c.execute(
                    "INSERT INTO users (name,email,password) VALUES (?,?,?)",
                    (name,email,password)
                )

            return redirect("/login")

        except:
            return "Email already exists"

    return render_template("signup.html")

@app.route("/login", methods=["GET","POST"])
def login():

    error = None

    if request.method == "POST":

        email = request.form["email"]
        password = request.form["password"]

        with sqlite3.connect("kiosk.db") as c:
            user = c.execute(
                "SELECT password FROM users WHERE email=?",
                (email,)
            ).fetchone()

        if user and check_password_hash(user[0], password):
            session.permanent = True
            session["user_email"] = email
            return redirect("/")

        else:
            error = "Invalid email or password"

    return render_template("login.html", error=error)
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

# ---------- HOME ----------
@app.route("/")
def index():

    if "user_email" not in session:
        return redirect("/login")

    return render_template("index.html")

# ---------- PROFILE ----------
@app.route("/profile", methods=["GET","POST"])
def profile():

    if "user_email" not in session:
        return redirect("/login")

    email = session["user_email"]

    with sqlite3.connect("kiosk.db") as c:

        if request.method == "POST":

            if "name" in request.form:
                c.execute(
                    "UPDATE users SET name=? WHERE email=?",
                    (request.form["name"], email)
                )

            if request.form.get("new_password"):
                hashed = generate_password_hash(
                    request.form["new_password"]
                )

                c.execute(
                    "UPDATE users SET password=? WHERE email=?",
                    (hashed,email)
                )

            if "photo" in request.files:
                photo = request.files["photo"]

                if photo.filename != "":
                    filename = secure_filename(email + ".png")
                    path = os.path.join(PROFILE_FOLDER,filename)
                    photo.save(path)

                    c.execute(
                        "UPDATE users SET photo=? WHERE email=?",
                        (filename,email)
                    )

            c.commit()

        user = c.execute(
            "SELECT name,email,photo FROM users WHERE email=?",
            (email,)
        ).fetchone()

    return render_template(
        "profile.html",
        name=user[0],
        email=user[1],
        photo=user[2]
    )

# ---------- HISTORY ----------
@app.route("/history")
def history():

    if "user_email" not in session:
        return redirect("/login")

    email = session["user_email"]

    with sqlite3.connect("kiosk.db") as c:
        jobs = c.execute(
            "SELECT file,pages,amount,status FROM jobs WHERE email=? ORDER BY rowid DESC",
            (email,)
        ).fetchall()

    return render_template("history.html", jobs=jobs)

# ---------- DELETE ACCOUNT ----------
@app.route("/delete-account", methods=["POST"])
def delete_account():

    if "user_email" not in session:
        return redirect("/login")

    email = session["user_email"]

    with sqlite3.connect("kiosk.db") as c:
        c.execute("DELETE FROM users WHERE email=?", (email,))
        c.execute("DELETE FROM jobs WHERE email=?", (email,))
        c.commit()

    session.clear()
    return redirect("/signup")

# ---------- UPLOAD ----------
@app.route("/upload", methods=["POST"])
def upload():

    if "user_email" not in session:
        return jsonify({"error":"Login required"}),401

    email = session["user_email"]

    with sqlite3.connect("kiosk.db") as c:
        name = c.execute(
            "SELECT name FROM users WHERE email=?",
            (email,)
        ).fetchone()[0]

    f = request.files["pdf"]

    jid = str(uuid.uuid4())

    path = os.path.join(
        UPLOAD_FOLDER,
        jid + "_" + secure_filename(f.filename)
    )

    f.save(path)

    reader = PdfReader(path)
    total_pages = len(reader.pages)

    images = convert_from_path(path, dpi=100)

    image_urls = []

    for i,img in enumerate(images):

        img_name = f"{jid}_page_{i+1}.jpg"
        img_path = os.path.join(PREVIEW_FOLDER,img_name)

        img.save(img_path,"JPEG")

        image_urls.append("/static/previews/"+img_name)

    with sqlite3.connect("kiosk.db") as c:
        c.execute("""
        INSERT INTO jobs
        (id,name,email,file,pages,amount,code,status,bw,copies,mode)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """,(jid,name,email,path,total_pages,0,"","UPLOADED","bw",1,"normal"))

    return jsonify({
        "job_id":jid,
        "pages":total_pages,
        "images":image_urls
    })

# ---------- CREATE ORDER ----------
@app.route("/create-order", methods=["POST"])
def create_order():

    data = request.json
    amount = int(float(data["amount"]) * 100)

    order = razorpay_client.order.create(
        {"amount":amount,"currency":"INR","payment_capture":1}
    )

    return jsonify({
        "order_id":order["id"],
        "amount":order["amount"],
        "key":os.getenv("RAZORPAY_KEY_ID")
    })

# ---------- PAYMENT SUCCESS ----------
@app.route("/payment-success", methods=["POST"])
def payment_success():

    data = request.json
    job_id = data["job_id"]
    amount = data["amount"]
    bw = data.get("bw","bw")
    copies = data["copies"]
    mode = data.get("mode","normal")
    page_modes = data.get("pages",{})

    with sqlite3.connect("kiosk.db") as c:

        while True:
            code = str(random.randint(100000,999999))
            r = c.execute(
                "SELECT code FROM jobs WHERE code=?",
                (code,)
            ).fetchone()

            if not r:
                break

        c.execute("""
        UPDATE jobs
        SET code=?,amount=?,bw=?,copies=?,status='PAID',mode=?
        WHERE id=?
        """,(code,amount,bw,copies,mode,job_id))

        if mode == "custom":
            for page_number,color_mode in page_modes.items():

                c.execute("""
                INSERT OR REPLACE INTO page_settings
                (job_id,page_number,color_mode)
                VALUES (?,?,?)
                """,(job_id,int(page_number),color_mode))

        name,email,file_path = c.execute(
            "SELECT name,email,file FROM jobs WHERE id=?",
            (job_id,)
        ).fetchone()

    # QR
    qr = qrcode.QRCode(version=1,box_size=8,border=2)
    qr.add_data(code)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black",back_color="white")

    buffer = BytesIO()
    img.save(buffer,format="PNG")

    qr_base64 = base64.b64encode(buffer.getvalue()).decode()

    msg = Message(
        subject="Your Print Code – PrintOnTime",
        sender=os.getenv("MAIL_USERNAME"),
        recipients=[email]
    )

    msg.html = f"""
    <h2>PrintOnTime</h2>
    <p>Your print code:</p>
    <h1>{code}</h1>
    <img src="data:image/png;base64,{qr_base64}">
    """

    mail.send(msg)

    return jsonify({"code":code})

# ---------- KIOSK ----------
@app.route("/kiosk")
def kiosk():
    return render_template("kiosk.html")

@app.route("/kiosk/validate", methods=["POST"])
def kiosk_validate():

    code = request.json["code"]

    with sqlite3.connect("kiosk_done.db") as d:

        r = d.execute(
            "SELECT code FROM printed_jobs WHERE code=?",
            (code,)
        ).fetchone()

        if r:
            return jsonify({"status":"DONE"})

    with sqlite3.connect("kiosk.db") as c:

        row = c.execute("""
        SELECT name,file,bw,copies,mode
        FROM jobs
        WHERE code=? AND status='PAID'
        """,(code,)).fetchone()

        if not row:
            return jsonify({"status":"INVALID"})

    return jsonify({
        "status":"OK",
        "name":row[0],
        "file":row[1],
        "bw":row[2],
        "copies":row[3],
        "mode":row[4]
    })

@app.route("/kiosk/print", methods=["POST"])
def kiosk_print():

    code = request.json["code"]

    with sqlite3.connect("kiosk.db") as c:

        row = c.execute("""
        SELECT file,bw,copies
        FROM jobs
        WHERE code=? AND status='PAID'
        """,(code,)).fetchone()

    file_path,bw,copies = row

    print_file = file_path

    if bw == "bw":

        gray_path = file_path.replace(".pdf","_gray.pdf")

        subprocess.run([
            "gs",
            "-sDEVICE=pdfwrite",
            "-dColorConversionStrategy=/Gray",
            "-dProcessColorModel=/DeviceGray",
            "-dCompatibilityLevel=1.4",
            "-dNOPAUSE",
            "-dBATCH",
            "-sOutputFile="+gray_path,
            file_path
        ])

        print_file = gray_path

    subprocess.run(["lp",print_file,"-n",str(copies)])

    with sqlite3.connect("kiosk_done.db") as d:
        d.execute(
            "INSERT INTO printed_jobs VALUES (?,?)",
            (code,datetime.datetime.now().isoformat())
        )

    with sqlite3.connect("kiosk.db") as c:
        c.execute(
            "UPDATE jobs SET status='PRINTED' WHERE code=?",
            (code,)
        )

    return jsonify({"status":"PRINTED"})

if __name__ == "__main__":
    app.run(host="0.0.0.0",port=5000,debug=True)