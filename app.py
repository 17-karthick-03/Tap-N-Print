from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import timedelta
import os
import sqlite3
import uuid
import random
import datetime
import subprocess
import base64
from io import BytesIO
from werkzeug.utils import secure_filename
from PyPDF2 import PdfReader
from pdf2image import convert_from_path
import razorpay
from PyPDF2 import PdfReader, PdfWriter
from flask_mail import Mail, Message
from dotenv import load_dotenv
import qrcode
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle,
    Paragraph, Spacer, Image as RLImage, HRFlowable
)
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.enums import TA_CENTER, TA_RIGHT

load_dotenv()

app = Flask(__name__)
app.secret_key = "super_secret_key"
app.permanent_session_lifetime = timedelta(days=30)

UPLOAD_FOLDER  = "uploads"
PREVIEW_FOLDER = "static/previews"
PROFILE_FOLDER = "static/profile_pics"

os.makedirs(UPLOAD_FOLDER,  exist_ok=True)
os.makedirs(PREVIEW_FOLDER, exist_ok=True)
os.makedirs(PROFILE_FOLDER, exist_ok=True)

# ---------- Razorpay ----------
razorpay_client = razorpay.Client(
    auth=(os.getenv("RAZORPAY_KEY_ID"), os.getenv("RAZORPAY_KEY_SECRET"))
)

# ---------- Mail ----------
app.config.update(
    MAIL_SERVER   = "smtp.gmail.com",
    MAIL_PORT     = 587,
    MAIL_USE_TLS  = True,
    MAIL_USERNAME = os.getenv("MAIL_USERNAME"),
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD"),
)
mail = Mail(app)

OTP_EXPIRY_MINUTES = 10


# ═══════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════

def send_otp_email(email, otp, purpose="verify"):
    """Send a clean OTP email. purpose = 'verify' | 'reset'"""

    subject = "Your PrintOnTime OTP" if purpose == "verify" else "Reset Your PrintOnTime Password"
    action  = "verify your email address" if purpose == "verify" else "reset your password"

    msg = Message(subject=subject,
                  sender=os.getenv("MAIL_USERNAME"),
                  recipients=[email])

    msg.html = f"""
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f0f4f8;font-family:'Segoe UI',Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="padding:40px 0;background:#f0f4f8;">
    <tr><td align="center">
      <table width="480" cellpadding="0" cellspacing="0"
        style="background:#fff;border-radius:20px;overflow:hidden;
               box-shadow:0 4px 24px rgba(0,0,0,.1);max-width:480px;">

        <!-- header -->
        <tr>
          <td style="background:linear-gradient(135deg,#1a1a2e,#16213e);
                     padding:32px 40px;text-align:center;">
            <div style="font-size:24px;font-weight:800;color:#00f7ff;letter-spacing:2px;">
              PrintOnTime
            </div>
            <div style="font-size:11px;color:rgba(255,255,255,.4);
                        margin-top:5px;letter-spacing:2px;">SMART PRINT KIOSK</div>
          </td>
        </tr>

        <!-- body -->
        <tr>
          <td style="padding:32px 40px 0;">
            <p style="margin:0;font-size:20px;font-weight:700;color:#1a1a2e;">
              One-Time Password
            </p>
            <p style="margin:10px 0 24px;font-size:14px;color:#666;line-height:1.7;">
              Use the code below to {action}.<br>
              This code expires in <strong>{OTP_EXPIRY_MINUTES} minutes</strong>.
            </p>

            <!-- OTP box -->
            <div style="background:linear-gradient(135deg,#e8fffe,#e8f0ff);
                        border:2px solid #00c8d4;border-radius:16px;
                        padding:28px 20px;text-align:center;margin-bottom:24px;">
              <div style="font-size:11px;font-weight:700;letter-spacing:3px;
                           color:#00a0aa;text-transform:uppercase;margin-bottom:10px;">
                Your OTP
              </div>
              <div style="font-size:44px;font-weight:900;letter-spacing:14px;
                           color:#1a1a2e;font-family:'Courier New',monospace;">
                {otp}
              </div>
              <div style="font-size:12px;color:#999;margin-top:10px;">
                Do not share this code with anyone
              </div>
            </div>

            <p style="font-size:13px;color:#aaa;line-height:1.7;">
              If you did not request this, you can safely ignore this email.
            </p>
          </td>
        </tr>

        <!-- footer -->
        <tr>
          <td style="background:#f8fafc;padding:20px 40px;
                     border-radius:0 0 20px 20px;text-align:center;">
            <p style="margin:0;font-size:12px;color:#aaa;line-height:1.8;">
              Automated email from <strong style="color:#555;">PrintOnTime</strong>.
              Do not reply.
            </p>
          </td>
        </tr>

      </table>
    </td></tr>
  </table>
</body>
</html>
"""
    mail.send(msg)


def store_otp(email, purpose):
    """Generate, store and return a fresh OTP."""
    otp = str(random.randint(100000, 999999))
    expires_at = (
        datetime.datetime.now() + datetime.timedelta(minutes=OTP_EXPIRY_MINUTES)
    ).isoformat()

    with sqlite3.connect("kiosk.db") as c:
        c.execute("DELETE FROM otps WHERE email=? AND purpose=?", (email, purpose))
        c.execute(
            "INSERT INTO otps (email, otp, purpose, expires_at) VALUES (?,?,?,?)",
            (email, otp, purpose, expires_at)
        )
    return otp


