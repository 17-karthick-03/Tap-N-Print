
Gemini said
🖨️ PrintOnTime – Smart Printing Kiosk System
<p align="center">
<img src="https://img.shields.io/badge/Status-Active-success?style=for-the-badge" alt="Status">
<img src="https://img.shields.io/badge/Maintained%3F-yes-blue?style=for-the-badge" alt="Maintained">
<img src="https://img.shields.io/badge/Framework-Flask-lightgrey?style=for-the-badge&logo=flask" alt="Flask">
<img src="https://img.shields.io/badge/Database-SQLite-003B57?style=for-the-badge&logo=sqlite" alt="SQLite">
</p>

🌟 Overview
Mobile-First Platform: Allows users to upload PDFs and customize printing from their phones.

Hardware-Free Access: Eliminates the need for USB drives or cables at printing centers.

Secure Pickup: Instant printing at kiosks using a secure, unique code.

🚀 Features
🔐 User Account System
Authentication: User signup and login with secure password hashing.

Profile Management: Dedicated profile pages with picture upload and account deletion options.

Activity Logs: Logout functionality and complete print history tracking.

📄 Document Upload
PDF Intelligence: Automatic page count detection and file validation.

Optimized UI: Clean, mobile-friendly interface for seamless document selection.

🎨 Print Customization
Global Settings: Toggle between Black & White/Color, Single/Double-sided, and number of copies.

Granular Control: Per-page customization (e.g., Page 1 in B&W, Page 2 in Color).

💳 Online Payment & Notifications
Gateway Integration: Secure transactions via Razorpay with automatic order verification.

Instant Delivery: Automated email containing a 6-digit print code and pickup instructions.

🏗️ Kiosk Printing System
Verification: User enters the 6-digit code for system validation.

Automatic Printing: Documents print instantly upon successful code entry.

Safety Measures:

Prevents duplicate printing of the same job.

Tracks job status in real-time.

Automatically converts color pages to grayscale when necessary.

🏗️ System Architecture

graph TD
    A[Mobile User] -->|Upload PDF| B(Flask Web Server)
    B --> C[(SQLite Database)]
    B --> D[Razorpay Gateway]
    B --> E[Email Notification System]
    E -->|6-Digit Code| F[User]
    F -->|Enters Code| G[Printer Kiosk]
    G --> H{Validate Code}
    H -->|Success| I[Instant Print]

📂 Project Structure
app.py: Core backend logic and Flask route definitions.

kiosk.db: Primary system database.

kiosk_done.db: Historical records of completed print jobs.

uploads/: Secure storage for uploaded PDF files.

static/: Assets including CSS, JS, and user profile pictures.

templates/: HTML views for login, signup, profile, history, and kiosk.

.env: Configuration for environment variables.

🧰 Technologies Used
Framework: Flask (Backend) & Jinja2 (Rendering).

Database: SQLite.

Payment: Razorpay API.

Processing: Ghostscript (Grayscale) & PyPDF2 (Page Counting).

Communication: Flask-Mail (Email Notifications).

Frontend: HTML, CSS, and JavaScript.

⚙️ Installation Guide
Clone & Dependencies
git clone https://github.com/17-karthick-03/Tap-N-Print.git
cd folder_name
pip install flask werkzeug PyPDF2 pdf2image razorpay flask-mail python-dotenv qrcode reportlab
Required System Tools

Ghostscript:

Linux: sudo apt install ghostscript

Windows: https://ghostscript.com/releases/

Poppler:

Linux: sudo apt install poppler-utils

Windows: https://github.com/oschwartz10612/poppler-windows/releases

Environment Variables

Create a .env file in the root directory:

RAZORPAY_KEY_ID=your_key
RAZORPAY_KEY_SECRET=your_secret
MAIL_USERNAME=your_email@gmail.com
MAIL_PASSWORD=your_email_app_password
Run Server

python app.py
📱 User Workflow
Auth: Sign up or log in to the platform.

Upload: Select and upload your PDF document.

Configure: Set copies, color mode, and specific page settings.

Pay: Complete the secure Razorpay transaction.

Notify: Check your email for the unique 6-digit print code.

Print: Visit the physical kiosk and enter your code to collect the document.

👨‍💻 Authors
Karthick S: B.E Student @ SRM Valliammai Engineering College

Naveen Kumar S: B.E Student @ SRM Valliammai Engineering College

Nikhil B: B.E Student @ SRM Valliammai Engineering College
