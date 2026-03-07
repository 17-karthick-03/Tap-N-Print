🖨️ PrintOnTime – Smart Printing Kiosk System
<p align="center">
<img src="https://img.shields.io/badge/Status-Active-success?style=for-the-badge" alt="Status">
<img src="https://img.shields.io/badge/Maintained%3F-yes-blue?style=for-the-badge" alt="Maintained">
<img src="https://img.shields.io/badge/Framework-Flask-lightgrey?style=for-the-badge&logo=flask" alt="Flask">
<img src="https://img.shields.io/badge/Database-SQLite-003B57?style=for-the-badge&logo=sqlite" alt="SQLite">
</p>

🌟 Overview:

    PrintOnTime is a mobile-first document printing platform that allows users to upload PDF files, customize printing options, pay online, and print documents instantly at a kiosk using a secure code. This system removes the need for USB drives, cables, or computer access at printing centers. Users simply upload documents from their phone, pay online, and collect the printed document from a printer kiosk.

🚀 Features
🔐 User Account System
User signup and login with secure password hashing.

Profile Management: Profile page, picture upload, and account deletion.

Tracking: Logout functionality and full print history tracking.

📄 Document Upload
PDF Support: Automatic page count detection and file validation.

UI: Mobile-friendly upload interface.

🎨 Print Customization
Global Options: Print Mode (B&W/Color), Page Sides (Single/Double), and Copies.

Per-Page Customization: Assign different modes for each page (e.g., Page 1: B&W, Page 2: Color).

💳 Online Payment & Notifications
Razorpay Integration: Secure online payment, auto-order creation, and verification.

Email System: Automated delivery of a 6-digit print code and instructions upon successful payment.

🏗️ Kiosk Printing System
Physical Kiosk: User enters code → System validates → Document prints.

Protections: Prevents duplicate printing, tracks jobs, and converts color to grayscale when required.

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

PrintOnTime/
├── app.py                 # Backend logic & Flask routes
├── kiosk.db               # Primary database
├── kiosk_done.db          # Printed jobs record
├── uploads/               # PDF file storage
├── static/                # CSS, JS, and profile_pics/
├── templates/             # index, login, signup, profile, history, kiosk.html
├── .env                   # Environment variables
└── README.md              # Project documentation

🧰 Technologies Used
Flask – Backend framework
SQLite – Database management
Razorpay – Online payment gateway
Ghostscript – PDF colour to grayscale conversion
PyPDF2 – PDF page counting
Flask-Mail – Email notifications
HTML / CSS / JavaScript – Frontend interface
Jinja2 – Template rendering

⚙️ Installation Guide
1. Clone & Dependencies
    git clone https://github.com/17-karthick-03/Tap-N-Print.git
    cd folder_name
    pip install flask werkzeug PyPDF2 pdf2image razorpay flask-mail python-dotenv qrcode pillow
2. Required System Tools
    Ghostscript (PDF grayscale conversion):
        Linux: sudo apt install ghostscript
        Windows: https://ghostscript.com/releases/

    Poppler (Required for pdf2image):
        Linux: sudo apt install poppler-utils
        Windows: https://github.com/oschwartz10612/poppler-windows/releases
3. Environment Variables
    Create a .env file in the root:
       RAZORPAY_KEY_ID=your_key
       RAZORPAY_KEY_SECRET=your_secret
       MAIL_USERNAME=your_email@gmail.com
       MAIL_PASSWORD=your_email_app_password
4. Run Server
      python app.py

📱 User Workflow
1. Login/Signup to the platform.
2. Upload a PDF document.
3. Configure specific print settings (sides, copies, color).
4. Pay securely via Razorpay.
5. Receive a unique 6-digit print code via email.
6. Visit Kiosk and enter the code to print instantly.


👨‍💻 Author
Karthick S
B.E Student @ SRM Valliammai Engineering College
Naveen Kumar S
B.E Student @ SRM Valliammai Engineering College
Nikhil B
B.E Student @ SRM Valliammai Engineering College