def verify_otp(email, otp_input, purpose):
    """
    Returns: 'ok' | 'invalid' | 'expired'
    Deletes the OTP row on success.
    """
    with sqlite3.connect("kiosk.db") as c:
        row = c.execute(
            "SELECT otp, expires_at FROM otps WHERE email=? AND purpose=?",
            (email, purpose)
        ).fetchone()

        if not row:
            return "invalid"

        stored_otp, expires_at = row

        if datetime.datetime.now() > datetime.datetime.fromisoformat(expires_at):
            c.execute("DELETE FROM otps WHERE email=? AND purpose=?", (email, purpose))
            return "expired"

        if otp_input.strip() != stored_otp:
            return "invalid"

        c.execute("DELETE FROM otps WHERE email=? AND purpose=?", (email, purpose))
        return "ok"


# ═══════════════════════════════════════════════
#  PDF RECEIPT GENERATOR
# ═══════════════════════════════════════════════

def generate_receipt_pdf(name, code, file_name, total_pages, pages_label,
                         mode_label, copies, amount, paid_at, qr_base64):
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        rightMargin=20*mm, leftMargin=20*mm,
        topMargin=20*mm,  bottomMargin=20*mm
    )

    dark     = colors.HexColor("#1a1a2e")
    teal     = colors.HexColor("#00a0aa")
    light_bg = colors.HexColor("#f0f4f8")
    grey     = colors.HexColor("#888888")
    white    = colors.white

    title_style      = ParagraphStyle("rcp_title",      fontSize=24, fontName="Helvetica-Bold", textColor=teal,  alignment=TA_CENTER, spaceAfter=16)
    sub_style        = ParagraphStyle("rcp_sub",        fontSize=9,  fontName="Helvetica",      textColor=grey,  alignment=TA_CENTER, spaceAfter=6)
    greet_style      = ParagraphStyle("rcp_greet",      fontSize=13, fontName="Helvetica-Bold", textColor=dark,  spaceAfter=4)
    body_style       = ParagraphStyle("rcp_body",       fontSize=10, fontName="Helvetica",      textColor=grey,  spaceAfter=14)
    label_style      = ParagraphStyle("rcp_label",      fontSize=10, fontName="Helvetica",      textColor=grey)
    value_style      = ParagraphStyle("rcp_value",      fontSize=10, fontName="Helvetica-Bold", textColor=dark,  alignment=TA_RIGHT)
    amt_label_style  = ParagraphStyle("rcp_amt_label",  fontSize=13, fontName="Helvetica-Bold", textColor=dark)
    amt_val_style    = ParagraphStyle("rcp_amt_val",    fontSize=16, fontName="Helvetica-Bold", textColor=teal,  alignment=TA_RIGHT)
    code_label_style = ParagraphStyle("rcp_code_label", fontSize=10, fontName="Helvetica",      textColor=grey,  alignment=TA_CENTER, spaceAfter=6)
    code_val_style   = ParagraphStyle("rcp_code_val",   fontSize=32, fontName="Helvetica-Bold", textColor=dark,  alignment=TA_CENTER, spaceAfter=19)
    hint_style       = ParagraphStyle("rcp_hint",       fontSize=9,  fontName="Helvetica",      textColor=grey,  alignment=TA_CENTER)
    footer_style     = ParagraphStyle("rcp_footer",     fontSize=8,  fontName="Helvetica",      textColor=grey,  alignment=TA_CENTER)

    qr_image = RLImage(BytesIO(base64.b64decode(qr_base64)), width=60*mm, height=60*mm)

    rows = [
        [Paragraph("File",           label_style), Paragraph(file_name,        value_style)],
        [Paragraph("Total Pages",    label_style), Paragraph(str(total_pages), value_style)],
        [Paragraph("Pages Printed",  label_style), Paragraph(pages_label,      value_style)],
        [Paragraph("Print Mode",     label_style), Paragraph(mode_label,       value_style)],
        [Paragraph("Copies",         label_style), Paragraph(str(copies),      value_style)],
        [Paragraph("Date & Time",    label_style), Paragraph(paid_at,          value_style)],
        [Paragraph("<b>Amount Paid</b>", amt_label_style), Paragraph(f"<b>Rs {amount}</b>", amt_val_style)],
    ]

    table = Table(rows, colWidths=[85*mm, 85*mm])
    table.setStyle(TableStyle([
        ("ROWBACKGROUNDS", (0,0),  (-1,-2), [white, light_bg]),
        ("BACKGROUND",     (0,-1), (-1,-1), colors.HexColor("#e8fffe")),
        ("LINEBELOW",      (0,0),  (-1,-2), 0.5, colors.HexColor("#e0e0e0")),
        ("LINEABOVE",      (0,-1), (-1,-1), 1.2, teal),
        ("TOPPADDING",     (0,0),  (-1,-1), 9),
        ("BOTTOMPADDING",  (0,0),  (-1,-1), 9),
        ("LEFTPADDING",    (0,0),  (-1,-1), 10),
        ("RIGHTPADDING",   (0,0),  (-1,-1), 10),
        ("VALIGN",         (0,0),  (-1,-1), "MIDDLE"),
        ("WORDWRAP",       (0,0),  (-1,-1), "CJK"),
    ]))

    usable_width = 170 * mm
    qr_table = Table([[qr_image]], colWidths=[usable_width])
    qr_table.setStyle(TableStyle([
        ("ALIGN",         (0,0), (-1,-1), "CENTER"),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
        ("TOPPADDING",    (0,0), (-1,-1), 8),
        ("BOTTOMPADDING", (0,0), (-1,-1), 8),
    ]))

    spaced_code = "  ".join(list(code))

    elements = [
        Paragraph("PrintOnTime", title_style),
        Paragraph("SMART PRINT KIOSK — RECEIPT", sub_style),
        HRFlowable(width="100%", thickness=1.5, color=teal, spaceAfter=14),
        Paragraph(f"Hi {name},", greet_style),
        Paragraph("Your print job is confirmed. Here are your details:", body_style),
        table,
        Spacer(1, 8*mm),
        HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#dddddd"), spaceAfter=12),
        Paragraph("YOUR PRINT CODE", code_label_style),
        Paragraph(f"<b>{spaced_code}</b>", code_val_style),
        Spacer(1, 10*mm),
        Paragraph("Scan the QR code at the kiosk to collect your printout", hint_style),
        Spacer(1, 5*mm),
        qr_table,
        Spacer(1, 18*mm),
        HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#dddddd"), spaceAfter=8),
        Paragraph("Auto-generated by PrintOnTime. Do not reply to this email.", footer_style),
    ]

    doc.build(elements)
    buffer.seek(0)
    return buffer


# ═══════════════════════════════════════════════
#  DATABASE
# ═══════════════════════════════════════════════

def init_db():
    with sqlite3.connect("kiosk.db") as c:

        c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT,
            email      TEXT UNIQUE,
            password   TEXT,
            photo      TEXT,
            is_verified INTEGER DEFAULT 0
        )""")

        try:
            c.execute("ALTER TABLE users ADD COLUMN is_verified INTEGER DEFAULT 0")
        except Exception:
            pass

        c.execute("""
        CREATE TABLE IF NOT EXISTS otps (
            email      TEXT,
            otp        TEXT,
            purpose    TEXT,
            expires_at TEXT,
            PRIMARY KEY (email, purpose)
        )""")

        c.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id         TEXT PRIMARY KEY,
            name       TEXT,
            email      TEXT,
            file       TEXT,
            pages      INTEGER,
            amount     REAL,
            code       TEXT,
            status     TEXT,
            bw         TEXT    DEFAULT 'bw',
            copies     INTEGER DEFAULT 1,
            mode       TEXT    DEFAULT 'normal',
            start_page INTEGER,
            end_page   INTEGER
        )""")

        for col in ("start_page INTEGER", "end_page INTEGER", "page_type TEXT DEFAULT 'all'"):
            try:
                c.execute(f"ALTER TABLE jobs ADD COLUMN {col}")
            except Exception:
                pass

        c.execute("""
        CREATE TABLE IF NOT EXISTS page_settings (
            job_id       TEXT,
            page_number  INTEGER,
            color_mode   TEXT,
            PRIMARY KEY (job_id, page_number)
        )""")


def init_kiosk_done_db():
    with sqlite3.connect("kiosk_done.db") as c:
        c.execute("""
        CREATE TABLE IF NOT EXISTS printed_jobs (
            code       TEXT PRIMARY KEY,
            printed_at TEXT
        )""")


init_db()
init_kiosk_done_db()


# ═══════════════════════════════════════════════
#  AUTH — SIGNUP
# ═══════════════════════════════════════════════

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        name     = request.form["name"]
        email    = request.form["email"]
        password = generate_password_hash(request.form["password"])

        with sqlite3.connect("kiosk.db") as c:
            existing = c.execute(
                "SELECT id FROM users WHERE email=?", (email,)
            ).fetchone()

        if existing:
            return render_template("signup.html", error="Email already registered.")

        with sqlite3.connect("kiosk.db") as c:
            c.execute(
                "INSERT INTO users (name,email,password,is_verified) VALUES (?,?,?,0)",
                (name, email, password)
            )

        otp = store_otp(email, "verify")
        send_otp_email(email, otp, purpose="verify")

        session["pending_verify_email"] = email
        return redirect("/verify-otp")

    return render_template("signup.html")


@app.route("/verify-otp", methods=["GET", "POST"])
def verify_otp_page():
    email = session.get("pending_verify_email")
    if not email:
        return redirect("/signup")

    error   = None
    success = None

    if request.method == "POST":
        action = request.form.get("action", "verify")

        if action == "resend":
            otp = store_otp(email, "verify")
            send_otp_email(email, otp, purpose="verify")
            success = "A new OTP has been sent to your email."

        else:
            result = verify_otp(email, request.form["otp"], "verify")

            if result == "ok":
                with sqlite3.connect("kiosk.db") as c:
                    c.execute(
                        "UPDATE users SET is_verified=1 WHERE email=?", (email,)
                    )
                session.pop("pending_verify_email", None)
                session["verified_redirect"] = True
                return redirect("/login")

            elif result == "expired":
                error = "OTP expired. Please request a new one."
            else:
                error = "Invalid OTP. Please try again."

    return render_template("verify_otp.html", email=email, error=error, success=success)


# ═══════════════════════════════════════════════
#  AUTH — LOGIN
# ═══════════════════════════════════════════════

@app.route("/login", methods=["GET", "POST"])
def login():
    error           = None
    verified_msg    = session.pop("verified_redirect", None)
    reset_msg       = session.pop("reset_redirect", None)

    if request.method == "POST":
        email    = request.form["email"]
        password = request.form["password"]

        with sqlite3.connect("kiosk.db") as c:
            user = c.execute(
                "SELECT password, is_verified FROM users WHERE email=?", (email,)
            ).fetchone()

        if not user or not check_password_hash(user[0], password):
            error = "Invalid email or password."

        elif not user[1]:
            otp = store_otp(email, "verify")
            send_otp_email(email, otp, purpose="verify")
            session["pending_verify_email"] = email
            return redirect("/verify-otp")

        else:
            session.permanent     = True
            session["user_email"] = email
            return redirect("/")

    return render_template(
        "login.html",
        error=error,
        verified_msg=verified_msg,
        reset_msg=reset_msg
    )


# ═══════════════════════════════════════════════
#  AUTH — FORGOT PASSWORD
# ═══════════════════════════════════════════════

@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    error   = None
    success = None

    if request.method == "POST":
        email = request.form["email"].strip()

        with sqlite3.connect("kiosk.db") as c:
            user = c.execute(
                "SELECT id FROM users WHERE email=?", (email,)
            ).fetchone()

        if not user:
            error = "No account found with that email."
        else:
            otp = store_otp(email, "reset")
            send_otp_email(email, otp, purpose="reset")
            session["pending_reset_email"] = email
            return redirect("/reset-otp")

    return render_template("forgot_password.html", error=error, success=success)


@app.route("/reset-otp", methods=["GET", "POST"])
def reset_otp_page():
    email = session.get("pending_reset_email")
    if not email:
        return redirect("/forgot-password")

    error   = None
    success = None

    if request.method == "POST":
        action = request.form.get("action", "verify")

        if action == "resend":
            otp = store_otp(email, "reset")
            send_otp_email(email, otp, purpose="reset")
            success = "A new OTP has been sent to your email."

        else:
            result = verify_otp(email, request.form["otp"], "reset")

            if result == "ok":
                session.pop("pending_reset_email", None)
                session["user_email"]    = email
                session["reset_redirect"] = True
                session.permanent         = True
                return redirect("/profile")

            elif result == "expired":
                error = "OTP expired. Please request a new one."
            else:
                error = "Invalid OTP. Please try again."

    return render_template("verify_otp.html",
                           email=email, error=error, success=success,
                           purpose="reset")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


# ═══════════════════════════════════════════════
#  HOME
# ═══════════════════════════════════════════════

@app.route("/")
def index():
    if "user_email" not in session:
        return redirect("/login")

    with sqlite3.connect("kiosk.db") as c:
        user = c.execute(
            "SELECT photo FROM users WHERE email=?", (session["user_email"],)
        ).fetchone()

    return render_template("index.html", photo=user[0] if user else None)


# ═══════════════════════════════════════════════
#  PROFILE
# ═══════════════════════════════════════════════

@app.route("/profile", methods=["GET", "POST"])
def profile():
    if "user_email" not in session:
        return redirect("/login")

    email      = session["user_email"]
    reset_popup = session.pop("reset_redirect", None)

    with sqlite3.connect("kiosk.db") as c:

        if request.method == "POST":

            if "name" in request.form:
                c.execute("UPDATE users SET name=? WHERE email=?",
                          (request.form["name"], email))

            if request.form.get("new_password"):
                c.execute("UPDATE users SET password=? WHERE email=?",
                          (generate_password_hash(request.form["new_password"]), email))

            if "photo" in request.files:
                photo = request.files["photo"]
                if photo.filename:
                    fname = secure_filename(email + ".png")
                    photo.save(os.path.join(PROFILE_FOLDER, fname))
                    c.execute("UPDATE users SET photo=? WHERE email=?", (fname, email))

            c.commit()

        user = c.execute(
            "SELECT name,email,photo FROM users WHERE email=?", (email,)
        ).fetchone()

    return render_template("profile.html",
                           name=user[0], email=user[1], photo=user[2],
                           reset_popup=reset_popup)


# ═══════════════════════════════════════════════
#  HISTORY
# ═══════════════════════════════════════════════

@app.route("/history")
def history():
    if "user_email" not in session:
        return redirect("/login")

    with sqlite3.connect("kiosk.db") as c:
        jobs = c.execute(
            "SELECT file,pages,amount,status,code FROM jobs WHERE email=? ORDER BY rowid DESC",
            (session["user_email"],)
        ).fetchall()

    return render_template("history.html", jobs=jobs)


# ═══════════════════════════════════════════════
#  DELETE ACCOUNT
# ═══════════════════════════════════════════════

@app.route("/delete-account", methods=["POST"])
def delete_account():
    if "user_email" not in session:
        return redirect("/login")

    email = session["user_email"]

    with sqlite3.connect("kiosk.db") as c:
        c.execute("DELETE FROM users WHERE email=?", (email,))
        c.execute("DELETE FROM jobs  WHERE email=?", (email,))
        c.execute("DELETE FROM otps  WHERE email=?", (email,))
        c.commit()

    session.clear()
    return redirect("/signup")


# ═══════════════════════════════════════════════
#  UPLOAD
# ═══════════════════════════════════════════════

ALLOWED_EXTENSIONS = {
    "pdf":  "pdf",
    "jpg":  "image", "jpeg": "image", "png": "image", "webp": "image"
}

IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}


def convert_to_pdf(src_path, jid, ext):
    """
    Convert any supported file to a PDF saved in UPLOAD_FOLDER.
    Returns the path to the resulting PDF.
    """
    from PIL import Image as PILImage

    pdf_path = os.path.join(UPLOAD_FOLDER, jid + "_converted.pdf")

    if ext in ("jpg", "jpeg", "png", "webp"):
        img = PILImage.open(src_path).convert("RGB")
        img.save(pdf_path, "PDF", resolution=150)

    elif ext in ("doc", "docx"):
        subprocess.run([
            "libreoffice", "--headless", "--convert-to", "pdf",
            "--outdir", UPLOAD_FOLDER, src_path
        ], check=True)
        base = os.path.splitext(os.path.basename(src_path))[0]
        lo_out = os.path.join(UPLOAD_FOLDER, base + ".pdf")
        os.rename(lo_out, pdf_path)

    return pdf_path


def merge_images_to_pdf(image_paths, output_path):
    """
    Merge multiple images into a single PDF (one image per page).
    """
    from PIL import Image as PILImage

    pil_images = []
    for path in image_paths:
        img = PILImage.open(path).convert("RGB")
        pil_images.append(img)

    if not pil_images:
        raise ValueError("No images to merge")

    # Save all images as a multi-page PDF
    first = pil_images[0]
    rest  = pil_images[1:]
    first.save(output_path, "PDF", resolution=150, save_all=True, append_images=rest)


@app.route("/upload", methods=["POST"])
def upload():
    if "user_email" not in session:
        return jsonify({"error": "Login required"}), 401

    email = session["user_email"]

    with sqlite3.connect("kiosk.db") as c:
        name = c.execute(
            "SELECT name FROM users WHERE email=?", (email,)
        ).fetchone()[0]

    files = request.files.getlist("file")
    if not files or all(f.filename == "" for f in files):
        return jsonify({"error": "No file selected"}), 400

    jid = str(uuid.uuid4())

    # ── Determine upload type ──────────────────────────────────────────────
    # Get extensions of all uploaded files
    exts = []
    for f in files:
        fname = secure_filename(f.filename)
        ext   = fname.rsplit(".", 1)[-1].lower() if "." in fname else ""
        exts.append(ext)

    # Validate all extensions
    for ext in exts:
        if ext not in ALLOWED_EXTENSIONS:
            return jsonify({"error": f"Unsupported file type: .{ext}"}), 400

    # If any file is a PDF, only allow a single file
    has_pdf = any(e == "pdf" for e in exts)
    if has_pdf and len(files) > 1:
        return jsonify({"error": "Only one PDF can be uploaded at a time. For multiple pages, upload images instead."}), 400

    # ── Single PDF ─────────────────────────────────────────────────────────
    if has_pdf:
        f    = files[0]
        ext  = exts[0]
        orig_filename = secure_filename(f.filename)
        orig_path     = os.path.join(UPLOAD_FOLDER, jid + "_" + orig_filename)
        f.save(orig_path)
        pdf_path = orig_path

    # ── One or more images → merge into PDF ────────────────────────────────
    else:
        saved_paths = []
        for i, f in enumerate(files):
            orig_filename = secure_filename(f.filename)
            save_path     = os.path.join(UPLOAD_FOLDER, f"{jid}_img{i}_{orig_filename}")
            f.save(save_path)
            saved_paths.append(save_path)

        pdf_path = os.path.join(UPLOAD_FOLDER, jid + "_merged.pdf")
        try:
            merge_images_to_pdf(saved_paths, pdf_path)
        except Exception as e:
            return jsonify({"error": f"Image merge failed: {str(e)}"}), 500

        # Use the first filename as display name (or "images" if multiple)
        if len(saved_paths) == 1:
            orig_filename = secure_filename(files[0].filename)
        else:
            orig_filename = f"{len(files)}_images_merged.pdf"

    # ── Count pages & generate colour previews ─────────────────────────────
    reader      = PdfReader(pdf_path)
    total_pages = len(reader.pages)
    images      = convert_from_path(pdf_path, dpi=100)
    image_urls  = []

    for i, img in enumerate(images):
        img_name = f"{jid}_page_{i+1}.jpg"
        img.save(os.path.join(PREVIEW_FOLDER, img_name), "JPEG")
        image_urls.append("/static/previews/" + img_name)

    # ── Generate grayscale previews ────────────────────────────────────────
    gray_image_urls = []
    for i, img in enumerate(images):
        gray_img  = img.convert("L").convert("RGB")   # grayscale via Pillow
        gray_name = f"{jid}_page_{i+1}_gray.jpg"
        gray_img.save(os.path.join(PREVIEW_FOLDER, gray_name), "JPEG")
        gray_image_urls.append("/static/previews/" + gray_name)

    # ── Store job ──────────────────────────────────────────────────────────
    with sqlite3.connect("kiosk.db") as c:
        c.execute("""
        INSERT INTO jobs (id,name,email,file,pages,amount,code,status,bw,copies,mode)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, (jid, name, email, pdf_path, total_pages, 0, "", "UPLOADED", "bw", 1, "normal"))

    return jsonify({
        "job_id":       jid,
        "pages":        total_pages,
        "images":       image_urls,       # colour previews
        "gray_images":  gray_image_urls,  # grayscale previews (pre-rendered)
    })


# ═══════════════════════════════════════════════
#  CREATE ORDER
# ═══════════════════════════════════════════════

@app.route("/create-order", methods=["POST"])
def create_order():
    amount = int(float(request.json["amount"]) * 100)
    order  = razorpay_client.order.create(
        {"amount": amount, "currency": "INR", "payment_capture": 1}
    )
    return jsonify({"order_id": order["id"], "amount": order["amount"],
                    "key": os.getenv("RAZORPAY_KEY_ID")})


# ═══════════════════════════════════════════════
#  PAYMENT SUCCESS
# ═══════════════════════════════════════════════

@app.route("/payment-success", methods=["POST"])
def payment_success():
    data       = request.json
    job_id     = data["job_id"]
    amount     = data["amount"]
    bw         = data.get("bw", "bw")
    copies     = data["copies"]
    mode       = data.get("mode", "normal")
    page_modes = data.get("pages", {})
    page_type = data.get("page_type", "all")
    start_page = data.get("start_page")
    end_page   = data.get("end_page")

    with sqlite3.connect("kiosk.db") as c:

        while True:
            code = str(random.randint(100000, 999999))
            if not c.execute("SELECT code FROM jobs WHERE code=?", (code,)).fetchone():
                break

        c.execute("""
            UPDATE jobs
            SET code=?,amount=?,bw=?,copies=?,status='PAID',
                mode=?,start_page=?,end_page=?,page_type=?
            WHERE id=?
        """, (code, amount, bw, copies, mode, start_page, end_page, page_type, job_id))

        if mode == "custom":
            for pn, cm in page_modes.items():
                c.execute("""
                    INSERT OR REPLACE INTO page_settings (job_id,page_number,color_mode)
                    VALUES (?,?,?)
                """, (job_id, int(pn), cm))

        name, email, file_path, total_pages = c.execute(
            "SELECT name,email,file,pages FROM jobs WHERE id=?", (job_id,)
        ).fetchone()

    file_name   = os.path.basename(file_path).split("_", 1)[-1]
    mode_label  = "B&W" if bw == "bw" else "Colour"
    pages_label = f"{start_page} - {end_page}" if start_page and end_page else "All"
    paid_at     = datetime.datetime.now().strftime("%d %b %Y, %I:%M %p")

    # QR
    qr = qrcode.QRCode(version=1, box_size=8, border=2)
    qr.add_data(code)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="#1a1a2e", back_color="white")
    qr_buf = BytesIO()
    qr_img.save(qr_buf, format="PNG")
    qr_base64 = base64.b64encode(qr_buf.getvalue()).decode()

    # PDF receipt
    pdf_buffer = generate_receipt_pdf(
        name=name, code=code, file_name=file_name,
        total_pages=total_pages, pages_label=pages_label,
        mode_label=mode_label, copies=copies,
        amount=amount, paid_at=paid_at, qr_base64=qr_base64
    )

    # Email
    msg = Message(
        subject="Your Print Code & Receipt - PrintOnTime",
        sender=os.getenv("MAIL_USERNAME"),
        recipients=[email]
    )
    msg.html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Your Print Receipt</title>
</head>
<body style="margin:0;padding:0;background-color:#f0f4f8;font-family:'Segoe UI',Arial,sans-serif;">

  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
         style="background-color:#f0f4f8;padding:40px 0;">
    <tr>
      <td align="center" style="padding:0 16px;">

        <table role="presentation" width="560" cellpadding="0" cellspacing="0" border="0"
               style="max-width:560px;width:100%;background-color:#ffffff;
                      border-radius:20px;overflow:hidden;
                      box-shadow:0 4px 24px rgba(0,0,0,0.10);">

          <tr>
            <td align="center"
                style="background:linear-gradient(135deg,#1a1a2e,#16213e);
                       padding:32px 40px;">
              <div style="font-size:26px;font-weight:800;color:#00f7ff;
                           letter-spacing:2px;line-height:1.2;">PrintOnTime</div>
              <div style="font-size:11px;color:rgba(255,255,255,0.4);
                           margin-top:6px;letter-spacing:2px;">SMART PRINT KIOSK</div>
            </td>
          </tr>

          <tr>
            <td style="padding:32px 40px 20px;">
              <p style="margin:0 0 8px;font-size:20px;font-weight:700;
                         color:#1a1a2e;line-height:1.3;">Hi {name},</p>
              <p style="margin:0;font-size:14px;color:#666666;line-height:1.7;">
                Your print job is confirmed and payment received successfully.<br>
                Use the code below at the kiosk to collect your printout.
              </p>
            </td>
          </tr>

          <tr>
            <td style="padding:0 40px 20px;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
                     style="background:linear-gradient(135deg,#e8fffe,#e8f0ff);
                            border:2px solid #00c8d4;border-radius:16px;">
                <tr>
                  <td align="center" style="padding:28px 20px;">
                    <div style="font-size:11px;font-weight:700;letter-spacing:3px;
                                 color:#00a0aa;text-transform:uppercase;margin-bottom:12px;">
                      Your Print Code
                    </div>
                    <div style="font-size:44px;font-weight:900;letter-spacing:12px;
                                 color:#1a1a2e;font-family:'Courier New',Courier,monospace;
                                 line-height:1.1;">
                      {code}
                    </div>
                    <div style="font-size:12px;color:#999999;margin-top:10px;">
                      Valid for one-time use only
                    </div>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <tr>
            <td align="center" style="padding:0 40px 28px;">
              <p style="margin:0 0 14px;font-size:12px;color:#aaaaaa;
                         letter-spacing:1.5px;text-transform:uppercase;">
                Or scan at the kiosk
              </p>
              <img src="cid:qrcode"
                   width="150" height="150" alt="QR Code"
                   style="display:block;margin:0 auto;border-radius:12px;
                          border:3px solid #e0e0e0;">
            </td>
          </tr>

          <tr>
            <td style="padding:0 40px;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
                <tr><td style="border-top:1px solid #eeeeee;font-size:0;">&nbsp;</td></tr>
              </table>
            </td>
          </tr>

          <tr>
            <td style="padding:24px 40px 12px;">
              <div style="font-size:11px;font-weight:700;letter-spacing:2.5px;
                           color:#aaaaaa;text-transform:uppercase;">
                Receipt
              </div>
            </td>
          </tr>

          <tr>
            <td style="padding:0 40px;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
                     style="font-size:14px;border-collapse:collapse;">

                <tr style="background-color:#ffffff;">
                  <td style="padding:11px 0;color:#888888;border-bottom:1px solid #f5f5f5;width:50%;">File</td>
                  <td style="padding:11px 0;color:#1a1a2e;font-weight:600;text-align:right;border-bottom:1px solid #f5f5f5;word-break:break-all;">{file_name}</td>
                </tr>

                <tr style="background-color:#f8fafc;">
                  <td style="padding:11px 0;color:#888888;border-bottom:1px solid #f5f5f5;">Total Pages</td>
                  <td style="padding:11px 0;color:#1a1a2e;font-weight:600;text-align:right;border-bottom:1px solid #f5f5f5;">{total_pages}</td>
                </tr>

                <tr style="background-color:#ffffff;">
                  <td style="padding:11px 0;color:#888888;border-bottom:1px solid #f5f5f5;">Pages Printed</td>
                  <td style="padding:11px 0;color:#1a1a2e;font-weight:600;text-align:right;border-bottom:1px solid #f5f5f5;">{pages_label}</td>
                </tr>

                <tr style="background-color:#f8fafc;">
                  <td style="padding:11px 0;color:#888888;border-bottom:1px solid #f5f5f5;">Print Mode</td>
                  <td style="padding:11px 0;color:#1a1a2e;font-weight:600;text-align:right;border-bottom:1px solid #f5f5f5;">{mode_label}</td>
                </tr>

                <tr style="background-color:#ffffff;">
                  <td style="padding:11px 0;color:#888888;border-bottom:1px solid #f5f5f5;">Copies</td>
                  <td style="padding:11px 0;color:#1a1a2e;font-weight:600;text-align:right;border-bottom:1px solid #f5f5f5;">{copies}</td>
                </tr>

                <tr style="background-color:#f8fafc;">
                  <td style="padding:11px 0;color:#888888;border-bottom:1px solid #e0e0e0;">Date &amp; Time</td>
                  <td style="padding:11px 0;color:#1a1a2e;font-weight:600;text-align:right;border-bottom:1px solid #e0e0e0;">{paid_at}</td>
                </tr>

                <tr style="background-color:#e8fffe;">
                  <td style="padding:16px 0 12px;font-size:15px;font-weight:700;color:#1a1a2e;">Amount Paid</td>
                  <td style="padding:16px 0 12px;font-size:22px;font-weight:900;color:#00a0aa;text-align:right;">Rs {amount}</td>
                </tr>

              </table>
            </td>
          </tr>

          <tr>
            <td style="padding:16px 40px 24px;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
                     style="background-color:#f0f4f8;border-radius:10px;">
                <tr>
                  <td style="padding:12px 16px;font-size:13px;color:#666666;">
                    &#128206; A PDF copy of this receipt is attached to this email.
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <tr>
            <td align="center"
                style="background-color:#f8fafc;padding:20px 40px;border-top:1px solid #eeeeee;">
              <p style="margin:0;font-size:12px;color:#aaaaaa;line-height:1.8;">
                This is an automated email from
                <strong style="color:#555555;">PrintOnTime</strong>.<br>
                Please do not reply to this email.
              </p>
            </td>
          </tr>

        </table>

      </td>
    </tr>
  </table>

</body>
</html>"""

    # Attach PDF receipt
    msg.attach(
        filename=f"PrintOnTime_Receipt_{code}.pdf",
        content_type="application/pdf",
        data=pdf_buffer.read()
    )

    # Attach QR as inline CID image (fixes Gmail blocking base64 data URIs)
    qr_bytes = base64.b64decode(qr_base64)
    msg.attach(
        filename="qr.png",
        content_type="image/png",
        data=qr_bytes,
        disposition="inline",
        headers={"Content-ID": "<qrcode>", "X-Attachment-Id": "qrcode"}
    )

    mail.send(msg)

    return jsonify({"code": code, "qr": qr_base64})


# ═══════════════════════════════════════════════
#  KIOSK
# ═══════════════════════════════════════════════

@app.route("/kiosk")
def kiosk():
    return render_template("kiosk.html")


@app.route("/kiosk/validate", methods=["POST"])
def kiosk_validate():
    code = request.json["code"]

    with sqlite3.connect("kiosk_done.db") as d:
        if d.execute("SELECT code FROM printed_jobs WHERE code=?", (code,)).fetchone():
            return jsonify({"status": "DONE"})

    with sqlite3.connect("kiosk.db") as c:
        row = c.execute("""
            SELECT name,file,bw,copies,mode FROM jobs
            WHERE code=? AND status='PAID'
        """, (code,)).fetchone()

    if not row:
        return jsonify({"status": "INVALID"})

    return jsonify({"status":"OK","name":row[0],"file":row[1],
                    "bw":row[2],"copies":row[3],"mode":row[4]})

def filter_pages(file_path, page_type, start_page=None, end_page=None):
    reader = PdfReader(file_path)
    writer = PdfWriter()

    for i, page in enumerate(reader.pages):
        page_no = i + 1

        # ✅ RANGE mode
        if page_type == "range":
            if start_page and end_page:
                if page_no < start_page or page_no > end_page:
                    continue

        # ✅ ODD / EVEN mode (IGNORE RANGE)
        elif page_type == "odd":
            if page_no % 2 == 0:
                continue

        elif page_type == "even":
            if page_no % 2 != 0:
                continue

        # ✅ ALL
        # no filtering

        writer.add_page(page)

    output_path = file_path.replace(".pdf", "_filtered.pdf")

    with open(output_path, "wb") as f:
        writer.write(f)

    return output_path

@app.route("/kiosk/print", methods=["POST"])
def kiosk_print():
    code = request.json["code"]

    with sqlite3.connect("kiosk.db") as c:
        row = c.execute("""
            SELECT file,bw,copies,start_page,end_page,page_type,name,email FROM jobs
            WHERE code=? AND status='PAID'
        """, (code,)).fetchone()

    file_path, bw, copies, start_page, end_page, page_type, user_name, user_email = row
    print_file = file_path
    if page_type in ["odd", "even"]:
        print_file = filter_pages(print_file, page_type, start_page, end_page)

    if bw == "bw":
        gray_path = print_file.replace(".pdf", "_gray.pdf")
        subprocess.run([
            "gs","-sDEVICE=pdfwrite","-dColorConversionStrategy=/Gray",
            "-dProcessColorModel=/DeviceGray","-dCompatibilityLevel=1.4",
            "-dNOPAUSE","-dBATCH","-sOutputFile="+gray_path, print_file
        ])
        print_file = gray_path

    lp_cmd = ["lp"]
    # ONLY apply range if page_type is range
    if page_type == "range" and start_page and end_page:
        lp_cmd += ["-P", f"{start_page}-{end_page}"]
    lp_cmd += [print_file, "-n", str(copies)]
    subprocess.run(lp_cmd)

    with sqlite3.connect("kiosk_done.db") as d:
        d.execute("INSERT INTO printed_jobs VALUES (?,?)",
                  (code, datetime.datetime.now().isoformat()))

    with sqlite3.connect("kiosk.db") as c:
        c.execute("UPDATE jobs SET status='PRINTED' WHERE code=?", (code,))

    # ── DELETE all files associated with this job ──────────────────────────
    deleted_at = datetime.datetime.now().strftime("%d %b %Y, %I:%M %p")
    job_id     = os.path.basename(file_path).split("_")[0]

    files_to_delete = []

    # Original uploaded file and converted PDF
    if os.path.exists(file_path):
        files_to_delete.append(file_path)

    # Grayscale print PDF
    gray_path = print_file.replace(".pdf", "_gray.pdf")
    if os.path.exists(gray_path):
        files_to_delete.append(gray_path)

    # All preview images for this job (colour + grayscale)
    for fname in os.listdir(PREVIEW_FOLDER):
        if fname.startswith(job_id + "_page_"):
            files_to_delete.append(os.path.join(PREVIEW_FOLDER, fname))

    for f in files_to_delete:
        try:
            os.remove(f)
        except Exception:
            pass

    # ── SEND PRIVACY DELETION EMAIL ────────────────────────────────────────
    try:
        file_display = os.path.basename(file_path).split("_", 1)[-1]
        msg = Message(
            subject="Your file has been permanently deleted — PrintOnTime",
            sender=os.getenv("MAIL_USERNAME"),
            recipients=[user_email]
        )
        msg.html = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f0f4f8;font-family:'Segoe UI',Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="padding:40px 0;background:#f0f4f8;">
    <tr><td align="center">
      <table width="480" cellpadding="0" cellspacing="0"
        style="background:#fff;border-radius:20px;overflow:hidden;
               box-shadow:0 4px 24px rgba(0,0,0,.1);max-width:480px;">

        <!-- Header -->
        <tr>
          <td style="background:linear-gradient(135deg,#1a1a2e,#16213e);padding:32px 40px;text-align:center;">
            <div style="font-size:24px;font-weight:800;color:#00f7ff;letter-spacing:2px;">PrintOnTime</div>
            <div style="font-size:11px;color:rgba(255,255,255,.4);margin-top:5px;letter-spacing:2px;">SMART PRINT KIOSK</div>
          </td>
        </tr>

        <!-- Body -->
        <tr>
          <td style="padding:32px 40px 0;">

            <!-- Shield icon -->
            <div style="text-align:center;margin-bottom:20px;">
              <div style="display:inline-block;width:64px;height:64px;
                          background:linear-gradient(135deg,#e8fffe,#e8f0ff);
                          border:2px solid #00c8d4;border-radius:50%;
                          line-height:64px;font-size:28px;">
                &#128737;
              </div>
            </div>

            <p style="margin:0 0 6px;font-size:20px;font-weight:700;color:#1a1a2e;text-align:center;">
              Your file has been deleted
            </p>
            <p style="margin:0 0 24px;font-size:14px;color:#666;text-align:center;line-height:1.7;">
              Hi {user_name}, your printout has been collected successfully.
            </p>

            <!-- Deletion confirmation box -->
            <div style="background:linear-gradient(135deg,#e8fffe,#e8f0ff);
                        border:2px solid #00c8d4;border-radius:16px;
                        padding:24px 20px;text-align:center;margin-bottom:24px;">
              <div style="font-size:11px;font-weight:700;letter-spacing:3px;
                          color:#00a0aa;text-transform:uppercase;margin-bottom:8px;">
                File permanently deleted
              </div>
              <div style="font-size:12px;color:#999;">
                Deleted on {deleted_at}
              </div>
            </div>

            <!-- Privacy message -->
            <div style="background:#f8fafc;border-left:4px solid #00c8d4;
                        border-radius:0 12px 12px 0;padding:16px 18px;margin-bottom:24px;">
              <p style="margin:0;font-size:14px;color:#444;line-height:1.8;">
                We believe your documents belong to <strong>you alone</strong>.
                Once your printout is collected, we automatically and permanently
                remove your file, all page previews, and any associated data from
                our servers. <strong>Nothing is retained.</strong>
              </p>
            </div>

            <p style="font-size:13px;color:#aaa;line-height:1.7;text-align:center;">
              Thank you for using PrintOnTime. We respect your privacy.
            </p>
          </td>
        </tr>

        <!-- Footer -->
        <tr>
          <td style="background:#f8fafc;padding:20px 40px;
                     border-radius:0 0 20px 20px;text-align:center;">
            <p style="margin:0;font-size:12px;color:#aaa;line-height:1.8;">
              Automated email from <strong style="color:#555;">PrintOnTime</strong>.
              Do not reply.
            </p>
          </td>
        </tr>

      </table>
    </td></tr>
  </table>
</body>
</html>"""
        mail.send(msg)
    except Exception:
        pass  # Don't fail the print response if email fails

    return jsonify({"status": "PRINTED"})
    
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)


"""
# ═══════════════════════════════════════════════
#  TEST — RECEIPT PDF PREVIEW (remove in production)
#  Visit: /test-receipt in your browser
# ═══════════════════════════════════════════════

@app.route("/test-receipt")
def test_receipt():
    from flask import send_file

    # ── Dummy QR code ──
    qr = qrcode.QRCode(version=1, box_size=8, border=2)
    qr.add_data("123456")
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="#1a1a2e", back_color="white")
    qr_buf = BytesIO()
    qr_img.save(qr_buf, format="PNG")
    qr_base64 = base64.b64encode(qr_buf.getvalue()).decode()

    # ── Generate receipt with dummy data ──
    pdf_buffer = generate_receipt_pdf(
        name        = "Test User",
        code        = "123456",
        file_name   = "my_document.pdf",
        total_pages = 10,
        pages_label = "1 - 10",
        mode_label  = "B&W",
        copies      = 2,
        amount      = "30.00",
        paid_at     = datetime.datetime.now().strftime("%d %b %Y, %I:%M %p"),
        qr_base64   = qr_base64
    )

    return send_file(
        pdf_buffer,
        mimetype="application/pdf",
        as_attachment=False,          # opens inline in browser
        download_name="test_receipt.pdf"
    )
"""
