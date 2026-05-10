from flask_mail import Mail, Message
from flask import Flask, render_template, request, session, redirect, url_for, send_file, make_response, jsonify, Response, has_request_context
from datetime import datetime, timedelta, date
from decimal import Decimal
import mysql.connector, uuid
import random; import string
import json
import io
import os
import re
import math
import requests
import base64
import hashlib
import hmac
from base64 import b64encode
import traceback
import shutil
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

from apify_client import ApifyClient
import joblib
import numpy as np
from openai import OpenAI
from dotenv import load_dotenv

from blockchain_integration import ( get_blockchain_manager,
    init_blockchain_contracts, to_checksum_address,
    get_wallet_transactions_from_blockchain, get_wallet_address,
    encrypt_payload, sha256_hex,
)

# def modules():
#     import subprocess
#     import sys
    
#     required_modules = [
#         'flask',
#         'flask-mail',
#         'mysql-connector-python',
#         'requests',
#         'apify-client',
#         'joblib',
#         'openai',
#         'gpt4all',
#         'python-dotenv',
#         'werkzeug'
#     ]
    
#     for module in required_modules:
#         try:
#             __import__(module.replace('-', '_'))
#             print(f"{module} is already installed")
#         except ImportError:
#             try:
#                 print(f"Installing {module}...")
#                 subprocess.check_call([sys.executable, '-m', 'pip', 'install', module])
#                 print(f"Successfully installed {module}")
#             except subprocess.CalledProcessError as e:
#                 print(f"Failed to install {module}: {e}")
#                 return False
    
#     print("All required modules are installed!")
#     return True

# modules()


# ---------------------------------------------------------------------------
# ------------------------------- SYSTEM SETUP ------------------------------
# ---------------------------------------------------------------------------

app = Flask(__name__)
app.secret_key = "Hev_Raphy"
app.permanent_session_lifetime = timedelta(hours=3)

load_dotenv()

app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'kidmartenterprise@gmail.com'
app.config['MAIL_PASSWORD'] = 'kstk cpek pqbt mqvy'
mail = Mail(app)

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("Warning: PIL/Pillow not available. Image compression will be disabled.")

UPLOAD_FOLDER = 'static/uploads'
COMPLETION_PROOF_FOLDER = os.path.join(UPLOAD_FOLDER, 'fund_completion_proofs')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}
FUND_WORKFLOW_STATUSES = ['Pending', 'Reviewed', 'Approved', 'In Progress', 'Completed']
FUND_WORKFLOW_PUBLIC_STATUS = {
    'Approved': 'Active',
    'In Progress': 'Active',
    'Completed': 'Completed'
}
DONATION_FUND_STATUSES = [
    'Donation Received',
    'Payment Confirmed',
    'Pending Allocation',
    'Funds Disbursed',
    'Completed / Used'
]

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
if not os.path.exists(COMPLETION_PROOF_FOLDER):
    os.makedirs(COMPLETION_PROOF_FOLDER)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def save_payment_verification_screenshot(upload_file, donation_ref):
    if not upload_file or not upload_file.filename:
        return None, 'Please upload a payment screenshot.'

    if not allowed_file(upload_file.filename):
        return None, 'Please upload a PNG or JPG screenshot.'

    if PIL_AVAILABLE:
        try:
            Image.open(upload_file.stream).verify()
            upload_file.stream.seek(0)
        except Exception:
            return None, 'The uploaded screenshot could not be read as an image.'

    original_filename = secure_filename(upload_file.filename)
    extension = os.path.splitext(original_filename)[1].lower() or '.png'
    stored_filename = f"payment_verification_{donation_ref}_{uuid.uuid4().hex}{extension}"
    stored_path = os.path.join(PAYMENT_VERIFICATION_FOLDER, stored_filename)
    upload_file.save(stored_path)
    return stored_filename, None


def extract_reference_number_with_openai(image_path):
    api_key = os.getenv("OPENAI_KEY")
    if not api_key or not image_path or not os.path.exists(image_path):
        return None

    try:
        with open(image_path, 'rb') as image_file:
            image_bytes = image_file.read()

        mime_type = 'image/jpeg'
        extension = os.path.splitext(image_path)[1].lower()
        if extension == '.png':
            mime_type = 'image/png'

        image_b64 = base64.b64encode(image_bytes).decode('utf-8')
        image_data_url = f"data:{mime_type};base64,{image_b64}"

        prompt = (
            "Extract the payment reference number from this payment screenshot. "
            "Return JSON only with the shape {\"reference_number\":\"...\"}. "
            "If no reference number is visible, return {\"reference_number\":\"\"}."
        )

        openai_client = OpenAI(api_key=api_key)

        try:
            response = openai_client.responses.create(
                model="gpt-4.1-mini",
                input=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": prompt},
                            {"type": "input_image", "image_url": image_data_url, "detail": "high"}
                        ]
                    }
                ]
            )
            raw_output = (getattr(response, 'output_text', None) or '').strip()
        except Exception:
            response = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": image_data_url}}
                        ]
                    }
                ],
                temperature=0
            )
            raw_output = (response.choices[0].message.content or '').strip()

        if not raw_output:
            return None

        try:
            parsed = json.loads(raw_output)
        except json.JSONDecodeError:
            json_start = raw_output.find('{')
            json_end = raw_output.rfind('}')
            if json_start == -1 or json_end == -1 or json_end <= json_start:
                return None
            parsed = json.loads(raw_output[json_start:json_end + 1])

        reference_number = (parsed.get('reference_number') or '').strip()
        if not reference_number:
            return None

        return reference_number
    except Exception as e:
        print(f"OpenAI OCR extraction failed: {e}")
        return None

def public_upload_url(filename):
    return url_for('static', filename=f'uploads/{filename}')

APIFY_TOKEN = os.getenv("APIFY_KEY")
PAYMONGO_SECRET_KEY = os.getenv("PAYMONGO_SECRET_KEY") or os.getenv("PAYMONGO_KEY")
PAYMONGO_PUBLIC_KEY = os.getenv("PAYMONGO_PUBLIC_KEY")
PAYMONGO_WEBHOOK_SECRET_KEY = os.getenv("PAYMONGO_WEBHOOK_SECRET_KEY")

if not PAYMONGO_SECRET_KEY:
    raise RuntimeError("PAYMONGO_SECRET_KEY is missing from the environment.")
if not PAYMONGO_WEBHOOK_SECRET_KEY:
    print("Warning: PAYMONGO_WEBHOOK_SECRET_KEY is missing. PayMongo webhook signature verification is disabled.")

auth_header = base64.b64encode(f"{PAYMONGO_SECRET_KEY}:".encode()).decode()
QRPH_PAYMENT_CODES = {}
PAYMENT_VERIFICATION_FOLDER = os.path.join(UPLOAD_FOLDER, 'payment_verification')

if not os.path.exists(PAYMENT_VERIFICATION_FOLDER):
    os.makedirs(PAYMENT_VERIFICATION_FOLDER)

QR_RECEIPT_VERIFICATION_SESSION_KEY = 'verified_qr_receipts'


# --------------------------------------------------------------------------
# ---------------------------- PLATFORM SETTINGS ---------------------------
# --------------------------------------------------------------------------

def get_setting(key, default_value=None):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT setting_value, setting_type FROM platform_settings WHERE setting_key = %s", (key,))
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if result:
            value, setting_type = result
            if setting_type == 'boolean':
                return value.lower() == 'true'
            elif setting_type == 'number':
                return int(value) if '.' not in value else float(value)
            else:
                return value
        return default_value
    except Exception as e:
        print(f"Error getting setting {key}: {e}")
        return default_value

def update_setting(key, value, setting_type='string'):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if setting_type == 'boolean':
            value_str = 'true' if value else 'false'
        else:
            value_str = str(value)
        
        cursor.execute("""
            INSERT INTO platform_settings (setting_key, setting_value, setting_type) 
            VALUES (%s, %s, %s) 
            ON DUPLICATE KEY UPDATE 
            setting_value = VALUES(setting_value), 
            setting_type = VALUES(setting_type),
            updated_at = CURRENT_TIMESTAMP
        """, (key, value_str, setting_type))
        
        conn.commit()
        cursor.close()
        conn.close()
        return True
    except Exception as e:
        print(f"Error updating setting {key}: {e}")
        return False

def get_all_settings():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT setting_key, setting_value, setting_type FROM platform_settings")
        settings = cursor.fetchall()
        cursor.close()
        conn.close()
        
        result = {}
        for setting in settings:
            key = setting['setting_key']
            value = setting['setting_value']
            setting_type = setting['setting_type']
            
            if setting_type == 'boolean':
                result[key] = value.lower() == 'true'
            elif setting_type == 'number':
                result[key] = int(value) if '.' not in value else float(value)
            else:
                result[key] = value
                
        return result
    except Exception as e:
        print(f"Error getting all settings: {e}")
        return {}


# --------------------------------------------------------------------------
# ------------------------------- MAINTENANCE ------------------------------
# --------------------------------------------------------------------------

@app.before_request
def check_maintenance_mode():
    if request.endpoint and (
        request.endpoint.startswith('admin') or 
        request.endpoint.startswith('treasurer') or
        request.endpoint.startswith('static') or
        request.endpoint in ['goto_signin', 'signin', 'get_settings_api', 'update_settings_api', 'update_settings_bulk']
    ):
        return
    
    if get_setting('maintenance_mode', False):
        return render_template('maintenance.html'), 503


@app.before_request
def enforce_verified_user_access():
    endpoint = request.endpoint or ''

    if not session.get('user_id'):
        return

    if endpoint.startswith('static') or endpoint in {
        'goto_signin',
        'signin',
        'create_account',
        'signup',
        'forgot',
        'verify_otp',
        'signout'
    }:
        return

    role = (session.get('role') or '').strip()
    if role in {'Admin', 'Treasurer', 'Bot'}:
        return

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id_verification_status FROM users WHERE id = %s",
            (session['user_id'],)
        )
        result = cursor.fetchone()
    except mysql.connector.Error as err:
        print(f"Error checking verification status: {err}")
        session.clear()
        return redirect(url_for('goto_signin'))
    finally:
        if 'cursor' in locals() and cursor:
            cursor.close()
        if 'conn' in locals() and conn:
            conn.close()

    verification_status = (result[0] if result else None) or 'not_verified'
    if verification_status == 'verified':
        session['id_verification_status'] = verification_status
        return

    session.clear()
    message = "Only verified users can access the system. Please wait for admin approval."
    if request.path.startswith('/api/'):
        return jsonify({'error': message}), 403
    return render_template('signin.html', error=message), 403

def get_db_connection():
    config = {
        "host": os.getenv("MYSQLHOST"),
        "user": os.getenv("MYSQLUSER"),
        "password": os.getenv("MYSQLPASSWORD"),
        "database": os.getenv("MYSQLDATABASE"),
        "port": os.getenv("MYSQLPORT")
    }

    try:
        return mysql.connector.connect(**config, consume_results=True)
    except TypeError:
        return mysql.connector.connect(**config)

def init_audit_trail():
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_trail_logs (
                audit_id BIGINT AUTO_INCREMENT PRIMARY KEY,
                event_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                actor_user_id INT NULL,
                actor_email VARCHAR(255) NULL,
                actor_role VARCHAR(50) NULL,
                action VARCHAR(120) NOT NULL,
                entity_type VARCHAR(100) NOT NULL,
                entity_id VARCHAR(120) NULL,
                request_method VARCHAR(10) NULL,
                request_path VARCHAR(255) NULL,
                ip_address VARCHAR(64) NULL,
                user_agent VARCHAR(255) NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'SUCCESS',
                reason VARCHAR(255) NULL,
                before_data LONGTEXT NULL,
                after_data LONGTEXT NULL,
                metadata LONGTEXT NULL,
                previous_hash CHAR(64) NULL,
                entry_hash CHAR(64) NOT NULL,
                INDEX idx_audit_event_time (event_time),
                INDEX idx_audit_actor (actor_user_id),
                INDEX idx_audit_action (action),
                INDEX idx_audit_entity (entity_type, entity_id)
            )
        """)
        conn.commit()
        print("Audit trail ready")
    except Exception as e:
        print(f"Error initializing audit trail table: {e}")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def init_admin_user_action_logs():
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS admin_user_action_logs (
                action_id BIGINT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                user_email VARCHAR(255) NULL,
                action_type VARCHAR(40) NOT NULL,
                previous_role VARCHAR(40) NULL,
                new_role VARCHAR(40) NULL,
                previous_verification_status VARCHAR(40) NULL,
                new_verification_status VARCHAR(40) NULL,
                reason VARCHAR(255) NOT NULL,
                remarks TEXT NULL,
                acted_by INT NULL,
                acted_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_admin_user_action_user (user_id),
                INDEX idx_admin_user_action_type (action_type),
                INDEX idx_admin_user_action_acted_at (acted_at)
            )
        """)
        conn.commit()
        print("Admin user action log ready")
    except Exception as e:
        print(f"Error initializing admin user action log table: {e}")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def init_fund_completion_proofs():
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS fund_completion_proofs (
                proof_id BIGINT AUTO_INCREMENT PRIMARY KEY,
                fund_id INT NOT NULL,
                audit_id BIGINT NULL,
                uploaded_by INT NULL,
                proof_filename VARCHAR(255) NOT NULL,
                original_filename VARCHAR(255) NULL,
                proof_mime_type VARCHAR(120) NULL,
                proof_note VARCHAR(500) NULL,
                uploaded_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_completion_proof_fund (fund_id),
                INDEX idx_completion_proof_uploaded_at (uploaded_at),
                INDEX idx_completion_proof_audit (audit_id)
            )
        """)
        conn.commit()
        print("Fund completion proof storage ready")
    except Exception as e:
        print(f"Error initializing fund completion proof table: {e}")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def init_fund_status_workflow():
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS fund_status_workflow (
                fund_id INT NOT NULL PRIMARY KEY,
                current_status VARCHAR(40) NOT NULL DEFAULT 'Pending',
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                updated_by INT NULL,
                INDEX idx_fund_workflow_status (current_status),
                INDEX idx_fund_workflow_updated_at (updated_at)
            )
        """)
        cursor.execute("""
            INSERT INTO fund_status_workflow (fund_id, current_status, created_at, updated_at)
            SELECT
                f.fund_id,
                CASE
                    WHEN f.fund_status = 'Completed' THEN 'Completed'
                    WHEN f.fund_status = 'Active' AND COALESCE(SUM(CASE WHEN d.don_status = 'Paid' THEN d.don_amount ELSE 0 END), 0) > 0 THEN 'In Progress'
                    WHEN f.fund_status = 'Active' THEN 'Approved'
                    WHEN f.fund_status = 'Pending' THEN 'Pending'
                    ELSE 'Pending'
                END AS current_status,
                COALESCE(f.fund_startdate, NOW()),
                COALESCE(f.fund_startdate, NOW())
            FROM fundraisers f
            LEFT JOIN donations d ON f.fund_id = d.fund_id
            LEFT JOIN fund_status_workflow fsw ON f.fund_id = fsw.fund_id
            WHERE fsw.fund_id IS NULL
            GROUP BY f.fund_id
        """)
        conn.commit()
        print("Fund status workflow ready")
    except Exception as e:
        print(f"Error initializing fund status workflow table: {e}")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def get_allowed_fund_workflow_targets(current_status):
    try:
        current_index = FUND_WORKFLOW_STATUSES.index(current_status)
    except ValueError:
        current_index = 0

    allowed = [FUND_WORKFLOW_STATUSES[current_index]]
    if current_index + 1 < len(FUND_WORKFLOW_STATUSES):
        allowed.append(FUND_WORKFLOW_STATUSES[current_index + 1])
    return allowed

def init_donation_fund_tracking():
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS donation_fund_status (
                reference_number VARCHAR(80) NOT NULL PRIMARY KEY,
                donation_id INT NULL,
                current_status VARCHAR(40) NOT NULL DEFAULT 'Donation Received',
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                updated_by INT NULL,
                INDEX idx_donation_fund_ref (reference_number),
                INDEX idx_donation_fund_donation (donation_id),
                INDEX idx_donation_fund_status (current_status),
                INDEX idx_donation_fund_updated_at (updated_at)
            )
        """)
        cursor.execute("""
            SELECT COLUMN_NAME
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'donation_fund_status'
        """)
        existing_columns = {
            row[0] if not isinstance(row, dict) else row.get('COLUMN_NAME')
            for row in cursor.fetchall()
        }
        if 'reference_number' not in existing_columns:
            cursor.execute("ALTER TABLE donation_fund_status ADD COLUMN reference_number VARCHAR(80) NULL AFTER donation_id")
        if 'donation_id' not in existing_columns:
            cursor.execute("ALTER TABLE donation_fund_status ADD COLUMN donation_id INT NULL AFTER reference_number")

        cursor.execute("""
            UPDATE donation_fund_status dfs
            JOIN donations d ON d.don_id = dfs.donation_id
            SET dfs.reference_number = d.don_refnum
            WHERE (dfs.reference_number IS NULL OR TRIM(dfs.reference_number) = '')
        """)
        cursor.execute("""
            UPDATE donation_fund_status dfs
            JOIN donations d ON d.don_refnum = dfs.reference_number
            SET dfs.current_status = CASE
                WHEN dfs.current_status = 'Pending' AND d.don_status = 'Paid' THEN 'Payment Confirmed'
                WHEN dfs.current_status = 'Pending' THEN 'Donation Received'
                WHEN dfs.current_status = 'In Progress' THEN 'Pending Allocation'
                WHEN dfs.current_status = 'Completed' THEN 'Completed / Used'
                ELSE dfs.current_status
            END
            WHERE dfs.current_status IN ('Pending', 'In Progress', 'Completed')
        """)

        try:
            cursor.execute("ALTER TABLE donation_fund_status MODIFY donation_id INT NULL")
        except Exception as migrate_error:
            print(f"Donation fund tracking migration note: {migrate_error}")

        try:
            cursor.execute("ALTER TABLE donation_fund_status DROP PRIMARY KEY, ADD PRIMARY KEY (reference_number)")
        except Exception as migrate_error:
            print(f"Donation fund tracking primary key migration note: {migrate_error}")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS donation_completion_proofs (
                proof_id BIGINT AUTO_INCREMENT PRIMARY KEY,
                donation_id INT NOT NULL,
                fund_id INT NULL,
                audit_id BIGINT NULL,
                uploaded_by INT NULL,
                proof_filename VARCHAR(255) NOT NULL,
                original_filename VARCHAR(255) NULL,
                proof_mime_type VARCHAR(120) NULL,
                proof_note VARCHAR(500) NULL,
                uploaded_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_donation_proof_donation (donation_id),
                INDEX idx_donation_proof_fund (fund_id),
                INDEX idx_donation_proof_uploaded_at (uploaded_at)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS donation_fund_status_history (
                history_id BIGINT AUTO_INCREMENT PRIMARY KEY,
                reference_number VARCHAR(80) NOT NULL,
                donation_id INT NULL,
                status VARCHAR(40) NOT NULL,
                previous_status VARCHAR(40) NULL,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_by INT NULL,
                audit_id BIGINT NULL,
                note VARCHAR(255) NULL,
                INDEX idx_donation_fund_history_ref (reference_number),
                INDEX idx_donation_fund_history_donation (donation_id),
                INDEX idx_donation_fund_history_status (status),
                INDEX idx_donation_fund_history_updated_at (updated_at)
            )
        """)
        cursor.execute("""
            INSERT INTO donation_fund_status (reference_number, donation_id, current_status, created_at, updated_at)
            SELECT
                d.don_refnum,
                d.don_id,
                CASE
                    WHEN d.don_status = 'Paid' THEN 'Payment Confirmed'
                    ELSE 'Donation Received'
                END,
                COALESCE(d.don_date, NOW()),
                COALESCE(d.don_date, NOW())
            FROM donations d
            LEFT JOIN donation_fund_status dfs ON d.don_refnum = dfs.reference_number
            WHERE dfs.reference_number IS NULL
        """)
        cursor.execute("""
            INSERT INTO donation_fund_status_history (
                reference_number, donation_id, status, previous_status, updated_at, note
            )
            SELECT d.don_refnum, d.don_id, 'Donation Received', NULL, COALESCE(d.don_date, NOW()), 'Initial donation record'
            FROM donations d
            WHERE NOT EXISTS (
                SELECT 1
                FROM donation_fund_status_history h
                WHERE h.reference_number = d.don_refnum
                  AND h.status = 'Donation Received'
            )
        """)
        cursor.execute("""
            INSERT INTO donation_fund_status_history (
                reference_number, donation_id, status, previous_status, updated_at, note
            )
            SELECT d.don_refnum, d.don_id, 'Payment Confirmed', 'Donation Received', COALESCE(d.don_date, NOW()), 'Payment status already confirmed'
            FROM donations d
            WHERE d.don_status = 'Paid'
              AND NOT EXISTS (
                SELECT 1
                FROM donation_fund_status_history h
                WHERE h.reference_number = d.don_refnum
                  AND h.status = 'Payment Confirmed'
            )
        """)
        conn.commit()
        print("Donation fund tracking ready")
    except Exception as e:
        print(f"Error initializing donation fund tracking tables: {e}")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def get_allowed_donation_fund_targets(current_status):
    try:
        current_index = DONATION_FUND_STATUSES.index(current_status)
    except ValueError:
        current_index = 0

    allowed = [DONATION_FUND_STATUSES[current_index]]
    if current_index + 1 < len(DONATION_FUND_STATUSES):
        allowed.append(DONATION_FUND_STATUSES[current_index + 1])
    return allowed

def record_donation_fund_status_update(cursor, reference_number, donation_id, new_status,
                                       previous_status=None, updated_by=None, audit_id=None,
                                       note=None):
    cursor.execute("""
        INSERT INTO donation_fund_status (
            reference_number, donation_id, current_status, updated_by, created_at, updated_at
        )
        VALUES (%s, %s, %s, %s, NOW(), NOW())
        ON DUPLICATE KEY UPDATE
            donation_id = VALUES(donation_id),
            current_status = VALUES(current_status),
            updated_by = VALUES(updated_by),
            updated_at = NOW()
    """, (reference_number, donation_id, new_status, updated_by))
    cursor.execute("""
        INSERT INTO donation_fund_status_history (
            reference_number, donation_id, status, previous_status, updated_at, updated_by, audit_id, note
        )
        VALUES (%s, %s, %s, %s, NOW(), %s, %s, %s)
    """, (reference_number, donation_id, new_status, previous_status, updated_by, audit_id, note))

def _safe_json(data):
    if data is None:
        return None
    try:
        return json.dumps(data, ensure_ascii=False, default=str)
    except Exception:
        return json.dumps({'unserializable': str(data)})

def _make_json_safe(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, bytes):
        return None
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _make_json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_make_json_safe(item) for item in value]
    return str(value)

def _get_client_ip():
    if not has_request_context():
        return None
    forwarded = request.headers.get('X-Forwarded-For', '')
    if forwarded:
        return forwarded.split(',')[0].strip()[:64]
    return (request.remote_addr or '')[:64]

def record_admin_user_action(
    user_id,
    user_email,
    action_type,
    previous_role,
    new_role,
    previous_verification_status,
    new_verification_status,
    reason,
    remarks=None,
    conn=None,
    cursor=None,
    acted_by=None
):
    owns_connection = conn is None or cursor is None
    local_conn = conn
    local_cursor = cursor

    try:
        if owns_connection:
            local_conn = get_db_connection()
            local_cursor = local_conn.cursor()

        local_cursor.execute("""
            INSERT INTO admin_user_action_logs (
                user_id,
                user_email,
                action_type,
                previous_role,
                new_role,
                previous_verification_status,
                new_verification_status,
                reason,
                remarks,
                acted_by
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            user_id,
            user_email,
            action_type,
            previous_role,
            new_role,
            previous_verification_status,
            new_verification_status,
            reason,
            remarks,
            acted_by if acted_by is not None else session.get('user_id')
        ))

        if owns_connection:
            local_conn.commit()
        return local_cursor.lastrowid or True
    except Exception as e:
        print(f"Error recording admin user action [{action_type}] for user {user_id}: {e}")
        return False
    finally:
        if owns_connection:
            if local_cursor:
                local_cursor.close()
            if local_conn:
                local_conn.close()

def send_user_action_email(user_email, user_name, action_taken, reason, remarks=None):
    if not user_email:
        return False, 'User has no registered email address.'

    action_label = (action_taken or '').strip().lower()
    if action_label not in {'approved', 'suspended'}:
        action_label = 'updated'

    actor_display = session.get('username') or session.get('email') or 'ReliePH Admin'
    subject = f"ReliePH Account {action_label.title()} Notification"
    body_lines = [
        f"Hello {user_name or 'User'},",
        "",
        f"Your ReliePH account has been {action_label}.",
        "",
        f"Action taken: {action_label.title()}",
        f"Reason: {reason}",
    ]

    if remarks:
        body_lines.extend([
            f"Admin remarks: {remarks}",
        ])

    body_lines.extend([
        "",
        f"Reviewed by: {actor_display}",
        "",
        "If you have questions about this decision, please contact the ReliePH admin team.",
        "",
        "ReliePH"
    ])

    try:
        msg = Message(subject, sender=app.config['MAIL_USERNAME'], recipients=[user_email])
        msg.body = "\n".join(body_lines)
        mail.send(msg)
        return True, None
    except Exception as e:
        print(f"Error sending user action email to {user_email}: {e}")
        return False, str(e)

def send_fund_creator_donation_email(donation_refnum):
    if not donation_refnum:
        return False, 'Missing donation reference number.'

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT
                d.don_refnum,
                d.don_donorname,
                d.don_amount,
                d.don_date,
                d.don_status,
                d.don_donorid,
                f.fund_id,
                f.fund_title,
                creator.name AS creator_name,
                creator.email AS creator_email,
                donor.email AS donor_email
            FROM donations d
            JOIN fundraisers f ON d.fund_id = f.fund_id
            LEFT JOIN users creator ON f.fund_creatorid = creator.id
            LEFT JOIN users donor ON d.don_donorid = donor.id
            WHERE d.don_refnum = %s
            LIMIT 1
        """, (donation_refnum,))
        donation = cursor.fetchone()

        if not donation:
            return False, 'Donation record not found.'

        if (donation.get('don_status') or '').strip() != 'Paid':
            return False, 'Donation is not marked as paid.'

        creator_email = (donation.get('creator_email') or '').strip()
        if not creator_email:
            return False, 'Fund creator has no registered email address.'

        donor_name = (donation.get('don_donorname') or '').strip() or 'Anonymous'
        donor_email = (donation.get('donor_email') or '').strip()
        donation_amount = float(donation.get('don_amount') or 0)
        donation_time = donation.get('don_date')
        donation_time_label = (
            donation_time.strftime('%B %d, %Y %I:%M %p')
            if donation_time else
            datetime.now().strftime('%B %d, %Y %I:%M %p')
        )

        donor_lines = [f"Donor name: {donor_name}"]
        if donor_email and donor_email.lower() != 'none@example.com':
            donor_lines.append(f"Donor email: {donor_email}")
        else:
            donor_lines.append("Donor email: Not available")

        body_lines = [
            f"Hello {donation.get('creator_name') or 'Fund Creator'},",
            "",
            "Someone has donated to your fundraiser on ReliePH.",
            "",
            "Donation details:",
            *donor_lines,
            f"Donation amount: PHP {donation_amount:,.2f}",
            f"Fundraiser: {donation.get('fund_title') or 'Untitled Fundraiser'}",
            f"Date and time of donation: {donation_time_label}",
            f"Reference number: {donation.get('don_refnum')}",
            "",
            "This is a confirmation that a successful donation has been recorded in the system.",
            "",
            "ReliePH"
        ]

        msg = Message(
            'ReliePH Donation Notification',
            sender=app.config['MAIL_USERNAME'],
            recipients=[creator_email]
        )
        msg.body = "\n".join(body_lines)
        mail.send(msg)
        return True, None
    except Exception as e:
        print(f"Error sending donation notification for {donation_refnum}: {e}")
        return False, str(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def log_audit_event(
    action,
    entity_type,
    entity_id=None,
    status='SUCCESS',
    reason=None,
    before_data=None,
    after_data=None,
    metadata=None,
    conn=None,
    cursor=None,
    actor_user_id=None,
    actor_email=None,
    actor_role=None
):
    """
    Append a tamper-evident audit trail entry.
    If conn/cursor are supplied, the insert participates in the current transaction.
    """
    owns_connection = conn is None or cursor is None
    local_conn = conn
    local_cursor = cursor

    try:
        if owns_connection:
            local_conn = get_db_connection()
            local_cursor = local_conn.cursor()

        if has_request_context():
            if actor_user_id is None:
                actor_user_id = session.get('user_id')
            if actor_email is None:
                actor_email = session.get('email')
            if actor_role is None:
                actor_role = session.get('role')

        before_json = _safe_json(before_data)
        after_json = _safe_json(after_data)
        metadata_json = _safe_json(metadata)
        request_method = request.method if has_request_context() else None
        request_path = request.path if has_request_context() else None
        ip_address = _get_client_ip() if has_request_context() else None
        user_agent = request.headers.get('User-Agent', '')[:255] if has_request_context() else None

        local_cursor.execute("SELECT entry_hash FROM audit_trail_logs ORDER BY audit_id DESC LIMIT 1")
        previous_hash_row = local_cursor.fetchone()
        if isinstance(previous_hash_row, dict):
            previous_hash = previous_hash_row.get('entry_hash')
        else:
            previous_hash = previous_hash_row[0] if previous_hash_row else None
        timestamp_str = datetime.now().isoformat()

        payload = "|".join([
            str(timestamp_str),
            str(actor_user_id or ''),
            str(actor_email or ''),
            str(actor_role or ''),
            str(action or ''),
            str(entity_type or ''),
            str(entity_id or ''),
            str(status or ''),
            str(reason or ''),
            str(before_json or ''),
            str(after_json or ''),
            str(metadata_json or ''),
            str(previous_hash or '')
        ])
        entry_hash = hashlib.sha256(payload.encode('utf-8')).hexdigest()

        local_cursor.execute("""
            INSERT INTO audit_trail_logs (
                actor_user_id, actor_email, actor_role, action, entity_type, entity_id,
                request_method, request_path, ip_address, user_agent,
                status, reason, before_data, after_data, metadata, previous_hash, entry_hash
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            actor_user_id, actor_email, actor_role, action, entity_type, str(entity_id) if entity_id is not None else None,
            request_method, request_path, ip_address, user_agent,
            status, reason, before_json, after_json, metadata_json, previous_hash, entry_hash
        ))

        if owns_connection:
            local_conn.commit()
        return local_cursor.lastrowid or True
    except Exception as e:
        print(f"Audit log error [{action}/{entity_type}]: {e}")
        return False
    finally:
        if owns_connection:
            if local_cursor:
                local_cursor.close()
            if local_conn:
                local_conn.close()

def parse_donation_notes_json(notes_value):
    """Return structured donation notes when stored as a JSON object."""
    if not notes_value:
        return None

    if isinstance(notes_value, dict):
        return notes_value

    if not isinstance(notes_value, str):
        return None

    try:
        parsed = json.loads(notes_value)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


def extract_display_notes(notes_value):
    """Extract human-readable notes from plain text or structured JSON notes."""
    parsed = parse_donation_notes_json(notes_value)
    if not parsed:
        return (notes_value or '').strip() if isinstance(notes_value, str) else ''

    note_text = str(parsed.get('note_text') or parsed.get('notes') or '').strip()
    workflow_notes = parsed.get('workflow_notes')
    if isinstance(workflow_notes, list):
        workflow_notes = [str(item).strip() for item in workflow_notes if str(item).strip()]
    else:
        workflow_notes = []

    parts = []
    if note_text:
        parts.append(note_text)
    if workflow_notes:
        parts.append("\n".join(workflow_notes))
    return "\n".join(parts).strip()


def build_secure_donation_notes(payload_data, display_notes=''):
    """Create notes JSON with encrypted payload and plaintext SHA-256 hash."""
    payload = payload_data if isinstance(payload_data, dict) else {}
    note_text = (display_notes or '').strip()

    try:
        donor_plain = json.dumps(payload, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
        enc = encrypt_payload(donor_plain)
        payload_hash = sha256_hex(donor_plain)

        notes_obj = {'enc': enc, 'plaintext_sha256': payload_hash}
        if note_text:
            notes_obj['note_text'] = note_text
        return json.dumps(notes_obj, ensure_ascii=False)
    except Exception as e:
        print(f"Error building secure donation notes: {e}")
        return note_text or None


def append_workflow_note(existing_notes, workflow_entry):
    """Append workflow notes while preserving legacy and structured note formats."""
    entry = (workflow_entry or '').strip()
    if not entry:
        if isinstance(existing_notes, dict):
            return json.dumps(existing_notes, ensure_ascii=False)
        return existing_notes or ''

    parsed = parse_donation_notes_json(existing_notes)
    if parsed and parsed.get('plaintext_sha256'):
        updated = dict(parsed)
        workflow_notes = updated.get('workflow_notes')
        if isinstance(workflow_notes, list):
            workflow_notes = [str(item).strip() for item in workflow_notes if str(item).strip()]
        else:
            workflow_notes = []
        workflow_notes.append(entry)
        updated['workflow_notes'] = workflow_notes
        return json.dumps(updated, ensure_ascii=False)

    existing = (existing_notes or '').strip()
    if not existing:
        return entry
    return f"{existing}\n{entry}"


def get_verified_qr_receipts():
    verified = session.get(QR_RECEIPT_VERIFICATION_SESSION_KEY, {})
    return verified if isinstance(verified, dict) else {}


def is_qr_receipt_verified(refnum):
    return refnum in get_verified_qr_receipts()


def mark_qr_receipt_verified(refnum, method, screenshot_filename=None):
    verified = get_verified_qr_receipts()
    verified[refnum] = {
        'method': method,
        'verified_at': datetime.now().isoformat(),
        'screenshot_filename': screenshot_filename
    }
    session[QR_RECEIPT_VERIFICATION_SESSION_KEY] = verified
    session.modified = True


def rename_verified_qr_receipt(old_refnum, new_refnum):
    verified = get_verified_qr_receipts()
    if old_refnum in verified:
        verified[new_refnum] = verified.pop(old_refnum)
        session[QR_RECEIPT_VERIFICATION_SESSION_KEY] = verified
        session.modified = True


def update_donation_reference_number(donation_id, old_refnum, new_refnum, conn=None, cursor=None):
    sanitized_refnum = (new_refnum or '').strip()
    old_refnum = (old_refnum or '').strip()

    if not sanitized_refnum:
        return old_refnum

    if sanitized_refnum == old_refnum:
        return old_refnum

    owns_connection = conn is None or cursor is None
    if owns_connection:
        conn = get_db_connection()
        cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT don_refnum
            FROM donations
            WHERE don_id = %s
            LIMIT 1
        """, (donation_id,))
        current_row = cursor.fetchone()

        if not current_row:
            raise ValueError(f"Donation {donation_id} not found while updating reference number.")

        current_refnum = (
            current_row.get('don_refnum')
            if isinstance(current_row, dict)
            else current_row[0]
        ) or old_refnum

        cursor.execute("""
            UPDATE donations
            SET don_refnum = %s
            WHERE don_id = %s
        """, (sanitized_refnum, donation_id))

        if cursor.rowcount <= 0 and sanitized_refnum != current_refnum:
            raise ValueError(f"Failed to update don_refnum for donation {donation_id}.")

        conn.commit()

        print(
            f"[DONATION VERIFICATION] Updated donations.don_refnum "
            f"for don_id={donation_id} from '{current_refnum}' to '{sanitized_refnum}'"
        )

        try:
            cursor.execute("""
                UPDATE donation_fund_status
                SET reference_number = %s
                WHERE reference_number = %s
            """, (sanitized_refnum, current_refnum))

            cursor.execute("""
                UPDATE donation_fund_status_history
                SET reference_number = %s
                WHERE reference_number = %s
            """, (sanitized_refnum, current_refnum))

            cursor.execute("""
                UPDATE payload_history
                SET don_refnum = %s
                WHERE donation_id = %s OR don_refnum = %s
            """, (sanitized_refnum, donation_id, current_refnum))

            log_audit_event(
                action='DONATION_REFERENCE_UPDATED',
                entity_type='donation',
                entity_id=sanitized_refnum,
                before_data={'don_id': donation_id, 'don_refnum': current_refnum},
                after_data={'don_id': donation_id, 'don_refnum': sanitized_refnum},
                metadata={'source': 'donation_verification'},
                conn=conn,
                cursor=cursor
            )
            conn.commit()
        except Exception as related_error:
            print(
                f"[DONATION VERIFICATION] Related reference sync failed for "
                f"don_id={donation_id}: {related_error}"
            )

        rename_verified_qr_receipt(current_refnum, sanitized_refnum)
        return sanitized_refnum
    except Exception:
        if owns_connection:
            conn.rollback()
        raise
    finally:
        if owns_connection:
            cursor.close()
            conn.close()

def amount_in_words(amount):
    """Convert a numeric amount to words in English (for Philippine Peso)"""
    if amount is None:
        return "Zero Pesos Only"
    
    # Handle float amounts
    if isinstance(amount, float):
        amount = round(amount, 2)
        pesos = int(amount)
        centavos = int(round((amount - pesos) * 100))
    else:
        pesos = int(amount)
        centavos = 0
    
    if pesos == 0 and centavos == 0:
        return "Zero Pesos Only"
    
    ones = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine"]
    teens = ["Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen", 
            "Seventeen", "Eighteen", "Nineteen"]
    tens = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]
    
    def convert_hundreds(num):
        """Convert a number less than 1000 to words"""
        if num == 0:
            return ""
        
        result = ""
        if num >= 100:
            result += ones[num // 100] + " Hundred"
            num %= 100
            if num > 0:
                result += " "
        
        if num >= 20:
            result += tens[num // 10]
            if num % 10 > 0:
                result += " " + ones[num % 10]
        elif num >= 10:
            result += teens[num - 10]
        elif num > 0:
            result += ones[num]
        
        return result
    
    def convert_number(num):
        """Convert a number to words"""
        if num == 0:
            return "Zero"
        
        result = ""
        
        # Billions
        if num >= 1000000000:
            billions = num // 1000000000
            result += convert_hundreds(billions) + " Billion"
            num %= 1000000000
            if num > 0:
                result += " "
        
        # Millions
        if num >= 1000000:
            millions = num // 1000000
            result += convert_hundreds(millions) + " Million"
            num %= 1000000
            if num > 0:
                result += " "
        
        # Thousands
        if num >= 1000:
            thousands = num // 1000
            result += convert_hundreds(thousands) + " Thousand"
            num %= 1000
            if num > 0:
                result += " "
        
        # Hundreds, Tens, Ones
        if num > 0:
            result += convert_hundreds(num)
        
        return result.strip()
    
    pesos_words = convert_number(pesos)
    
    if centavos > 0:
        centavos_words = convert_number(centavos)
        return f"{pesos_words} Pesos and {centavos_words} Centavos Only"
    else:
        return f"{pesos_words} Pesos Only"

# Register as Jinja2 template filter
@app.template_filter('amount_in_words')
def amount_in_words_filter(amount):
    return amount_in_words(amount)

# Make amount_in_words available as a function in templates
@app.context_processor
def inject_amount_in_words():
    return dict(amount_in_words=amount_in_words)


# --------------------------------------------------------------------------
# -------------------------------- FUNDRAISERS -----------------------------
# --------------------------------------------------------------------------

@app.route('/')
def index():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    if 'email' in session:
        cursor.execute("SELECT id, name FROM users WHERE email = %s", (session['email'],))
        user = cursor.fetchone()
        user_id = user['id'] if user else None
    else:
        user_id = None
    
    if user_id:
        cursor.execute(
            """
            SELECT f.fund_id, f.fund_title, f.fund_img, f.fund_goalamount, f.fund_status,
                f.fund_category, COALESCE(SUM(CASE WHEN d.don_status = 'Paid' THEN d.don_amount ELSE 0 END), 0) AS total_raised
            FROM fundraisers f
            LEFT JOIN donations d
                ON f.fund_id = d.fund_id AND d.don_status = 'Paid'
            WHERE f.fund_creatorid != %s AND f.fund_status IN ('Active', 'Completed')
            GROUP BY f.fund_id
            ORDER BY RAND()
            LIMIT 8
            """,
            (user_id,)
        )
    else:
        cursor.execute(
            """
            SELECT f.fund_id, f.fund_title, f.fund_img, f.fund_goalamount, f.fund_status,
                f.fund_category, COALESCE(SUM(CASE WHEN d.don_status = 'Paid' THEN d.don_amount ELSE 0 END), 0) AS total_raised
            FROM fundraisers f
            LEFT JOIN donations d
                ON f.fund_id = d.fund_id AND d.don_status = 'Paid'
            WHERE f.fund_status IN ('Active', 'Completed')
            GROUP BY f.fund_id
            ORDER BY RAND()
            LIMIT 8
            """
        )
    
    campaigns = cursor.fetchall()
    cursor.close()
    conn.close()
    settings = get_all_settings()
    return render_template('landing.html', campaigns=campaigns, user=user if 'email' in session else None, settings=settings)

@app.route('/home')
def home():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    if 'email' in session:
        cursor.execute("SELECT id, name FROM users WHERE email = %s", (session['email'],))
        user = cursor.fetchone()
        user_id = user['id'] if user else None
    else:
        user = None
        user_id = None
    
    if user_id:
        cursor.execute(
            """
            SELECT f.fund_id, f.fund_title, f.fund_img, f.fund_goalamount, f.fund_status,
                f.fund_category, COALESCE(SUM(CASE WHEN d.don_status = 'Paid' THEN d.don_amount ELSE 0 END), 0) AS total_raised
            FROM fundraisers f
            LEFT JOIN donations d
                ON f.fund_id = d.fund_id AND d.don_status = 'Paid'
            WHERE f.fund_creatorid != %s AND f.fund_status IN ('Active', 'Completed')
            GROUP BY f.fund_id
            ORDER BY RAND() DESC
            LIMIT 8
            """,
            (user_id,)
        )
    else:
        cursor.execute(
            """
            SELECT f.fund_id, f.fund_title, f.fund_img, f.fund_goalamount, f.fund_status,
                f.fund_category, COALESCE(SUM(CASE WHEN d.don_status = 'Paid' THEN d.don_amount ELSE 0 END), 0) AS total_raised
            FROM fundraisers f
            LEFT JOIN donations d
                ON f.fund_id = d.fund_id AND d.don_status = 'Paid'
            WHERE f.fund_status IN ('Active', 'Completed')
            GROUP BY f.fund_id
            ORDER BY RAND() DESC
            LIMIT 8
            """
        )
    
    campaigns = cursor.fetchall()
    cursor.close()
    conn.close()
    settings = get_all_settings()
    return render_template('landing.html', campaigns=campaigns, user=user if 'email' in session else None, settings=settings)

@app.route('/about')
def about():
    settings = get_all_settings()
    return render_template('about.html', settings=settings)

@app.route('/terms-and-conditions')
def terms_and_conditions():
    return render_template('terms_and_conditions.html')

@app.route('/privacy-notice')
def privacy_notice():
    return render_template('privacy_notice.html')

@app.route('/fundraisers')
def fundraisers():
    page = request.args.get('page', 1, type=int)
    search_query = request.args.get('q', '').strip()
    sort = normalize_fundraiser_sort(request.args.get('sort', 'popular').strip().lower())
    per_page = 8
    campaigns, pagination_info = get_fundraiser_listing(search_query, sort, page, per_page)
    settings = get_all_settings()
    return render_template(
        'fundraisers.html',
        campaigns=campaigns,
        pagination=pagination_info,
        search_query=search_query,
        selected_sort=sort,
        settings=settings
    )

@app.route('/api/fundraisers', methods=['GET'])
def api_fundraisers():
    page = request.args.get('page', 1, type=int)
    search_query = request.args.get('q', '').strip()
    sort = normalize_fundraiser_sort(request.args.get('sort', 'popular').strip().lower())
    per_page = request.args.get('per_page', 8, type=int)
    per_page = min(max(per_page, 1), 24)
    campaigns, pagination_info = get_fundraiser_listing(search_query, sort, page, per_page)

    serialized_campaigns = []
    for campaign in campaigns:
        goal = float(campaign.get('fund_goalamount') or 0)
        raised = float(campaign.get('total_raised') or 0)
        pct = 100 if campaign.get('fund_status') == 'Completed' else ((raised / goal * 100) if goal > 0 else 0)
        pct = min(pct, 100)
        image_data = b64encode_filter(campaign.get('fund_img'))

        serialized_campaigns.append({
            'fund_id': campaign.get('fund_id'),
            'fund_title': campaign.get('fund_title'),
            'fund_category': campaign.get('fund_category'),
            'fund_goalamount': goal,
            'fund_status': campaign.get('fund_status'),
            'fund_startdate': campaign.get('fund_startdate').isoformat() if campaign.get('fund_startdate') else None,
            'total_raised': raised,
            'donation_count': int(campaign.get('donation_count') or 0),
            'progress_pct': round(pct),
            'image_url': f"data:image/png;base64,{image_data}" if image_data else url_for('static', filename='images/placeholder_img.png'),
            'view_url': url_for('view_fundraiser', fundraiser_id=campaign.get('fund_id')),
            'donate_url': url_for('donate', fundraiser_id=campaign.get('fund_id'))
        })

    return jsonify({
        'campaigns': serialized_campaigns,
        'pagination': pagination_info,
        'search_query': search_query,
        'sort': normalize_fundraiser_sort(sort)
    })

def normalize_fundraiser_sort(sort):
    allowed_sorts = {'popular', 'most_donated', 'most_supported', 'newest', 'oldest', 'random'}
    return sort if sort in allowed_sorts else 'popular'

def get_fundraiser_order_clause(sort):
    sort = normalize_fundraiser_sort(sort)
    if sort == 'newest':
        return "f.fund_startdate DESC, f.fund_id DESC"
    if sort == 'oldest':
        return "f.fund_startdate ASC, f.fund_id ASC"
    if sort == 'most_supported':
        return "donation_count DESC, total_raised DESC, f.fund_startdate DESC"
    if sort == 'random':
        return "RAND()"
    return "total_raised DESC, donation_count DESC, f.fund_startdate DESC"

def get_fundraiser_listing(search_query='', sort='popular', page=1, per_page=8):
    page = max(page, 1)
    offset = (page - 1) * per_page
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    base_where = "WHERE f.fund_status IN ('Active', 'Completed')"
    search_where = ""
    search_params = []
    
    if search_query:
        search_where = " AND (f.fund_title LIKE %s OR f.fund_desc LIKE %s OR f.fund_beneficiary LIKE %s)"
        search_params = [f"%{search_query}%", f"%{search_query}%", f"%{search_query}%"]
    
    count_query = f"SELECT COUNT(*) as total FROM fundraisers f {base_where}{search_where}"
    cursor.execute(count_query, search_params)
    total_campaigns = cursor.fetchone()['total']
    
    order_clause = get_fundraiser_order_clause(sort)
    
    campaigns_query = f"""
        SELECT f.fund_id, f.fund_title, f.fund_img, f.fund_goalamount, f.fund_status,
            f.fund_category, f.fund_startdate,
            COALESCE(SUM(CASE WHEN d.don_status = 'Paid' THEN d.don_amount ELSE 0 END), 0) AS total_raised,
            COUNT(d.don_id) AS donation_count
        FROM fundraisers f
        LEFT JOIN donations d
            ON f.fund_id = d.fund_id AND d.don_status = 'Paid'
        {base_where}{search_where}
        GROUP BY f.fund_id
        ORDER BY {order_clause}
        LIMIT %s OFFSET %s
    """
    
    cursor.execute(campaigns_query, search_params + [per_page, offset])
    campaigns = cursor.fetchall()
    
    total_pages = (total_campaigns + per_page - 1) // per_page
    has_prev = page > 1
    has_next = page < total_pages
    
    pagination_info = {
        'page': page,
        'per_page': per_page,
        'total': total_campaigns,
        'total_pages': total_pages,
        'has_prev': has_prev,
        'has_next': has_next,
        'prev_num': page - 1 if has_prev else None,
        'next_num': page + 1 if has_next else None
    }
    cursor.close()
    conn.close()
    return campaigns, pagination_info

@app.route('/search')
def search():
    query = request.args.get('q', '').strip()
    if not query:
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    search_query = f"%{query}%"
    cursor.execute(
        """
        SELECT f.fund_id, f.fund_title, f.fund_img, f.fund_goalamount, f.fund_status,
            f.fund_category, COALESCE(SUM(CASE WHEN d.don_status = 'Paid' THEN d.don_amount ELSE 0 END), 0) AS total_raised
        FROM fundraisers f
        LEFT JOIN donations d
            ON f.fund_id = d.fund_id AND d.don_status = 'Paid'
        WHERE f.fund_title LIKE %s 
            OR f.fund_desc LIKE %s 
            OR f.fund_beneficiary LIKE %s
        AND f.fund_status IN ('Active', 'Completed')
        GROUP BY f.fund_id
        ORDER BY f.fund_startdate DESC
        LIMIT 20
        """,
        (search_query, search_query, search_query)
    )
    campaigns = cursor.fetchall()
    cursor.close()
    conn.close()
    settings = get_all_settings()
    
    return render_template('landing.html', campaigns=campaigns, search_query=query, is_search=True, settings=settings)


# -----------------------------------------------------------------------
# -------------------------------- DONATE -------------------------------
# -----------------------------------------------------------------------

@app.route('/donate/<int:fundraiser_id>')
def donate(fundraiser_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM fundraisers WHERE fund_id = %s", (fundraiser_id,))
    fund = cursor.fetchone()

    if not fund:
        return "Fundraiser not found", 404

    cursor.execute(
        """
        SELECT COALESCE(SUM(CASE WHEN don_status = 'Paid' THEN don_amount ELSE 0 END), 0) AS total_raised
        FROM donations
        WHERE fund_id = %s AND don_status = 'Paid'
        """,
        (fundraiser_id,)
    )
    raised_data = cursor.fetchone()
    total_raised = float(raised_data['total_raised']) if raised_data['total_raised'] else 0
    goal_amount = float(fund['fund_goalamount']) if fund['fund_goalamount'] else 0
    remaining_amount = max(0, goal_amount - total_raised)

    saved_payment_methods = []
    if session.get('email'):
        cursor.execute(
            """
            SELECT id, method_type, account_name, account_number, is_default, date_added
            FROM payment_methods
            WHERE user_id = (SELECT id FROM users WHERE email = %s)
            ORDER BY is_default DESC, date_added DESC
            """,
            (session['email'],)
        )
        saved_payment_methods = cursor.fetchall()

    settings = get_all_settings()
    cursor.close()
    conn.close()
    response = make_response(render_template(
        'donate.html',
        fund=fund,
        settings=settings,
        saved_payment_methods=saved_payment_methods,
        total_raised=total_raised,
        goal_amount=goal_amount,
        remaining_amount=remaining_amount
    ))
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@app.route('/donate/saved-method', methods=['POST'])
def donate_saved_method():
    if 'email' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        data = request.get_json()
        amount = data.get('amount')
        fundraiser_id = data.get('fundraiser_id')
        donor_id = data.get('donor_id', None)
        donor_name = data.get('donor_name', 'Anonymous')
        donor_email = data.get('donor_email', None)
        payment_method_id = data.get('payment_method_id')
        
        if not amount or not fundraiser_id or not payment_method_id:
            return jsonify({'error': 'Missing required fields'}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("""
            SELECT pm.* FROM payment_methods pm
            JOIN users u ON u.id = pm.user_id
            WHERE pm.id = %s AND u.email = %s
        """, (payment_method_id, session['email']))
        payment_method = cursor.fetchone()
        
        if not payment_method:
            cursor.close()
            conn.close()
            return jsonify({'error': 'Payment method not found'}), 404
        
        # In a real implementation, you'd integrate with the payment provider's saved method API
        cursor.close()
        conn.close()
        
        return jsonify({
            'checkout_url': f'/paymongo/gcash?saved_method={payment_method_id}',
            'saved_method': payment_method
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/paymongo/gcash', methods=['POST'])
def paymongo_gcash():
    data = request.get_json()
    amount = data.get('amount')
    fundraiser_id = data.get('fundraiser_id')
    donor_id = data.get('donor_id', None)
    donor_name = data.get('donor_name', 'Anonymous')
    donor_email = data.get('donor_email', None)

    if not amount or not fundraiser_id:
        return jsonify({'error': 'Missing amount or fundraiser ID'}), 400

    url = "https://api.paymongo.com/v1/checkout_sessions"
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "authorization": "Basic " + auth_header
    }
    
    refnum = generate_reference_number()
    
    payload = {
        "data": {
            "attributes": {
                "line_items": [
                    {
                        "currency": "PHP",
                        "amount": int(amount),
                        "name": f"Donation to Fundraiser {fundraiser_id}",
                        "quantity": 1
                    }
                ],
                "payment_method_types": ["gcash"],
                "success_url": url_for('donation_confirmation', fundraiser_id=fundraiser_id, donation_ref=refnum, _external=True),
                "cancel_url": url_for('donate', fundraiser_id=fundraiser_id, _external=True),
                "metadata": {
                    "fundraiser_id": fundraiser_id,
                    "donor_name": donor_name,
                    "donor_email": donor_email
                }
            }
        }
    }

    resp = requests.post(url, headers=headers, json=payload)

    if resp.status_code in (200, 201):
        checkout_url = resp.json()['data']['attributes']['checkout_url']

        donor_wallet = get_user_wallet_address(donor_id)
        
        refnum, donation_id = insert_donation(
            fund_id=fundraiser_id,
            donor_id=donor_id,
            donor_name=donor_name,
            receiver="Fundraiser Org",  # REVISE
            paymethod="GCash",
            amount=int(amount),
            refnum=refnum,
            donor_wallet=donor_wallet
        )

        return jsonify({'checkout_url': checkout_url, 'refnum': refnum})
    else:
        print("PayMongo error:", resp.text)
        return jsonify({'error': 'PayMongo error', 'details': resp.text}), 500

def get_country_iso_code(country_name):
    """Convert country name to ISO 3166-1 alpha-2 country code"""
    country_mapping = {
        'philippines': 'PH',
        'ph': 'PH',
        'united states': 'US',
        'usa': 'US',
        'united kingdom': 'GB',
        'uk': 'GB',
        'canada': 'CA',
        'australia': 'AU',
        'singapore': 'SG',
        'malaysia': 'MY',
        'indonesia': 'ID',
        'thailand': 'TH',
        'vietnam': 'VN',
        'japan': 'JP',
        'south korea': 'KR',
        'china': 'CN',
        'hong kong': 'HK',
        'taiwan': 'TW',
        'india': 'IN',
        'new zealand': 'NZ',
        'france': 'FR',
        'germany': 'DE',
        'italy': 'IT',
        'spain': 'ES',
        'netherlands': 'NL',
        'belgium': 'BE',
        'switzerland': 'CH',
        'austria': 'AT',
        'sweden': 'SE',
        'norway': 'NO',
        'denmark': 'DK',
        'finland': 'FI',
        'poland': 'PL',
        'portugal': 'PT',
        'greece': 'GR',
        'ireland': 'IE',
        'brazil': 'BR',
        'mexico': 'MX',
        'argentina': 'AR',
        'chile': 'CL',
        'colombia': 'CO',
        'peru': 'PE',
        'south africa': 'ZA',
        'egypt': 'EG',
        'saudi arabia': 'SA',
        'uae': 'AE',
        'united arab emirates': 'AE',
        'israel': 'IL',
        'turkey': 'TR',
        'russia': 'RU',
    }
    
    if not country_name:
        return 'PH'  # Default to Philippines
    
    country_lower = country_name.strip().lower()
    
    if len(country_lower) == 2 and country_lower.isalpha():
        return country_lower.upper()
    
    # Look up in mapping
    return country_mapping.get(country_lower, 'PH')

@app.route('/paymongo/credit-card', methods=['POST'])
def paymongo_credit_card():
    try:
        data = request.get_json()
        amount = data.get('amount')
        fundraiser_id = data.get('fundraiser_id')
        donor_id = data.get('donor_id', None)
        donor_name = data.get('donor_name', 'Anonymous')
        donor_email = data.get('donor_email', None)
        card_details = data.get('card_details', {})

        if not amount or not fundraiser_id:
            return jsonify({'error': 'Missing amount or fundraiser ID'}), 400

        if not card_details or not card_details.get('number') or not card_details.get('expiry') or not card_details.get('cvv'):
            return jsonify({'error': 'Card details are required'}), 400

        try:
            amount_int = int(amount)
            if amount_int < 100:
                return jsonify({'error': 'Amount must be at least ₱1.00'}), 400
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid amount format'}), 400

        headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "authorization": "Basic " + auth_header
        }

        refnum = generate_reference_number()
        
        intent_url = "https://api.paymongo.com/v1/payment_intents"
        intent_payload = {
            "data": {
                "attributes": {
                    "amount": amount_int,
                    "currency": "PHP",
                    "payment_method_allowed": ["card"],
                    "metadata": {
                        "fundraiser_id": str(fundraiser_id),
                        "donor_name": donor_name,
                        "donor_email": donor_email or "",
                        "donor_id": str(donor_id) if donor_id else "",
                        "reference": refnum
                    }
                }
            }
        }

        intent_resp = requests.post(intent_url, headers=headers, json=intent_payload, timeout=30)
        
        if intent_resp.status_code not in (200, 201):
            error_text = intent_resp.text
            print(f"PayMongo Payment Intent error (Status {intent_resp.status_code}): {error_text}")
            try:
                error_data = intent_resp.json()
                error_message = error_data.get('errors', [{}])[0].get('detail', 'Failed to create payment intent')
            except:
                error_message = 'Failed to create payment intent. Please try again.'
            return jsonify({'error': 'Payment gateway error', 'details': error_message}), 500

        intent_data = intent_resp.json()
        client_key = intent_data.get('data', {}).get('attributes', {}).get('client_key')
        payment_intent_id = intent_data.get('data', {}).get('id')
        
        if not payment_intent_id:
            return jsonify({'error': 'Invalid response from payment gateway', 'details': 'Missing payment intent ID'}), 500

        method_url = "https://api.paymongo.com/v1/payment_methods"
        
        expiry = card_details.get('expiry', '').replace('/', '').replace(' ', '')
        if len(expiry) != 4:
            return jsonify({'error': 'Invalid expiry date format'}), 400
        
        expiry_month = expiry[:2]
        expiry_year = '20' + expiry[2:]
        
        billing_address = {}
        if card_details.get('postal_code'):
            billing_address['postal_code'] = card_details.get('postal_code')
        
        country = card_details.get('country', 'Philippines')
        country_code = get_country_iso_code(country)
        billing_address['country'] = country_code

        method_payload = {
            "data": {
                "attributes": {
                    "type": "card",
                    "details": {
                        "card_number": card_details.get('number', '').replace(' ', ''),
                        "exp_month": int(expiry_month),
                        "exp_year": int(expiry_year),
                        "cvc": card_details.get('cvv')
                    },
                    "billing": {
                        "name": card_details.get('name') or f"{card_details.get('first_name', '')} {card_details.get('last_name', '')}".strip(),
                        "email": card_details.get('email') or donor_email,
                        "address": billing_address
                    }
                }
            }
        }

        method_resp = requests.post(method_url, headers=headers, json=method_payload, timeout=30)
        
        if method_resp.status_code not in (200, 201):
            error_text = method_resp.text
            print(f"PayMongo Payment Method error (Status {method_resp.status_code}): {error_text}")
            try:
                error_data = method_resp.json()
                error_message = error_data.get('errors', [{}])[0].get('detail', 'Failed to create payment method')
            except:
                error_message = 'Failed to process card details. Please check your card information and try again.'
            return jsonify({'error': 'Payment gateway error', 'details': error_message}), 500

        method_data = method_resp.json()
        payment_method_id = method_data.get('data', {}).get('id')
        
        if not payment_method_id:
            return jsonify({'error': 'Invalid response from payment gateway', 'details': 'Missing payment method ID'}), 500

        attach_url = f"https://api.paymongo.com/v1/payment_intents/{payment_intent_id}/attach"
        attach_payload = {
            "data": {
                "attributes": {
                    "payment_method": payment_method_id,
                    "return_url": url_for('donation_confirmation', fundraiser_id=fundraiser_id, donation_ref=refnum, _external=True)
                }
            }
        }

        attach_resp = requests.post(attach_url, headers=headers, json=attach_payload, timeout=30)
        
        if attach_resp.status_code not in (200, 201):
            error_text = attach_resp.text
            print(f"PayMongo Attach error (Status {attach_resp.status_code}): {error_text}")
            try:
                error_data = attach_resp.json()
                error_message = error_data.get('errors', [{}])[0].get('detail', 'Failed to process payment')
            except:
                error_message = 'Failed to process payment. Please try again.'
            return jsonify({'error': 'Payment gateway error', 'details': error_message}), 500

        attach_data = attach_resp.json()
        payment_status = attach_data.get('data', {}).get('attributes', {}).get('status')
        next_action = attach_data.get('data', {}).get('attributes', {}).get('next_action')
        
        if next_action and next_action.get('type') == 'redirect':
            redirect_url = next_action.get('redirect', {}).get('url')
            if redirect_url:
                donor_wallet = get_user_wallet_address(donor_id)
                
                refnum, donation_id = insert_donation(
                    fund_id=fundraiser_id,
                    donor_id=donor_id,
                    donor_name=donor_name,
                    receiver="Fundraiser Org",
                    paymethod="Credit Card",
                    amount=amount_int,
                    refnum=refnum,
                    donor_wallet=donor_wallet
                )
                
                return jsonify({
                    'checkout_url': redirect_url,
                    'refnum': refnum,
                    'requires_3ds': True,
                    'message': '3D Secure authentication required. Redirecting...'
                })
        
        if payment_status == 'succeeded':
            donor_wallet = get_user_wallet_address(donor_id)
            
            refnum, donation_id = insert_donation(
                fund_id=fundraiser_id,
                donor_id=donor_id,
                donor_name=donor_name,
                receiver="Fundraiser Org",
                paymethod="Credit Card",
                amount=amount_int,
                refnum=refnum,
                donor_wallet=donor_wallet
            )
            
            status_updated = update_donation_status(refnum, 'Paid')
            if not status_updated:
                return jsonify({
                    'success': False,
                    'error': 'Payment completed, but donation finalization failed because blockchain recording did not succeed.'
                }), 502
            
            return jsonify({
                'success': True,
                'refnum': refnum,
                'status': 'succeeded',
                'redirect_url': url_for('donation_confirmation', fundraiser_id=fundraiser_id, donation_ref=refnum, _external=True),
                'message': 'Payment processed successfully!'
            })
        else:
            return jsonify({
                'success': False,
                'status': payment_status,
                'error': 'Payment is pending. Please try again.'
            }), 400
            
    except requests.exceptions.RequestException as e:
        print(f"Network error connecting to PayMongo: {e}")
        return jsonify({
            'error': 'Network error', 
            'details': 'Unable to connect to payment gateway. Please check your internet connection and try again.'
        }), 500
    except Exception as e:
        print(f"Unexpected error in credit card payment: {e}")
        traceback.print_exc()
        return jsonify({
            'error': 'Payment processing error', 
            'details': str(e)
        }), 500

@app.route('/paymongo/qrph', methods=['POST'])
def paymongo_qrph():
    try:
        payment_intent_id = None
        data = request.get_json()
        amount = data.get('amount')
        fundraiser_id = data.get('fundraiser_id')
        donor_id = data.get('donor_id', None)
        session_name = (session.get('username') or '').strip()
        session_email = (session.get('email') or '').strip()
        donor_name = session_name or (data.get('donor_name') or '').strip() or 'Anonymous'
        donor_email = session_email or (data.get('donor_email') or '').strip() or 'none@example.com'
        billing = data.get('billing', {}) or {}

        if not amount or not fundraiser_id:
            return jsonify({'error': 'Missing amount or fundraiser ID'}), 400

        billing_name = (billing.get('name') or donor_name or 'Anonymous').strip()
        billing_email = (billing.get('email') or donor_email or 'none@example.com').strip()

        try:
            amount_int = int(amount)
            if amount_int < 100:
                return jsonify({'error': 'Amount must be at least PHP 1.00'}), 400
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid amount format'}), 400

        headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "authorization": "Basic " + auth_header
        }

        metadata = {
            "fundraiser_id": str(fundraiser_id),
            "donor_name": donor_name,
            "donor_email": billing_email,
            "donor_id": str(donor_id) if donor_id else "",
            "payment_method": "QRPH"
        }

        intent_url = "https://api.paymongo.com/v1/payment_intents"
        intent_payload = {
            "data": {
                "attributes": {
                    "amount": amount_int,
                    "currency": "PHP",
                    "payment_method_allowed": ["card", "dob", "paymaya", "qrph"],
                    "metadata": metadata
                }
            }
        }

        intent_resp = requests.post(intent_url, headers=headers, json=intent_payload, timeout=30)

        if intent_resp.status_code not in (200, 201):
            error_text = intent_resp.text
            print(f"PayMongo QRPH Payment Intent error (Status {intent_resp.status_code}): {error_text}")
            try:
                error_data = intent_resp.json()
                error_message = error_data.get('errors', [{}])[0].get('detail', 'Failed to create QRPH payment intent')
            except Exception:
                error_message = 'Failed to create QRPH payment intent. Please try again.'
            return jsonify({'error': 'Payment gateway error', 'details': error_message}), 500

        payment_intent_id = intent_resp.json().get('data', {}).get('id')

        if not payment_intent_id:
            return jsonify({'error': 'Invalid response from payment gateway', 'details': 'Missing payment intent ID'}), 500

        refnum = generate_pending_qr_reference(payment_intent_id)

        method_billing = {
            "name": billing_name,
            "email": billing_email
        }

        phone = (billing.get('phone') or '').strip()
        if phone:
            method_billing["phone"] = phone

        address = billing.get('address') or {}
        if isinstance(address, dict):
            clean_address = {key: value for key, value in address.items() if value}
            if clean_address:
                method_billing["address"] = clean_address

        method_url = "https://api.paymongo.com/v1/payment_methods"
        method_payload = {
            "data": {
                "attributes": {
                    "type": "qrph",
                    "billing": method_billing
                }
            }
        }

        method_resp = requests.post(method_url, headers=headers, json=method_payload, timeout=30)

        if method_resp.status_code not in (200, 201):
            error_text = method_resp.text
            print(f"PayMongo QRPH Payment Method error (Status {method_resp.status_code}): {error_text}")
            try:
                error_data = method_resp.json()
                error_message = error_data.get('errors', [{}])[0].get('detail', 'Failed to create QRPH payment method')
            except Exception:
                error_message = 'Failed to create QRPH payment method. Please try again.'
            return jsonify({'error': 'Payment gateway error', 'details': error_message}), 500

        payment_method_id = method_resp.json().get('data', {}).get('id')

        if not payment_method_id:
            return jsonify({'error': 'Invalid response from payment gateway', 'details': 'Missing payment method ID'}), 500

        attach_url = f"https://api.paymongo.com/v1/payment_intents/{payment_intent_id}/attach"
        attach_payload = {
            "data": {
                "attributes": {
                    "payment_method": payment_method_id
                }
            }
        }

        attach_resp = requests.post(attach_url, headers=headers, json=attach_payload, timeout=30)

        if attach_resp.status_code not in (200, 201):
            error_text = attach_resp.text
            print(f"PayMongo QRPH Attach error (Status {attach_resp.status_code}): {error_text}")
            try:
                error_data = attach_resp.json()
                error_message = error_data.get('errors', [{}])[0].get('detail', 'Failed to attach QRPH payment method')
            except Exception:
                error_message = 'Failed to prepare QRPH payment. Please try again.'
            return jsonify({'error': 'Payment gateway error', 'details': error_message}), 500

        attach_data = attach_resp.json()
        attributes = attach_data.get('data', {}).get('attributes', {})
        payment_status = attributes.get('status')
        next_action = attributes.get('next_action') or {}
        qr_code = next_action.get('code') or {}
        qr_image_url = qr_code.get('image_url')

        if payment_status != 'awaiting_next_action' or next_action.get('type') != 'consume_qr' or not qr_image_url:
            return jsonify({
                'error': 'Invalid QRPH response from payment gateway',
                'details': 'QR code was not returned by PayMongo.'
            }), 500

        donor_wallet = get_user_wallet_address(donor_id)
        refnum, donation_id = insert_donation(
            fund_id=fundraiser_id,
            donor_id=donor_id,
            donor_name=donor_name,
            receiver="Fundraiser Org",
            paymethod="QRPH",
            amount=amount_int,
            refnum=refnum,
            donor_wallet=donor_wallet,
            payment_intent_id=payment_intent_id
        )

        QRPH_PAYMENT_CODES[donation_id] = {
            'image_url': qr_image_url,
            'qr_code_id': qr_code.get('id'),
            'label': qr_code.get('label'),
            'payment_intent_id': payment_intent_id,
            'fundraiser_id': fundraiser_id,
            'created_at': datetime.now()
        }

        return jsonify({
            'success': True,
            'status': payment_status,
            'refnum': '',
            'reference_pending': True,
            'donation_id': donation_id,
            'payment_intent_id': payment_intent_id,
            'qr_code_image_url': qr_image_url,
            'qr_code_id': qr_code.get('id'),
            'qr_label': qr_code.get('label'),
            'expires_in_minutes': 30,
            'qr_page_url': url_for('qrph_payment_page', donation_id=donation_id, _external=True),
            'status_url': url_for('check_donation_status_by_id', donation_id=donation_id, _external=True),
            'verification_url': url_for('donation_verification', fundraiser_id=fundraiser_id, donation_id=donation_id, _external=True),
            'confirmation_url': None
        })

    except requests.exceptions.RequestException as e:
        print(f"Network error connecting to PayMongo QRPH: {e}")
        return jsonify({
            'error': 'Network error',
            'details': 'Unable to connect to payment gateway. Please check your internet connection and try again.'
        }), 500
    except Exception as e:
        print(f"Unexpected error in QRPH payment: {e}")
        traceback.print_exc()
        return jsonify({
            'error': 'Payment processing error',
            'details': str(e)
        }), 500
    
def generate_reference_number():
    today = datetime.now()
    date_str = today.strftime("%y%m%d")
    
    code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    
    return f"REL-{date_str}-{code}"


def generate_pending_qr_reference(payment_intent_id=None):
    suffix = (payment_intent_id or uuid.uuid4().hex).replace('-', '')[:18].upper()
    return f"QRPH-PENDING-{suffix}"

def insert_donation(fund_id, donor_id, donor_name, receiver, paymethod, amount, refnum=None, donor_wallet=None, payment_intent_id=None):
    conn = get_db_connection()
    cursor = conn.cursor()

    if refnum is None:
        refnum = generate_reference_number()

    if donor_id is None:
        donor_id = 0
    
    if donor_name is None or donor_name.strip() == '':
        donor_name = 'Anonymous'

    try:
        donor_payload = {
            'donor_id': int(donor_id) if donor_id is not None else 0,
            'donor_name': donor_name,
            'donor_wallet': donor_wallet,
            'receiver': receiver,
            'paymethod': paymethod,
            'amount': float(amount) / 100,
            'reference': refnum,
            'timestamp': datetime.now().isoformat()
        }
        donor_plain = json.dumps(donor_payload, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
        enc = encrypt_payload(donor_plain)
        payload_hash = sha256_hex(donor_plain)
        don_notes = {'enc': enc, 'plaintext_sha256': payload_hash}
        if payment_intent_id:
            don_notes['payment_intent_id'] = payment_intent_id
        don_notes_json = json.dumps(don_notes)
    except Exception as e:
        print(f"Error encrypting donor payload: {e}")
        don_notes_json = None

    cursor.execute("""
        INSERT INTO donations (
            fund_id, don_donorid, don_donorname, don_receiver, don_paymethod,
            don_amount, don_refnum, don_status, don_date, donor_wallet_address, don_notes
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        fund_id,
        donor_id,
        donor_name,
        receiver,
        paymethod,
        float(amount) / 100,
        refnum,
        "Pending",
        datetime.now(),
        donor_wallet,
        don_notes_json
    ))

    donation_id = cursor.lastrowid
    log_audit_event(
        action='DONATION_CREATED',
        entity_type='donation',
        entity_id=refnum,
        after_data={
            'don_id': donation_id,
            'fund_id': fund_id,
            'don_donorid': donor_id,
            'don_donorname': donor_name,
            'don_paymethod': paymethod,
            'don_amount': float(amount) / 100,
            'don_refnum': refnum,
            'don_status': 'Pending',
            'receiver': receiver
        },
        conn=conn,
        cursor=cursor
    )
    record_donation_fund_status_update(
        cursor=cursor,
        reference_number=refnum,
        donation_id=donation_id,
        new_status='Donation Received',
        previous_status=None,
        updated_by=session.get('user_id') if has_request_context() else None,
        audit_id=None,
        note='Donation created'
    )
    conn.commit()
    cursor.close()
    conn.close()

    return refnum, donation_id

def update_donation_status(refnum, new_status, payment_id=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            SELECT don_id, don_refnum, don_status, don_amount, fund_id, don_donorid, don_paymethod, donor_wallet_address
            FROM donations
            WHERE don_refnum = %s
        """, (refnum,))
        current_donation = cursor.fetchone()

        if (
            current_donation and
            current_donation[6] in ('Cash', 'Cheque', 'In-Kind') and
            not (current_donation[2] == 'Endorsed' and new_status == 'Paid')
        ):
            print(
                "In-person donation status updates are restricted to "
                "Admin endorsement and Treasurer confirmation."
            )
            return False

        cursor.execute("""
            UPDATE donations 
            SET don_status = %s
            WHERE don_refnum = %s
        """, (new_status, refnum))
        
        rows_affected = cursor.rowcount
        if rows_affected > 0:
            log_audit_event(
                action='DONATION_STATUS_UPDATED',
                entity_type='donation',
                entity_id=current_donation[1] if current_donation else refnum,
                before_data={
                    'don_id': current_donation[0] if current_donation else None,
                    'don_refnum': current_donation[1] if current_donation else refnum,
                    'don_status': current_donation[2] if current_donation else None,
                    'don_amount': float(current_donation[3]) if current_donation and current_donation[3] is not None else None,
                    'fund_id': current_donation[4] if current_donation else None,
                    'don_donorid': current_donation[5] if current_donation else None,
                    'don_paymethod': current_donation[6] if current_donation else None
                },
                after_data={
                    'don_refnum': refnum,
                    'don_status': new_status,
                    'payment_id': payment_id,
                    'action_datetime': datetime.now()
                },
                metadata={'source': 'update_donation_status'},
                conn=conn,
                cursor=cursor
            )
            if new_status == 'Paid':
                log_audit_event(
                    action='DONATION_PAYMENT_CONFIRMED',
                    entity_type='donation',
                    entity_id=current_donation[1] if current_donation else refnum,
                    after_data={
                        'don_refnum': refnum,
                        'don_status': new_status,
                        'payment_id': payment_id,
                        'action_datetime': datetime.now()
                    },
                    metadata={'source': 'update_donation_status'},
                    conn=conn,
                    cursor=cursor
                )
                if current_donation:
                    cursor.execute("""
                        SELECT current_status
                        FROM donation_fund_status
                        WHERE reference_number = %s
                        LIMIT 1
                    """, (refnum,))
                    fund_status_row = cursor.fetchone()
                    fund_current_status = fund_status_row[0] if fund_status_row else 'Donation Received'
                    if fund_current_status == 'Donation Received':
                        record_donation_fund_status_update(
                            cursor=cursor,
                            reference_number=refnum,
                            donation_id=current_donation[0],
                            new_status='Payment Confirmed',
                            previous_status='Donation Received',
                            updated_by=session.get('user_id') if has_request_context() else None,
                            audit_id=None,
                            note='Payment confirmed'
                        )
        if rows_affected > 0:
            print(f"✅ Donation {refnum} status updated to {new_status}")
            if payment_id:
                print(f"   Payment ID: {payment_id}")
            
            if new_status == 'Paid':
                blockchain_recorded = record_donation_on_blockchain(
                    refnum,
                    donation_data={
                        'fund_id': current_donation[4] if current_donation else None,
                        'blockchain_fund_id': None,
                        'don_amount': current_donation[3] if current_donation else None,
                        'donor_wallet_address': current_donation[7] if current_donation else None
                    },
                    conn=conn,
                    cursor=cursor
                )
                if not blockchain_recorded:
                    conn.rollback()
                    print(f"Blockchain recording failed for donation {refnum}. Status rollback applied.")
                    return False
            conn.commit()
            if new_status == 'Paid':
                email_sent, email_error = send_fund_creator_donation_email(refnum)
                if not email_sent:
                    print(f"Donation creator email not sent for {refnum}: {email_error}")
                check_and_update_fundraiser_status(refnum)
        else:
            print(f"No donation found with reference {refnum}")
            
        return rows_affected > 0
        
    except Exception as e:
        print(f"❌ Error updating donation status: {e}")
        return False
    finally:
        cursor.close()
        conn.close()

def check_and_update_fundraiser_status(donation_refnum):
    """Check if fundraiser goal is reached and update status to Completed"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT fund_id FROM donations WHERE don_refnum = %s", (donation_refnum,))
        result = cursor.fetchone()
        
        if not result:
            return False
            
        fundraiser_id = result[0]
        
        cursor.execute("SELECT fund_goalamount FROM fundraisers WHERE fund_id = %s", (fundraiser_id,))
        goal_result = cursor.fetchone()
        
        if not goal_result:
            return False
            
        goal_amount = float(goal_result[0])
        
        cursor.execute("""
            SELECT COALESCE(SUM(CASE WHEN don_status = 'Paid' THEN don_amount ELSE 0 END), 0) as total_raised
            FROM donations 
            WHERE fund_id = %s AND don_status = 'Paid'
        """, (fundraiser_id,))
        
        raised_result = cursor.fetchone()
        total_raised = float(raised_result[0]) if raised_result else 0
        
        if total_raised >= goal_amount:
            cursor.execute("""
                UPDATE fundraisers 
                SET fund_status = 'Completed' 
                WHERE fund_id = %s AND fund_status = 'Active'
            """, (fundraiser_id,))

            cursor.execute("""
                INSERT INTO fund_status_workflow (fund_id, current_status, updated_by, created_at, updated_at)
                VALUES (%s, 'Completed', %s, NOW(), NOW())
                ON DUPLICATE KEY UPDATE
                    current_status = 'Completed',
                    updated_by = VALUES(updated_by),
                    updated_at = NOW()
            """, (fundraiser_id, session.get('user_id') if has_request_context() else None))
            
            log_audit_event(
                action='FUNDRAISER_COMPLETED',
                entity_type='fundraiser',
                entity_id=fundraiser_id,
                after_data={
                    'fund_status': 'Completed',
                    'workflow_status': 'Completed',
                    'total_raised': total_raised,
                    'action_datetime': datetime.now()
                },
                metadata={'source': 'check_and_update_fundraiser_status'},
                conn=conn,
                cursor=cursor
            )
            conn.commit()
            print(f"🎉 Fundraiser {fundraiser_id} goal reached! Status updated to Completed.")
            return True
            
        return False
        
    except Exception as e:
        print(f"❌ Error checking fundraiser status: {e}")
        return False
    finally:
        cursor.close()
        conn.close()

def get_donation_by_refnum(refnum):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        cursor.execute("SELECT * FROM donations WHERE don_refnum = %s", (refnum,))
        return cursor.fetchone()
    except Exception as e:
        print(f"❌ Error fetching donation: {e}")
        return None
    finally:
        cursor.close()
        conn.close()


def get_donation_by_id(donation_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute("SELECT * FROM donations WHERE don_id = %s", (donation_id,))
        return cursor.fetchone()
    except Exception as e:
        print(f"Error fetching donation by id: {e}")
        return None
    finally:
        cursor.close()
        conn.close()

def get_paymongo_event_details(payload):
    event_attributes = payload.get('data', {}).get('attributes', {}) if isinstance(payload, dict) else {}
    event_type = event_attributes.get('type')
    event_resource = event_attributes.get('data') or {}
    event_resource_attributes = event_resource.get('attributes', {}) if isinstance(event_resource, dict) else {}
    event_data = event_resource_attributes or event_attributes
    event_resource_id = event_resource.get('id') if isinstance(event_resource, dict) else event_data.get('id')
    return event_type, event_data, event_resource_id

def parse_paymongo_signature_header(signature_header):
    signature_parts = {}
    for part in (signature_header or '').split(','):
        if '=' not in part:
            continue
        key, value = part.split('=', 1)
        signature_parts[key.strip()] = value.strip()
    return signature_parts

def verify_paymongo_webhook_signature(raw_body, signature_header):
    if not PAYMONGO_WEBHOOK_SECRET_KEY:
        return True

    signature_parts = parse_paymongo_signature_header(signature_header)
    timestamp = signature_parts.get('t')

    if not timestamp:
        return False

    signed_payload = f"{timestamp}.{raw_body}".encode('utf-8')
    expected_signature = hmac.new(
        PAYMONGO_WEBHOOK_SECRET_KEY.encode('utf-8'),
        signed_payload,
        hashlib.sha256
    ).hexdigest()

    candidate_signatures = [
        signature_parts.get('li'),
        signature_parts.get('te')
    ]

    return any(
        candidate and hmac.compare_digest(expected_signature, candidate)
        for candidate in candidate_signatures
    )

def extract_paymongo_payment_intent_id(event_type, event_data, event_resource_id):
    if event_type == 'payment_intent.succeeded':
        return event_resource_id or event_data.get('id')

    payment_intent = (
        event_data.get('payment_intent_id') or
        event_data.get('payment_intent') or
        event_data.get('payment_intent_id')
    )

    if isinstance(payment_intent, dict):
        return payment_intent.get('id')

    return payment_intent

def get_donation_ref_by_payment_intent_id(payment_intent_id):
    if not payment_intent_id:
        return None

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT don_refnum
            FROM donations
            WHERE (
                CASE
                    WHEN JSON_VALID(don_notes)
                    THEN JSON_UNQUOTE(JSON_EXTRACT(don_notes, '$.payment_intent_id'))
                    ELSE NULL
                END
            ) = %s
            OR don_notes LIKE %s
            ORDER BY don_date DESC
            LIMIT 1
        """, (payment_intent_id, f'%"{payment_intent_id}"%'))
        row = cursor.fetchone()
        return row[0] if row else None
    except Exception as e:
        print(f"Error finding donation by payment intent {payment_intent_id}: {e}")
        return None
    finally:
        cursor.close()
        conn.close()

def mark_paymongo_payment_paid(payment_intent_id, payment_id=None, metadata=None, amount=None):
    metadata = metadata or {}
    donation_refnum = get_donation_ref_by_payment_intent_id(payment_intent_id)

    if not donation_refnum:
        donation_refnum = metadata.get('reference')

    if not donation_refnum:
        fundraiser_id = metadata.get('fundraiser_id')
        donor_name = metadata.get('donor_name')

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            if fundraiser_id and donor_name:
                cursor.execute("""
                    SELECT don_refnum
                    FROM donations
                    WHERE fund_id = %s AND don_donorname = %s AND don_status = 'Pending'
                    ORDER BY don_date DESC
                    LIMIT 1
                """, (fundraiser_id, donor_name))
            elif amount:
                cursor.execute("""
                    SELECT don_refnum
                    FROM donations
                    WHERE don_amount = %s AND don_status = 'Pending'
                    ORDER BY don_date DESC
                    LIMIT 1
                """, (float(amount) / 100,))
            else:
                return False, None

            row = cursor.fetchone()
            donation_refnum = row[0] if row else None
        finally:
            cursor.close()
            conn.close()

    if not donation_refnum:
        return False, None

    return update_donation_status(donation_refnum, 'Paid', payment_id or payment_intent_id), donation_refnum

@app.route('/webhook/paymongo', methods=['POST'])
@app.route('/webhooks/paymongo.php', methods=['POST'])
def paymongo_webhook():
    try:
        raw_body = request.get_data(as_text=True)

        if not verify_paymongo_webhook_signature(raw_body, request.headers.get('Paymongo-Signature')):
            print("PayMongo webhook rejected due to invalid signature.")
            return jsonify({'error': 'Invalid webhook signature'}), 401

        data = json.loads(raw_body) if raw_body else None

        if not data:
            return jsonify({'error': 'No data received'}), 400

        event_type, event_data, event_resource_id = get_paymongo_event_details(data)

        if event_type not in ('payment.paid', 'payment_intent.succeeded'):
            return jsonify({'status': 'ignored', 'event_type': event_type}), 200

        payment_id = event_resource_id if event_type == 'payment.paid' else None
        amount = event_data.get('amount')
        metadata = event_data.get('metadata', {}) or {}
        payment_intent_id = extract_paymongo_payment_intent_id(event_type, event_data, event_resource_id)

        if not payment_intent_id and not metadata.get('reference'):
            print(f"PayMongo webhook missing payment_intent_id for event {event_type}")
            return jsonify({'error': 'Missing payment_intent_id'}), 400

        updated, donation_refnum = mark_paymongo_payment_paid(
            payment_intent_id=payment_intent_id,
            payment_id=payment_id,
            metadata=metadata,
            amount=amount
        )

        if updated:
            print(f"Donation {donation_refnum} updated to Paid from PayMongo event {event_type}")
            return jsonify({
                'status': 'success',
                'event_type': event_type,
                'payment_intent_id': payment_intent_id,
                'donation_refnum': donation_refnum
            }), 200

        if donation_refnum:
            print(f"Donation {donation_refnum} could not be finalized from PayMongo event {event_type}")
            return jsonify({
                'status': 'blockchain_failed',
                'event_type': event_type,
                'payment_intent_id': payment_intent_id,
                'donation_refnum': donation_refnum
            }), 502

        print(f"No donation found for PayMongo payment intent {payment_intent_id}")
        return jsonify({
            'status': 'no_match',
            'event_type': event_type,
            'payment_intent_id': payment_intent_id
        })
    
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data received'}), 400
        
        print(f"🔔 Webhook received: {data}")
        
        event_attributes = data.get('data', {}).get('attributes', {})
        event_type = event_attributes.get('type')
        event_resource = event_attributes.get('data') or {}
        event_resource_attributes = event_resource.get('attributes', {}) if isinstance(event_resource, dict) else {}
        event_data = event_resource_attributes or event_attributes
        
        if event_type == 'payment.paid':
            payment_id = event_resource.get('id') if isinstance(event_resource, dict) else event_data.get('id')
            amount = event_data.get('amount')
            status = event_data.get('status')
            metadata = event_data.get('metadata', {})
            
            print(f"Payment details - ID: {payment_id}, Amount: {amount}, Status: {status}")
            
            if status == 'paid':
                conn = get_db_connection()
                cursor = conn.cursor()
                
                fundraiser_id = metadata.get('fundraiser_id')
                donor_name = metadata.get('donor_name')
                reference = metadata.get('reference')
                
                if reference:
                    cursor.execute("""
                        SELECT don_refnum
                        FROM donations
                        WHERE don_refnum = %s AND don_status = 'Pending'
                        LIMIT 1
                    """, (reference,))
                elif fundraiser_id and donor_name:
                    cursor.execute("""
                        SELECT don_refnum
                        FROM donations
                        WHERE fund_id = %s AND don_donorname = %s AND don_status = 'Pending'
                        ORDER BY don_date DESC 
                        LIMIT 1
                    """, (fundraiser_id, donor_name))
                else:
                    cursor.execute("""
                        SELECT don_refnum
                        FROM donations
                        WHERE don_amount = %s AND don_status = 'Pending'
                        ORDER BY don_date DESC 
                        LIMIT 1
                    """, (float(amount) / 100,))

                donation_row = cursor.fetchone()
                cursor.close()
                conn.close()
                
                if donation_row and donation_row[0]:
                    donation_refnum = donation_row[0]
                    status_updated = update_donation_status(donation_refnum, 'Paid', payment_id)
                    if status_updated:
                        print(f"Donation updated to Paid status for payment {payment_id}")
                        return jsonify({'status': 'success', 'rows_affected': 1})
                    print(f"Donation {donation_refnum} could not be finalized for payment {payment_id}")
                    return jsonify({'status': 'blockchain_failed', 'refnum': donation_refnum}), 502
                else:
                    print(f"No donation found to update for payment {payment_id}")
                    return jsonify({'status': 'no_match'})
        
        elif event_type == 'payment.failed':
            payment_id = event_resource.get('id') if isinstance(event_resource, dict) else event_data.get('id')
            amount = event_data.get('amount')
            metadata = event_data.get('metadata', {})
            
            print(f"Payment failed - ID: {payment_id}, Amount: {amount}")
            
            conn = get_db_connection()
            cursor = conn.cursor()
            
            fundraiser_id = metadata.get('fundraiser_id')
            donor_name = metadata.get('donor_name')
            reference = metadata.get('reference')
            
            if reference:
                cursor.execute("""
                    UPDATE donations 
                    SET don_status = 'Failed'
                    WHERE don_refnum = %s AND don_status = 'Pending'
                """, (reference,))
            elif fundraiser_id and donor_name:
                cursor.execute("""
                    UPDATE donations 
                    SET don_status = 'Failed'
                    WHERE fund_id = %s AND don_donorname = %s AND don_status = 'Pending'
                    ORDER BY don_date DESC 
                    LIMIT 1
                """, (fundraiser_id, donor_name))
            else:
                cursor.execute("""
                    UPDATE donations 
                    SET don_status = 'Failed'
                    WHERE don_amount = %s AND don_status = 'Pending'
                    ORDER BY don_date DESC 
                    LIMIT 1
                """, (float(amount) / 100,))
            
            rows_affected = cursor.rowcount
            conn.commit()
            cursor.close()
            conn.close()
            
            print(f"Donation marked as Failed for payment {payment_id}")
            return jsonify({'status': 'failed', 'rows_affected': rows_affected})
        
        return jsonify({'status': 'ignored', 'event_type': event_type})
        
    except json.JSONDecodeError:
        return jsonify({'error': 'Invalid JSON payload'}), 400
    except Exception as e:
        print(f"Webhook error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/donation-status/<refnum>', methods=['GET'])
def check_donation_status(refnum):
    try:
        donation = get_donation_by_refnum(refnum)
        
        if not donation:
            return jsonify({'error': 'Donation not found'}), 404
        
        return jsonify({
            'refnum': donation['don_refnum'],
            'status': donation['don_status'],
            'amount': float(donation['don_amount']),
            'date': donation['don_date'].isoformat() if donation['don_date'] else None,
            'fundraiser_id': donation['fund_id'],
            'donor_name': donation['don_donorname'],
            'payment_method': donation['don_paymethod']
        })
        
    except Exception as e:
        print(f"Error checking donation status: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/donation-status/id/<int:donation_id>', methods=['GET'])
def check_donation_status_by_id(donation_id):
    try:
        donation = get_donation_by_id(donation_id)

        if not donation:
            return jsonify({'error': 'Donation not found'}), 404

        return jsonify({
            'donation_id': donation['don_id'],
            'refnum': donation['don_refnum'],
            'status': donation['don_status'],
            'amount': float(donation['don_amount']),
            'date': donation['don_date'].isoformat() if donation['don_date'] else None,
            'fundraiser_id': donation['fund_id'],
            'donor_name': donation['don_donorname'],
            'payment_method': donation['don_paymethod']
        })

    except Exception as e:
        print(f"Error checking donation status by id: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/paymongo/qrph/donation/<int:donation_id>', methods=['GET'])
def qrph_payment_page(donation_id):
    donation = get_donation_by_id(donation_id)

    if not donation:
        return "Donation not found", 404

    qr_data = QRPH_PAYMENT_CODES.get(donation_id)
    created_at = qr_data.get('created_at') if qr_data else None
    is_expired = False

    if created_at and datetime.now() - created_at > timedelta(minutes=30):
        is_expired = True
        QRPH_PAYMENT_CODES.pop(donation_id, None)
        qr_data = None

    return render_template(
        'qrph_payment.html',
        donation=donation,
        qr_data=qr_data,
        is_expired=is_expired,
        status_url=url_for('check_donation_status_by_id', donation_id=donation_id, _external=True),
        verification_url=url_for(
            'donation_verification',
            fundraiser_id=donation['fund_id'],
            donation_id=donation_id,
            _external=True
        ),
        confirmation_url=url_for(
            'donation_confirmation',
            fundraiser_id=donation['fund_id'],
            donation_ref=donation['don_refnum'],
            _external=True
        ),
        donate_url=url_for('donate', fundraiser_id=donation['fund_id'])
    )

@app.route('/api/update-donation-status', methods=['POST'])
def manual_update_donation_status():
    try:
        data = request.get_json()
        refnum = data.get('refnum')
        new_status = data.get('status')
        
        if not refnum or not new_status:
            return jsonify({'error': 'Missing refnum or status'}), 400
        
        valid_statuses = ['Pending', 'Paid', 'Failed', 'Cancelled']
        if new_status not in valid_statuses:
            return jsonify({'error': f'Invalid status. Must be one of: {valid_statuses}'}), 400
        
        success = update_donation_status(refnum, new_status)
        
        if success:
            return jsonify({'message': f'Donation {refnum} status updated to {new_status}'})
        else:
            return jsonify({'error': 'Donation not found or update failed'}), 404
            
    except Exception as e:
        print(f"Error updating donation status: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/fundraiser/<int:fundraiser_id>/donations', methods=['GET'])
def get_fundraiser_donations(fundraiser_id):
    if 'email' not in session or session.get('role') != 'Admin':
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("""
            SELECT d.*, u.name as donor_name, u.email as donor_email
            FROM donations d
            LEFT JOIN users u ON d.don_donorid = u.id
            WHERE d.fund_id = %s
            ORDER BY d.don_date DESC
        """, (fundraiser_id,))
        donations = cursor.fetchall()
        
        cursor.execute("""
            SELECT 
                COUNT(*) as total_donations,
                COUNT(CASE WHEN don_status = 'Paid' THEN 1 END) as paid_donations,
                COUNT(CASE WHEN don_status = 'Pending' THEN 1 END) as pending_donations,
                COUNT(CASE WHEN don_status = 'Failed' THEN 1 END) as failed_donations,
                COALESCE(SUM(CASE WHEN don_status = 'Paid' THEN don_amount ELSE 0 END), 0) as total_raised,
                COALESCE(AVG(CASE WHEN don_status = 'Paid' THEN don_amount END), 0) as avg_donation,
                COALESCE(MAX(CASE WHEN don_status = 'Paid' THEN don_amount END), 0) as max_donation,
                COALESCE(MIN(CASE WHEN don_status = 'Paid' THEN don_amount END), 0) as min_donation
            FROM donations 
            WHERE fund_id = %s
        """, (fundraiser_id,))
        stats = cursor.fetchone()
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'donations': donations,
            'stats': stats
        })
        
    except Exception as e:
        print(f"Error fetching fundraiser donations: {e}")
        return jsonify({'error': str(e)}), 500


# -----------------------------------------------------------------------
# ------------------------------- ACCOUNT -------------------------------
# -----------------------------------------------------------------------

@app.route('/create-account')
def create_account():
    return render_template('signup.html')

@app.route('/signin')
def goto_signin():
    return render_template('signin.html')

def verify_sha256(stored_hash, plain_password):
    if not stored_hash:
        return False
    if stored_hash.startswith('pbkdf2:') or stored_hash.startswith('scrypt:'):
        return check_password_hash(stored_hash, plain_password)
    return stored_hash == hashlib.sha256(plain_password.encode()).hexdigest()

@app.route('/signin', methods=['POST', 'GET'])
def signin():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        try:
            conn = get_db_connection()
            cursor = conn.cursor(buffered=True)
        except mysql.connector.Error as err:
            print("Error connecting to database:", err)
            return render_template('signin.html', error="Database connection error.")

        try:
            sql = """
                SELECT id, name, role, password, id_verification_status
                FROM users
                WHERE email = %s
            """
            cursor.execute(sql, (email,))
            account = cursor.fetchone()

            if account:
                stored_hash = account[3]

                if stored_hash and verify_sha256(stored_hash, password):
                    user_id = account[0]
                    username = account[1]
                    role = account[2]
                    verification_status = (account[4] or 'not_verified').strip().lower()

                    if role not in ['Admin', 'Treasurer'] and verification_status != 'verified':
                        failure_reason = f"ID verification status is {verification_status}"
                        log_audit_event(
                            action='AUTH_SIGNIN',
                            entity_type='user',
                            entity_id=user_id,
                            status='FAILED',
                            reason=failure_reason,
                            after_data={'email': email, 'role': role, 'id_verification_status': verification_status}
                        )
                        if verification_status == 'pending':
                            return render_template('signin.html', error="Your account is still pending ID verification.")
                        if verification_status == 'rejected':
                            return render_template('signin.html', error="Your ID verification was rejected. Please contact an administrator.")
                        return render_template('signin.html', error="Your account is not yet verified.")

                    session['email'] = email
                    session['role'] = role
                    session['user_id'] = user_id
                    session['username'] = username
                    session['id_verification_status'] = verification_status
                    log_audit_event(
                        action='AUTH_SIGNIN',
                        entity_type='user',
                        entity_id=user_id,
                        status='SUCCESS',
                        after_data={'email': email, 'role': role, 'id_verification_status': verification_status}
                    )

                    if role == 'User':
                        return redirect(url_for('home'))
                    elif role == 'Admin':
                        return redirect(url_for('admin'))
                    elif role == 'Treasurer':
                        return redirect(url_for('treasurer'))
                    elif role == 'MSWDO':
                        return render_template('signin.html', error="MSWDO is no longer available.")
                    else:
                        log_audit_event(
                            action='AUTH_SIGNIN',
                            entity_type='user',
                            entity_id=user_id,
                            status='FAILED',
                            reason='Undefined role',
                            after_data={'email': email, 'role': role}
                        )
                        return render_template('signin.html', error="User role is undefined.")
                else:
                    log_audit_event(
                        action='AUTH_SIGNIN',
                        entity_type='user',
                        status='FAILED',
                        reason='Invalid password',
                        after_data={'email': email}
                    )
                    return render_template('signin.html', error="Invalid email or password.")
            else:
                log_audit_event(
                    action='AUTH_SIGNIN',
                    entity_type='user',
                    status='FAILED',
                    reason='Account not found',
                    after_data={'email': email}
                )
                return render_template('signup.html', email_prefill=email)

        except mysql.connector.Error as err:
            print("Error during login query:", err)
            log_audit_event(
                action='AUTH_SIGNIN',
                entity_type='user',
                status='FAILED',
                reason=f"Database error: {str(err)[:200]}",
                after_data={'email': email}
            )
            return render_template('signin.html', error="An error occurred while logging in.")

        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    return render_template('signin.html')


def validate_password(password):
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"
    
    if not any(c.isupper() for c in password):
        return False, "Password must contain at least 1 uppercase letter"
    
    if not any(c.isdigit() for c in password):
        return False, "Password must contain at least 1 number"
    
    if not any(c in "!@#$%^&*()_+=-" for c in password):
        return False, "Password must contain at least 1 symbol (!@#$%^&*()_+=-)"
    
    return True, "Password is valid"

@app.route('/signup', methods=['POST'])
def signup():
    fname = request.form['fname']
    lname = request.form['lname']
    email = request.form['email']
    phone = request.form['phone']
    password = request.form['password']
    confirm_password = request.form['confirm_password']
    
    id_document_type = request.form['id_document_type']
    id_document_image = request.files['id_document_image']

    if password != confirm_password:
        return render_template('signup.html', error="Passwords do not match. Please check your password confirmation.", email_prefill=email)

    is_valid, error_message = validate_password(password)
    if not is_valid:
        return render_template('signup.html', error=error_message, email_prefill=email)

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT email FROM users WHERE email = %s", (email,))
        if cursor.fetchone():
            return render_template('signup.html', error="Email already exists. Please use a different email.", email_prefill=email)
        
        if not id_document_image or not id_document_image.filename:
            return render_template('signup.html', error="Please upload a photo of your ID document.", email_prefill=email)

        if not allowed_file(id_document_image.filename):
            return render_template('signup.html', error="Invalid file format. Please upload a JPG or PNG image.", email_prefill=email)
        
        id_document_data = id_document_image.read()
        id_document_filename = secure_filename(id_document_image.filename)
        
        verification_status = 'pending'
        
        # Hash the password before storing
        password_hash = generate_password_hash(password)
        
        full_name = f"{fname} {lname}"
        cursor.execute("""
            INSERT INTO users (name, email, number, password, role, date_created, 
                                id_verification_status, id_document_type,
                                id_document_image, id_document_filename) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (full_name, email, phone, password_hash, 'User', datetime.now().date(),
            verification_status, id_document_type, id_document_data, id_document_filename))
        new_user_id = cursor.lastrowid
        log_audit_event(
            action='USER_CREATED',
            entity_type='user',
            entity_id=new_user_id,
            after_data={
                'id': new_user_id,
                'name': full_name,
                'email': email,
                'number': phone,
                'role': 'User',
                'id_verification_status': verification_status
            },
            conn=conn,
            cursor=cursor,
            actor_user_id=new_user_id,
            actor_email=email,
            actor_role='User'
        )
        conn.commit()
        cursor.close()
        conn.close()
        
        return render_template('signin.html', success="Account created successfully! Please sign in.")
        
    except mysql.connector.Error as err:
        print(f"Error during signup: {err}")
        return render_template('signup.html', error="An error occurred while creating your account. Please try again.", email_prefill=email)

@app.route('/forgot-password')
def forgot():
    return render_template('forgot.html')

otp_store = {}

@app.route('/forgot-password/send-otp', methods=['POST'])
def forgot_otp():
    email = request.json.get('email')

    if not email:
        return jsonify({'error': 'Email is required.'}), 400

    try:
        conn = get_db_connection()
        cursor = conn.cursor(buffered=True)
        cursor.execute('SELECT id FROM users WHERE email = %s', (email,))
        account = cursor.fetchone()
        cursor.close()
        conn.close()
    except Exception:
        return jsonify({'error': 'Database error. Please try again.'}), 500

    if not account:
        return jsonify({'error': 'No account found with that email address.'}), 404

    otp = str(random.randint(100000, 999999))
    expiry = datetime.now() + timedelta(minutes=3)
    otp_store[email] = (otp, expiry)

    msg = Message('Password Reset OTP', sender=app.config['MAIL_USERNAME'], recipients=[email])
    msg.body = f"Your OTP code for password reset is {otp}.\nUse this code to reset your password. This OTP will expire in 3 minutes."

    try:
        mail.send(msg)
        return jsonify({'message': 'OTP sent successfully! Check your email.'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/forgot-password/verify-otp', methods=['POST'])
def verify_otp():
    email = request.form.get('email')
    otp_input = request.form.get('otp')

    otp_data = otp_store.get(email)
    if not otp_data:
        return jsonify({'error': 'No OTP found. Please request a new one.'}), 400

    otp, expiry = otp_data
    if datetime.now() > expiry:
        otp_store.pop(email, None)
        return jsonify({'error': 'OTP expired. Please request a new one.'}), 400

    if otp_input != otp:
        return jsonify({'error': 'Invalid OTP. Please try again.'}), 400

    otp_store.pop(email, None)
    return redirect(url_for('reset_pass', email=email))

@app.route('/reset-pass')
def reset_pass():
    email = request.args.get('email')
    return render_template('reset.html', email=email)

@app.route('/reset_password', methods=['POST'])
def reset_password():
    email = request.form['email']
    new_password = request.form['password']
    confirm_password = request.form['conf_pass']

    if new_password != confirm_password:
        return render_template('reset.html', email=email, error="Passwords do not match.")

    is_valid, error_message = validate_password(new_password)
    if not is_valid:
        return render_template('reset.html', email=email, error=error_message)

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        # Hash the password before storing
        password_hash = generate_password_hash(new_password)
        cursor.execute("UPDATE users SET password = %s WHERE email = %s", (password_hash, email))
        conn.commit()
        return redirect(url_for('signin', reset_success=1))
    except mysql.connector.Error as err:
        print(f"Error updating password: {err}")
        return render_template('reset.html', email=email, error="An error occurred while resetting your password.")
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


# -----------------------------------------------------------------------
# ----------------------------- USER PROFILE ----------------------------
# -----------------------------------------------------------------------

@app.route('/profile/my-fundraisers')
def profile_funds():
    if 'email' not in session:
        return redirect(url_for('goto_signin'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True, buffered=True)
    
    try:
        cursor.execute("SELECT id, name FROM users WHERE email = %s", (session['email'],))
        user = cursor.fetchone()
        
        cursor.execute("SELECT * FROM fundraisers WHERE fund_creatorid = %s", (user['id'],))
        fund = cursor.fetchall()
        
        return render_template('profile_funds.html', user=user, fund=fund)
    finally:
        cursor.close()
        conn.close()


@app.route('/manage-fundraiser/<int:fundraiser_id>')
def manage_fundraiser(fundraiser_id):
    if 'email' not in session:
        return redirect(url_for('goto_signin'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True, buffered=True)
    
    try:
        cursor.execute("SELECT * FROM fundraisers WHERE fund_id = %s", (fundraiser_id,))
        fundraiser = cursor.fetchone()
        
        if not fundraiser:
            return "Fundraiser not found", 404
        
        cursor.execute("SELECT id FROM users WHERE email = %s", (session['email'],))
        user = cursor.fetchone()
        
        if fundraiser['fund_creatorid'] != user['id']:
            return "Unauthorized", 403
        
        cursor.execute("""
            SELECT don_donorname, don_amount, don_date, don_status
            FROM donations 
            WHERE fund_id = %s AND don_status = 'Paid'
            ORDER BY don_date DESC
        """, (fundraiser_id,))
        donations = cursor.fetchall()
        
        cursor.execute("""
            SELECT image_id, image_filename, image_order, is_primary, uploaded_date
            FROM fundraiser_images 
            WHERE fund_id = %s 
            ORDER BY is_primary DESC, image_order ASC, uploaded_date ASC
        """, (fundraiser_id,))
        additional_images = cursor.fetchall()
        
        cursor.execute("""
            SELECT * FROM beneficiaries 
            WHERE fund_id = %s 
            ORDER BY date_added ASC
        """, (fundraiser_id,))
        beneficiaries = cursor.fetchall()
        
        total_raised = sum(d['don_amount'] for d in donations if d['don_status'] == 'Paid') if donations else 0
        
        return render_template('manage_fundraiser.html', 
            fundraiser=fundraiser, 
            donations=donations, 
            total_raised=total_raised,
            beneficiaries=beneficiaries,
            additional_images=additional_images)
    finally:
        cursor.close()
        conn.close()

@app.route('/update-fundraiser', methods=['POST'])
def update_fundraiser():
    if 'email' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        fund_id = request.form.get('fund_id')
        if not fund_id:
            return jsonify({'error': 'Fundraiser ID required'}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT
                f.fund_creatorid, u.id, f.fund_title, f.fund_beneficiary,
                f.fund_goalamount, f.fund_desc, f.fund_status
            FROM fundraisers f
            JOIN users u ON u.email = %s
            WHERE f.fund_id = %s
        """, (session['email'], fund_id))
        result = cursor.fetchone()
        
        if not result or result[0] != result[1]:
            cursor.close()
            conn.close()
            return jsonify({'error': 'Unauthorized'}), 403

        before_snapshot = {
            'fund_title': result[2],
            'fund_beneficiary': result[3],
            'fund_goalamount': float(result[4]) if result[4] is not None else None,
            'fund_desc': result[5],
            'fund_status': result[6]
        }
        
        update_fields = []
        values = []
        
        fields_to_update = [
            'fund_title', 'fund_beneficiary', 
            'fund_goalamount', 'fund_desc', 'fund_status'
        ]
        
        for field in fields_to_update:
            value = request.form.get(field)
            if value is not None:
                update_fields.append(f"{field} = %s")
                values.append(value)
        
        if 'fund_img' in request.files:
            file = request.files['fund_img']
            if file and file.filename:
                update_fields.append("fund_img = %s")
                values.append(file.read())
        
        if update_fields:
            values.append(fund_id)
            sql = f"UPDATE fundraisers SET {', '.join(update_fields)} WHERE fund_id = %s"
            cursor.execute(sql, values)
            requested_updates = {field: request.form.get(field) for field in fields_to_update if request.form.get(field) is not None}
            if 'fund_img' in request.files and request.files['fund_img'] and request.files['fund_img'].filename:
                requested_updates['fund_img_updated'] = True
            after_snapshot = dict(before_snapshot)
            after_snapshot.update(requested_updates)
            log_audit_event(
                action='FUNDRAISER_UPDATED',
                entity_type='fundraiser',
                entity_id=fund_id,
                before_data=before_snapshot,
                after_data=after_snapshot,
                conn=conn,
                cursor=cursor
            )
            conn.commit()
        
        cursor.close()
        conn.close()
        
        return jsonify({'success': True})
        
    except Exception as e:
        print(f"Error updating fundraiser: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/fundraiser/<int:fundraiser_id>/images', methods=['GET'])
def get_fundraiser_images(fundraiser_id):
    """Get all images for a specific fundraiser"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("""
            SELECT image_id, image_filename, image_order, is_primary, uploaded_date
            FROM fundraiser_images 
            WHERE fund_id = %s 
            ORDER BY is_primary DESC, image_order ASC, uploaded_date ASC
        """, (fundraiser_id,))
        
        images = cursor.fetchall()
        cursor.close()
        conn.close()
        
        return jsonify({'images': images})
        
    except Exception as e:
        print(f"Error fetching fundraiser images: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/fundraiser/<int:fundraiser_id>/images', methods=['POST'])
def upload_fundraiser_images(fundraiser_id):
    if 'email' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT f.fund_creatorid, u.id 
            FROM fundraisers f
            JOIN users u ON u.email = %s
            WHERE f.fund_id = %s
        """, (session['email'], fundraiser_id))
        result = cursor.fetchone()
        
        if not result or result[0] != result[1]:
            cursor.close()
            conn.close()
            return jsonify({'error': 'Unauthorized'}), 403
        
        files = request.files.getlist('images')
        if not files or all(not file.filename for file in files):
            return jsonify({'error': 'No images provided'}), 400
        
        cursor.execute("""
            SELECT COALESCE(MAX(image_order), 0) as max_order 
            FROM fundraiser_images 
            WHERE fund_id = %s
        """, (fundraiser_id,))
        max_order = cursor.fetchone()[0]
        
        uploaded_images = []
        for i, file in enumerate(files):
            if file and file.filename and allowed_file(file.filename):
                image_data = file.read()
                filename = secure_filename(file.filename)
                image_order = max_order + i + 1
                
                is_primary = 1 if i == 0 else 0
                
                cursor.execute("""
                    INSERT INTO fundraiser_images 
                    (fund_id, image_data, image_filename, image_order, is_primary)
                    VALUES (%s, %s, %s, %s, %s)
                """, (fundraiser_id, image_data, filename, image_order, is_primary))
                
                uploaded_images.append({
                    'filename': filename,
                    'order': image_order,
                    'is_primary': bool(is_primary)
                })
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({
            'success': True, 
            'uploaded_count': len(uploaded_images),
            'images': uploaded_images
        })
        
    except Exception as e:
        print(f"Error uploading images: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/fundraiser/<int:fundraiser_id>/images/<int:image_id>', methods=['DELETE'])
def delete_fundraiser_image(fundraiser_id, image_id):
    if 'email' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT f.fund_creatorid, u.id 
            FROM fundraisers f
            JOIN users u ON u.email = %s
            WHERE f.fund_id = %s
        """, (session['email'], fundraiser_id))
        result = cursor.fetchone()
        
        if not result or result[0] != result[1]:
            cursor.close()
            conn.close()
            return jsonify({'error': 'Unauthorized'}), 403
        
        cursor.execute("""
            DELETE FROM fundraiser_images 
            WHERE image_id = %s AND fund_id = %s
        """, (image_id, fundraiser_id))
        
        if cursor.rowcount == 0:
            cursor.close()
            conn.close()
            return jsonify({'error': 'Image not found'}), 404
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({'success': True})
        
    except Exception as e:
        print(f"Error deleting image: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/fundraiser/<int:fundraiser_id>/images/<int:image_id>/set-primary', methods=['POST'])
def set_primary_image(fundraiser_id, image_id):
    """Set an image as the primary image for a fundraiser"""
    if 'email' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT f.fund_creatorid, u.id 
            FROM fundraisers f
            JOIN users u ON u.email = %s
            WHERE f.fund_id = %s
        """, (session['email'], fundraiser_id))
        result = cursor.fetchone()
        
        if not result or result[0] != result[1]:
            cursor.close()
            conn.close()
            return jsonify({'error': 'Unauthorized'}), 403
        
        cursor.execute("""
            UPDATE fundraiser_images 
            SET is_primary = 0 
            WHERE fund_id = %s
        """, (fundraiser_id,))
        
        cursor.execute("""
            UPDATE fundraiser_images 
            SET is_primary = 1 
            WHERE image_id = %s AND fund_id = %s
        """, (image_id, fundraiser_id))
        
        if cursor.rowcount == 0:
            cursor.close()
            conn.close()
            return jsonify({'error': 'Image not found'}), 404
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({'success': True})
        
    except Exception as e:
        print(f"Error setting primary image: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/fundraiser/<int:fundraiser_id>/images/<int:image_id>', methods=['GET'])
def get_fundraiser_image(fundraiser_id, image_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT image_data, image_filename 
            FROM fundraiser_images 
            WHERE image_id = %s AND fund_id = %s
        """, (image_id, fundraiser_id))
        
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if not result:
            return "Image not found", 404
        
        image_data, filename = result
        
        content_type = 'image/jpeg'
        if filename:
            ext = filename.lower().split('.')[-1]
            if ext in ['png']:
                content_type = 'image/png'
            elif ext in ['gif']:
                content_type = 'image/gif'
            elif ext in ['webp']:
                content_type = 'image/webp'
        
        return Response(image_data, mimetype=content_type)
        
    except Exception as e:
        print(f"Error fetching image: {e}")
        return "Error fetching image", 500

@app.route('/profile/my-donations')
def profile_dons():
    if 'email' not in session:
        return redirect(url_for('goto_signin'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, name FROM users WHERE email = %s", (session['email'],))
    user = cursor.fetchone()
    cursor.execute("""
        SELECT d.*, f.fund_title
        FROM donations d
        JOIN fundraisers f ON d.fund_id = f.fund_id
        WHERE d.don_donorid = %s
        ORDER BY d.don_date DESC
    """, (user['id'],))
    dons = cursor.fetchall()
    cursor.close()
    conn.close()

    return render_template('profile_dons.html', user=user, dons=dons)

@app.route('/profile/billing')
def profile_bill():
    if 'email' not in session:
        return redirect(url_for('goto_signin'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, name FROM users WHERE email = %s", (session['email'],))
    user = cursor.fetchone()

    cursor.execute(
        """
        SELECT don_refnum, don_status, don_amount, don_date
        FROM donations
        WHERE don_donorid = %s
        ORDER BY don_date DESC
        """,
        (user['id'],)
    )
    payments = cursor.fetchall()

    cursor.execute(
        """
        SELECT id, method_type, account_name, account_number, is_default, date_added
        FROM payment_methods
        WHERE user_id = %s
        ORDER BY is_default DESC, date_added DESC
        """,
        (user['id'],)
    )
    methods = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('profile_bill.html', user=user, payments=payments, methods=methods)

@app.route('/payment-methods/<int:method_id>/set-default', methods=['POST'])
def set_default_payment_method(method_id: int):
    if 'email' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT id FROM users WHERE email = %s", (session['email'],))
        user_row = cursor.fetchone()
        if not user_row:
            cursor.close()
            conn.close()
            return jsonify({'error': 'User not found'}), 404
        user_id = user_row[0]

        cursor.execute("SELECT id FROM payment_methods WHERE id = %s AND user_id = %s", (method_id, user_id))
        row = cursor.fetchone()
        if not row:
            cursor.close()
            conn.close()
            return jsonify({'error': 'Not found'}), 404

        cursor.execute("UPDATE payment_methods SET is_default = 0 WHERE user_id = %s", (user_id,))
        cursor.execute("UPDATE payment_methods SET is_default = 1 WHERE id = %s", (method_id,))
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/payment-methods', methods=['POST'])
def add_payment_method():
    if 'email' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    try:
        payload = request.get_json() or {}
        method_type = payload.get('method_type')
        account_name = payload.get('account_name')
        account_number = payload.get('account_number')
        make_default = bool(payload.get('is_default', False))

        if not method_type or not account_name or not account_number:
            return jsonify({'error': 'Missing required fields'}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT id FROM users WHERE email = %s", (session['email'],))
        user_row = cursor.fetchone()
        if not user_row:
            cursor.close()
            conn.close()
            return jsonify({'error': 'User not found'}), 404
        user_id = user_row[0]

        if make_default:
            cursor.execute("UPDATE payment_methods SET is_default = 0 WHERE user_id = %s", (user_id,))

        cursor.execute(
            """
            INSERT INTO payment_methods (user_id, method_type, account_name, account_number, is_default, date_added)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (user_id, method_type, account_name, account_number, 1 if make_default else 0, datetime.now())
        )
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/payment-methods/<int:method_id>/delete', methods=['POST'])
def delete_payment_method(method_id: int):
    if 'email' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT pm.user_id FROM payment_methods pm
            JOIN users u ON u.id = pm.user_id
            WHERE pm.id = %s AND u.email = %s
        """, (method_id, session['email']))
        row = cursor.fetchone()
        if not row:
            cursor.close()
            conn.close()
            return jsonify({'error': 'Not found'}), 404

        cursor.execute("DELETE FROM payment_methods WHERE id = %s", (method_id,))
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
@app.route('/profile/account-settings')
def profile_acc():
    if 'email' not in session:
        return redirect(url_for('goto_signin'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, name, email, number FROM users WHERE email = %s", (session['email'],))
    user = cursor.fetchone()
    cursor.close()
    conn.close()

    return render_template('profile_acc.html', user=user)

@app.route('/signout')
def signout():
    print(f"User {session.get('user_id')} has signed out.")
    session.clear()
    return redirect(url_for('index'))


# -----------------------------------------------------------------------
# -------------------------- START A FUNDRAISER -------------------------
# -----------------------------------------------------------------------

@app.route('/start_fundraiser', methods=['GET', 'POST'])
def start_fundraiser():
    if 'email' not in session:
        return redirect(url_for('goto_signin'))
    
    if request.method == 'POST':
        fundraiser_type = request.form.get('fundraiser_type')
        session['fundraiser'] = {
            'fund_type': fundraiser_type
        }
        return redirect(url_for('start_fundraiser_3'))
    
    return render_template('start_fundraiser.html')

@app.route('/start_fundraiser-2', methods=['GET', 'POST'])
def start_fundraiser_2():
    if 'email' not in session:
        return redirect(url_for('goto_signin'))

    if request.method == 'POST':
        fundraiser = session.get('fundraiser', {})
        fundraiser['fundraiser_for'] = request.form.get('fundraiser_for')
        session['fundraiser'] = fundraiser
        return redirect(url_for('start_fundraiser_3'))

    return render_template('start_fundraiser2.html')

@app.route('/start_fundraiser-2.1', methods=['GET', 'POST'])
def start_fundraiser_21():
    if 'email' not in session:
        return redirect(url_for('goto_signin'))

    if request.method == 'POST':
        fundraiser = session.get('fundraiser', {})
        fundraiser['fundraiser_for'] = request.form.get('fundraiser_for')
        session['fundraiser'] = fundraiser
        return redirect(url_for('start_fundraiser_3'))

    return render_template('start_fundraiser21.html')

@app.route('/start_fundraiser-3', methods=['GET', 'POST'])
def start_fundraiser_3():
    if 'email' not in session:
        return redirect(url_for('goto_signin'))

    if request.method == 'POST':
        fundraiser = session.get('fundraiser', {})
        amount = request.form.get('amount')
        
        try:
            amount_value = int(amount.replace(',', '')) if amount else 0
            min_amount = get_setting('min_goal_amount', 5000)
            max_amount = get_setting('max_goal_amount', 10000000)
            
            if amount_value < min_amount:
                settings = get_all_settings()
                return render_template('start_fundraiser3.html', 
                    settings=settings, 
                    error=f"Minimum amount is ₱{min_amount:,}.00")
            
            if amount_value > max_amount:
                settings = get_all_settings()
                return render_template('start_fundraiser3.html', 
                    settings=settings, 
                    error=f"Maximum amount is ₱{max_amount:,}.00")
            
            fundraiser['goal_amount'] = amount
            session['fundraiser'] = fundraiser
            return redirect(url_for('start_fundraiser_4'))
            
        except ValueError:
            settings = get_all_settings()
            return render_template('start_fundraiser3.html', 
                settings=settings, 
                error="Please enter a valid amount")

    settings = get_all_settings()
    return render_template('start_fundraiser3.html', settings=settings)

@app.route('/start_fundraiser-4', methods=['GET', 'POST'])
def start_fundraiser_4():
    if 'email' not in session:
        return redirect(url_for('goto_signin'))

    if request.method == 'POST':
        fundraiser = session.get('fundraiser', {})
        
        file = request.files.get('fund_img')
        if file and file.filename and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            unique_filename = f"{uuid.uuid4()}_{filename}"
            temp_path = os.path.join(UPLOAD_FOLDER, unique_filename)
            
            file.save(temp_path)
            fundraiser['image_path'] = temp_path
        
        additional_files = request.files.getlist('additional_images')
        additional_image_paths = []
        
        for file in additional_files:
            if file and file.filename and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                unique_filename = f"{uuid.uuid4()}_{filename}"
                temp_path = os.path.join(UPLOAD_FOLDER, unique_filename)
                
                file.save(temp_path)
                additional_image_paths.append(temp_path)
        
        if additional_image_paths:
            fundraiser['additional_image_paths'] = additional_image_paths
            
        session['fundraiser'] = fundraiser
        return redirect(url_for('start_fundraiser_5'))

    return render_template('start_fundraiser4.html')

@app.route('/start_fundraiser-5', methods=['GET', 'POST'])
def start_fundraiser_5():
    if 'email' not in session:
        return redirect(url_for('goto_signin'))

    if request.method == 'POST':
        fundraiser = session.get('fundraiser', {})
        fundraiser['title'] = request.form.get('fund_title')
        fundraiser['story'] = request.form.get('fund_story')
        session['fundraiser'] = fundraiser
        return redirect(url_for('save_fundraiser'))

    return render_template('start_fundraiser5.html')

@app.route('/gen_story', methods=['POST'])
def gen_story():
    if 'email' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    data = request.get_json()
    fund_title = data.get('fund_title', '').strip()
    if not fund_title:
        return jsonify({'error': 'Fundraiser title is required.'}), 400

    username = session.get('name', 'Anonymous Donor')
    fundraiser_for = session.get('fundraiser', {}).get('fundraiser_for', 'Someone In Need')
    goal_amount = session.get('fundraiser', {}).get('goal_amount', None)
    fund_type = session.get('fundraiser', {}).get('fund_type', 'other')

    prompt = f"""
    Write a clear, factual, and descriptive fundraiser description for the following:
    Title: {fund_title}
    Beneficiary: {fundraiser_for}
    Created by: {username}
    Disaster Type: {fund_type}
    """
    if goal_amount:
        prompt += f"\nGoal Amount: ₱{goal_amount}"
    prompt += (
        "\nDo NOT repeat or list the title, creator, or beneficiary in the description. "
        "Do not predict or assume the age of the user or beneficiary. "
        "Do not start the description with a heading or summary of these fields. "
        "The description should not be a letter or addressed to anyone. "
        "It should be written in the third person, focusing on the facts, background, and needs of the fundraiser. "
        f"Focus on the {fund_type} context and explain who the fundraiser is for, what happened, why help is needed, and any relevant details. "
        "Keep it easy to understand and emotionally engaging, but do not use a letter or direct address format."
    )

    try:
        load_dotenv()
        api_key = os.getenv("OPENAI_KEY")
        if api_key:
            client = OpenAI(api_key=api_key)
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7
            )
            story = response.choices[0].message.content.strip()
        else:
            pass
    except Exception as e:
        return jsonify({'error': f'Failed to generate story: {str(e)}'}), 500

    return jsonify({'story': story})

@app.route('/gen_title', methods=['POST'])
def gen_title():
    if 'email' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    data = request.get_json()
    raw_title = data.get('title', '').strip()
    if not raw_title:
        return jsonify({'error': 'Title is required.'}), 400

    fund_type = session.get('fundraiser', {}).get('fund_type', 'other')

    prompt = (
        f"Generate exactly 3 improved fundraiser title suggestions for a {fund_type} disaster relief campaign. "
        "Keep each title under 80 characters, concise, descriptive, and in title case. "
        "Make them relevant to the disaster type and emotionally compelling. "
        "Avoid emojis, quotes, hashtags, numbering, bullets, and unnecessary punctuation. "
        "Return only the 3 title suggestions, one per line, with no extra text.\n"
        f"Original Title: {raw_title}"
    )

    try:
        load_dotenv()
        api_key = os.getenv("OPENAI_KEY")
        if api_key:
            client = OpenAI(api_key=api_key)
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.5
            )
            polished = response.choices[0].message.content.strip()
        else:
            pass
    except Exception as e:
        return jsonify({'error': f'Failed to generate title: {str(e)}'}), 500

    suggestions = []
    for line in polished.splitlines():
        cleaned = line.strip().lstrip("-*0123456789. )(").strip()
        if cleaned and cleaned not in suggestions:
            suggestions.append(cleaned[:80])
        if len(suggestions) == 3:
            break

    if not suggestions:
        fallback = ' '.join(polished.splitlines()).strip()
        if fallback:
            suggestions.append(fallback[:80])

    return jsonify({
        'title': suggestions[0] if suggestions else '',
        'suggestions': suggestions[:3]
    })

def compress_image(image_path, max_size_mb=1, max_dimensions=(1920, 1080), quality=85):
    """
    Compress and resize an image to reduce file size.
    
    Args:
        image_path: Path to the image file
        max_size_mb: Maximum file size in MB (default: 1MB)
        max_dimensions: Maximum width and height (default: 1920x1080)
        quality: JPEG quality (1-100, default: 85)
    
    Returns:
        Compressed image data as bytes, or None if compression fails
    """
    if not PIL_AVAILABLE:
        try:
            with open(image_path, 'rb') as f:
                data = f.read()
            if len(data) > 5 * 1024 * 1024:
                print(f"Warning: Image file is too large ({len(data) / 1024 / 1024:.2f}MB) and PIL is not available for compression.")
                return None
            return data
        except Exception as e:
            print(f"Error reading image without compression: {e}")
            return None
    
    try:
        max_size_bytes = max_size_mb * 1024 * 1024
        
        with Image.open(image_path) as img:
            if img.mode in ('RGBA', 'LA', 'P'):
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                img = background
            elif img.mode != 'RGB':
                img = img.convert('RGB')
            
            if img.size[0] > max_dimensions[0] or img.size[1] > max_dimensions[1]:
                img.thumbnail(max_dimensions, Image.Resampling.LANCZOS)
                print(f"Image resized to {img.size}")
            
            output = io.BytesIO()
            current_quality = quality
            
            for attempt in range(5):
                output.seek(0)
                output.truncate(0)
                img.save(output, format='JPEG', quality=current_quality, optimize=True)
                
                if output.tell() <= max_size_bytes:
                    break
                
                current_quality = max(50, current_quality - 10)
            
            compressed_data = output.getvalue()
            original_size = os.path.getsize(image_path)
            print(f"Image compressed: {original_size / 1024 / 1024:.2f}MB -> {len(compressed_data) / 1024 / 1024:.2f}MB")
            
            if len(compressed_data) > max_size_bytes * 1.5:
                print(f"Warning: Compressed image is still large ({len(compressed_data) / 1024 / 1024:.2f}MB)")
            
            return compressed_data
            
    except Exception as e:
        print(f"Error compressing image: {e}")
        traceback.print_exc()
        try:
            with open(image_path, 'rb') as f:
                return f.read()
        except:
            return None

@app.route('/save_fundraiser')
def save_fundraiser():
    if 'email' not in session or 'fundraiser' not in session:
        return redirect(url_for('goto_signin'))

    fundraiser = session['fundraiser']
    print("Session fundraiser data:", fundraiser)

    connection = get_db_connection()
    cursor = connection.cursor()

    image_data = None
    if 'image_path' in fundraiser and os.path.exists(fundraiser['image_path']):
        try:
            file_size = os.path.getsize(fundraiser['image_path'])
            if file_size > 10 * 1024 * 1024:
                print(f"Error: Image file is too large ({file_size / 1024 / 1024:.2f}MB)")
                cursor.close()
                connection.close()
                error_msg = f"Image file is too large ({file_size / 1024 / 1024:.1f}MB). Please use an image smaller than 10MB."
                if not PIL_AVAILABLE:
                    error_msg += " For automatic compression, please install Pillow: pip install Pillow"
                return render_template('start_fundraiser4.html', error=error_msg)
            
            image_data = compress_image(fundraiser['image_path'], max_size_mb=1)
            if image_data is None:
                with open(fundraiser['image_path'], 'rb') as f:
                    image_data = f.read()
            
            if image_data and len(image_data) > 2 * 1024 * 1024:
                print(f"Warning: Image is still large ({len(image_data) / 1024 / 1024:.2f}MB) after compression.")
                if PIL_AVAILABLE and os.path.exists(fundraiser['image_path']):
                    image_data = compress_image(fundraiser['image_path'], max_size_mb=0.8, quality=70)
                    if image_data and len(image_data) > 2 * 1024 * 1024:
                        cursor.close()
                        connection.close()
                        return render_template('start_fundraiser4.html', error="Image is too large even after compression. Please use a smaller image file (under 2MB recommended).")
                else:
                    cursor.close()
                    connection.close()
                    return render_template('start_fundraiser4.html', error=f"Image file is too large ({len(image_data) / 1024 / 1024:.1f}MB). Please compress it to under 2MB or install Pillow for automatic compression.")
            
            os.remove(fundraiser['image_path'])
            print(f"Image loaded and temp file cleaned: {fundraiser['image_path']}")
        except Exception as e:
            print(f"Error reading image file: {e}")
            traceback.print_exc()
            cursor.close()
            connection.close()
            return render_template('start_fundraiser4.html', error=f"Error processing image: {str(e)}")

    additional_images_data = []
    if 'additional_image_paths' in fundraiser:
        for i, image_path in enumerate(fundraiser['additional_image_paths']):
            if os.path.exists(image_path):
                try:
                    image_data_additional = compress_image(image_path)
                    if image_data_additional is None:
                        file_size = os.path.getsize(image_path)
                        if file_size > 5 * 1024 * 1024:
                            print(f"Warning: Additional image {i+1} is too large ({file_size / 1024 / 1024:.2f}MB), skipping.")
                            os.remove(image_path)
                            continue
                        with open(image_path, 'rb') as f:
                            image_data_additional = f.read()
                    
                    additional_images_data.append({
                        'data': image_data_additional,
                        'filename': os.path.basename(image_path),
                        'order': i + 1
                    })
                    os.remove(image_path)
                    print(f"Additional image {i+1} loaded and temp file cleaned: {image_path}")
                except Exception as e:
                    print(f"Error reading additional image file {image_path}: {e}")

    fund_type_mapping = {
        'animal_rescue': 'Animal Rescue & Welfare',
        'community': 'Community',
        'disaster_relief': 'Disaster Relief',
        'family': 'Family',
        'education': 'Education',
        'livelihood_support': 'Livelihood Support',
        'medical': 'Medical',
        'volunteer': 'Volunteer',
        'other': 'Other'
    }

    fund_category = fund_type_mapping.get(fundraiser.get('fund_type', 'other'), 'Other')
    
    sql = """
        INSERT INTO fundraisers
        (fund_title, fund_desc, fund_category, fund_img,
        fund_beneficiary, fund_goalamount, fund_link,
        fund_status, fund_startdate, fund_creatorid)
        VALUES (%s, %s, %s, %s, %s,
                %s, %s, %s,
                NOW(), %s)
    """
    values = (
        fundraiser['title'],
        fundraiser['story'],
        fund_category,
        image_data,
        None,  # fund_beneficiary - beneficiaries are managed separately
        fundraiser['goal_amount'],
        "generated-link",
        "Active",
        session['user_id']
    )

    cursor.execute(sql, values)
    connection.commit()

    fund_id = cursor.lastrowid
    print(f"New fundraiser ID: {fund_id}")

    if additional_images_data:
        for img_data in additional_images_data:
            try:
                cursor.execute("""
                    INSERT INTO fundraiser_images (fund_id, image_data, image_filename, image_order, is_primary, uploaded_date)
                    VALUES (%s, %s, %s, %s, %s, NOW())
                """, (fund_id, img_data['data'], img_data['filename'], img_data['order'], 0))
                print(f"Additional image saved: {img_data['filename']}")
            except Exception as e:
                print(f"Error saving additional image: {e}")

    connection.commit()
    print(f"All images saved successfully for fundraiser ID: {fund_id}")

    session.pop('fundraiser', None)

    print("Fundraiser saved successfully.")
    return redirect(url_for('start_fundraiser_6', fundraiser_id=fund_id))

@app.route('/start_fundraiser-6')
def start_fundraiser_6():
    if 'email' not in session:
        return redirect(url_for('goto_signin'))
    fund_id = request.args.get('fundraiser_id', type=int)
    return render_template('start_fundraiser6.html', fund_id=fund_id)

@app.route('/api/donation-verification/extract-reference', methods=['POST'])
def extract_donation_reference_from_screenshot():
    screenshot = request.files.get('payment_screenshot')
    if not screenshot or not screenshot.filename:
        return jsonify({'error': 'Missing payment screenshot'}), 400

    stored_filename = None
    try:
        temp_ref = f"ocr-{uuid.uuid4().hex[:10]}"
        stored_filename, error_message = save_payment_verification_screenshot(screenshot, temp_ref)
        if error_message:
            return jsonify({'error': error_message}), 400

        screenshot_path = os.path.join(PAYMENT_VERIFICATION_FOLDER, stored_filename)
        extracted_reference = extract_reference_number_with_openai(screenshot_path)

        return jsonify({
            'reference_number': extracted_reference or '',
            'detected': bool(extracted_reference)
        })
    except Exception as e:
        print(f"Reference extraction endpoint failed: {e}")
        return jsonify({'error': 'Unable to extract a reference number right now.'}), 500
    finally:
        if stored_filename:
            temp_path = os.path.join(PAYMENT_VERIFICATION_FOLDER, stored_filename)
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass

@app.route('/donation-verification/<int:fundraiser_id>/donation/<int:donation_id>', methods=['GET', 'POST'])
def donation_verification(fundraiser_id, donation_id):
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    error_message = None
    extracted_reference = ''

    try:
        cursor.execute("SELECT * FROM fundraisers WHERE fund_id = %s", (fundraiser_id,))
        fundraiser = cursor.fetchone()

        if not fundraiser:
            return "Fundraiser not found", 404

        cursor.execute("SELECT * FROM donations WHERE fund_id = %s AND don_id = %s", (fundraiser_id, donation_id))
        donation = cursor.fetchone()

        if not donation:
            return "Donation not found", 404

        if (donation.get('don_paymethod') or '').strip().upper() != 'QRPH':
            return redirect(url_for('donation_confirmation', fundraiser_id=fundraiser_id, donation_ref=donation['don_refnum']))

        if donation.get('don_status') != 'Paid':
            return redirect(url_for('qrph_payment_page', donation_id=donation_id))

        if is_qr_receipt_verified(donation['don_refnum']):
            return redirect(url_for('donation_confirmation', fundraiser_id=fundraiser_id, donation_ref=donation['don_refnum']))

        if request.method == 'POST':
            entered_reference = (request.form.get('reference_number') or '').strip()
            screenshot = request.files.get('payment_screenshot')
            screenshot_filename = None

            if screenshot and screenshot.filename:
                screenshot_filename, error_message = save_payment_verification_screenshot(screenshot, donation['don_refnum'])

            if error_message:
                return render_template(
                    'donation_verification.html',
                    fundraiser=fundraiser,
                    donation=donation,
                    error_message=error_message,
                    entered_reference=entered_reference,
                    extracted_reference=extracted_reference
                )

            final_reference = entered_reference

            if not final_reference:
                error_message = 'Enter a reference number in the field before continuing to the receipt.'

            if not error_message:
                update_donation_reference_number(
                    donation_id=donation['don_id'],
                    old_refnum=donation['don_refnum'],
                    new_refnum=final_reference,
                    conn=connection,
                    cursor=cursor
                )
                connection.commit()

                cursor.execute("""
                    SELECT don_refnum
                    FROM donations
                    WHERE don_id = %s
                    LIMIT 1
                """, (donation['don_id'],))
                updated_row = cursor.fetchone()
                persisted_reference = (updated_row or {}).get('don_refnum') if isinstance(updated_row, dict) else None

                if not persisted_reference:
                    raise ValueError(f"Updated reference number was not persisted for donation {donation['don_id']}.")

                verification_method = 'reference_number'
                mark_qr_receipt_verified(persisted_reference, verification_method, screenshot_filename=screenshot_filename)
                return redirect(url_for('donation_confirmation', fundraiser_id=fundraiser_id, donation_ref=persisted_reference))

        return render_template(
            'donation_verification.html',
            fundraiser=fundraiser,
            donation=donation,
            error_message=error_message,
            entered_reference='',
            extracted_reference=extracted_reference
        )
    finally:
        cursor.close()
        connection.close()

@app.route('/donation-confirmation/<int:fundraiser_id>/<donation_ref>')
def donation_confirmation(fundraiser_id, donation_ref):
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute("SELECT * FROM fundraisers WHERE fund_id = %s", (fundraiser_id,))
        fundraiser = cursor.fetchone()

        if not fundraiser:
            return "Fundraiser not found", 404

        cursor.execute("SELECT * FROM donations WHERE fund_id = %s AND don_refnum = %s", (fundraiser_id, donation_ref))
        donation = cursor.fetchone()

        if not donation:
            return "Donation not found", 404

        if donation['don_status'] == 'Pending' and (donation.get('don_paymethod') or '').strip().upper() != 'QRPH':
            success = update_donation_status(donation_ref, 'Paid')
            if success:
                cursor.execute("SELECT * FROM donations WHERE fund_id = %s AND don_refnum = %s", (fundraiser_id, donation_ref))
                donation = cursor.fetchone()

        if (
            (donation.get('don_paymethod') or '').strip().upper() == 'QRPH' and
            donation.get('don_status') == 'Paid' and
            not is_qr_receipt_verified(donation_ref)
        ):
            return redirect(url_for('donation_verification', fundraiser_id=fundraiser_id, donation_id=donation['don_id']))

        return render_template('donation_confirmation.html', 
            fundraiser=fundraiser, 
            donation=donation)
    finally:
        cursor.close()
        connection.close()

@app.route('/track-donation')
def track_donation():
    reference = (request.args.get('ref') or '').strip()
    if reference:
        return redirect(url_for('track_donation_by_ref', donation_ref=reference))

    if session.get('user_id'):
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute("""
                SELECT don_refnum
                FROM donations
                WHERE don_donorid = %s
                ORDER BY don_date DESC
                LIMIT 1
            """, (session.get('user_id'),))
            latest = cursor.fetchone()
            if latest and latest.get('don_refnum'):
                return redirect(url_for('track_donation_by_ref', donation_ref=latest['don_refnum'], auto=1))
        finally:
            cursor.close()
            connection.close()

    return render_template(
        'track_donation.html',
        query_ref='',
        donation=None,
        fundraiser=None,
        fundraiser_stats=None,
        beneficiary_stats=None,
        beneficiary_names=[],
        timeline=[],
        not_found=False,
        auto_loaded=False,
        user_recent_donations=[]
    )

@app.route('/track-donation/<donation_ref>')
def track_donation_by_ref(donation_ref):
    reference = (donation_ref or '').strip()
    if not reference:
        return redirect(url_for('track_donation'))

    auto_loaded = request.args.get('auto') == '1'
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        user_recent_donations = []
        if session.get('user_id'):
            cursor.execute("""
                SELECT don_refnum, don_amount, don_status, don_date
                FROM donations
                WHERE don_donorid = %s
                ORDER BY don_date DESC
                LIMIT 8
            """, (session.get('user_id'),))
            user_recent_donations = cursor.fetchall()

        cursor.execute("""
            SELECT
                d.don_id, d.fund_id, d.don_donorname, d.don_paymethod, d.don_amount,
                d.don_refnum, d.don_status, d.don_date, d.blockchain_tx_hash, d.block_number,
                f.fund_title, f.fund_goalamount, f.fund_status, f.fund_beneficiary
            FROM donations d
            JOIN fundraisers f ON d.fund_id = f.fund_id
            WHERE d.don_refnum = %s
            LIMIT 1
        """, (reference,))
        donation = cursor.fetchone()

        if not donation:
            return render_template(
                'track_donation.html',
                query_ref=reference,
                donation=None,
                fundraiser=None,
                fundraiser_stats=None,
                beneficiary_stats=None,
                beneficiary_names=[],
                timeline=[],
                not_found=True,
                auto_loaded=auto_loaded,
                user_recent_donations=user_recent_donations
            )

        cursor.execute("""
            SELECT
                COALESCE(SUM(CASE WHEN don_status = 'Paid' THEN don_amount ELSE 0 END), 0) as total_raised,
                COUNT(CASE WHEN don_status = 'Paid' THEN 1 END) as paid_donations
            FROM donations
            WHERE fund_id = %s
        """, (donation['fund_id'],))
        fundraiser_totals = cursor.fetchone()

        beneficiary_stats = {'total_beneficiaries': 0, 'verified_beneficiaries': 0}
        cursor.execute("""
            SELECT COUNT(*) as has_is_verified
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'beneficiaries'
              AND COLUMN_NAME = 'is_verified'
        """)
        has_verified_col = (cursor.fetchone() or {}).get('has_is_verified', 0) > 0

        if has_verified_col:
            cursor.execute("""
                SELECT
                    COUNT(*) as total_beneficiaries,
                    COUNT(CASE WHEN is_verified = 1 THEN 1 END) as verified_beneficiaries
                FROM beneficiaries
                WHERE fund_id = %s
            """, (donation['fund_id'],))
            beneficiary_stats = cursor.fetchone() or beneficiary_stats
        else:
            cursor.execute("""
                SELECT COUNT(*) as total_beneficiaries
                FROM beneficiaries
                WHERE fund_id = %s
            """, (donation['fund_id'],))
            row = cursor.fetchone() or {}
            beneficiary_stats = {
                'total_beneficiaries': row.get('total_beneficiaries', 0) or 0,
                'verified_beneficiaries': 0
            }

        beneficiary_names = []
        try:
            cursor.execute("""
                SELECT beneficiary_name
                FROM beneficiaries
                WHERE fund_id = %s
                  AND beneficiary_name IS NOT NULL
                  AND TRIM(beneficiary_name) <> ''
                ORDER BY beneficiary_name ASC
                LIMIT 120
            """, (donation['fund_id'],))
            beneficiary_names = [row.get('beneficiary_name') for row in cursor.fetchall() if row.get('beneficiary_name')]
        except Exception:
            beneficiary_names = []

        audit_rows = []
        try:
            cursor.execute("""
                SELECT action, event_time, status, after_data
                FROM audit_trail_logs
                WHERE entity_type = 'donation' AND entity_id IN (%s, %s)
                ORDER BY event_time ASC
                LIMIT 50
            """, (str(donation['don_id']), donation['don_refnum']))
            audit_rows = cursor.fetchall()
        except Exception:
            audit_rows = []

        status_history_rows = []
        try:
            cursor.execute("""
                SELECT status, previous_status, updated_at, updated_by, audit_id, note
                FROM donation_fund_status_history
                WHERE reference_number = %s
                ORDER BY updated_at ASC, history_id ASC
            """, (donation['don_refnum'],))
            status_history_rows = cursor.fetchall()
        except Exception:
            status_history_rows = []

        cursor.execute("""
            SELECT
                proof_id,
                proof_filename,
                original_filename,
                proof_note,
                uploaded_at
            FROM fund_completion_proofs
            WHERE fund_id = %s
            ORDER BY uploaded_at DESC, proof_id DESC
            LIMIT 1
        """, (donation['fund_id'],))
        fundraiser_completion_proof = cursor.fetchone()
        if fundraiser_completion_proof:
            fundraiser_completion_proof['public_url'] = url_for(
                'static',
                filename=f"uploads/{fundraiser_completion_proof['proof_filename']}"
            )

        cursor.execute("""
            SELECT
                proof_id,
                proof_filename,
                original_filename,
                proof_note,
                uploaded_at
            FROM donation_completion_proofs
            WHERE donation_id = %s
            ORDER BY uploaded_at DESC, proof_id DESC
            LIMIT 1
        """, (donation['don_id'],))
        donation_completion_proof = cursor.fetchone()
        if donation_completion_proof:
            donation_completion_proof['public_url'] = url_for(
                'static',
                filename=f"uploads/{donation_completion_proof['proof_filename']}"
            )

        status_timestamps = {}
        for row in status_history_rows:
            status_name = (row.get('status') or '').strip()
            if status_name in DONATION_FUND_STATUSES and status_name not in status_timestamps:
                status_timestamps[status_name] = row.get('updated_at')

        donation_history = []
        payment_confirmed_time = None
        funds_disbursed_time = None
        completed_time = None
        for row in audit_rows:
            after_data = {}
            try:
                after_data = json.loads(row.get('after_data') or '{}')
            except Exception:
                after_data = {}

            action = (row.get('action') or '').strip()
            status_data = (row.get('status') or '').strip()
            event_time = row.get('event_time')

            if action == 'DONATION_PAYMENT_CONFIRMED' or (action == 'DONATION_STATUS_UPDATED' and after_data.get('don_status') == 'Paid'):
                payment_confirmed_time = payment_confirmed_time or event_time
            if action == 'FUNDRAISER_COMPLETED':
                funds_disbursed_time = funds_disbursed_time or event_time
                completed_time = completed_time or event_time

            donation_history.append({
                'timestamp': event_time,
                'action': action,
                'status': status_data or after_data.get('don_status') or '',
                'details': after_data
            })

        for row in status_history_rows:
            donation_history.append({
                'timestamp': row.get('updated_at'),
                'action': 'DONATION_LIFECYCLE_STATUS',
                'status': row.get('status'),
                'details': {
                    'reference_number': donation['don_refnum'],
                    'previous_status': row.get('previous_status'),
                    'audit_id': row.get('audit_id'),
                    'note': row.get('note')
                }
            })
        donation_history.sort(key=lambda item: item.get('timestamp') or datetime.min)

        goal_amount = float(donation['fund_goalamount'] or 0)
        total_raised = float((fundraiser_totals or {}).get('total_raised') or 0)
        paid_count = int((fundraiser_totals or {}).get('paid_donations') or 0)
        donation_amount = float(donation['don_amount'] or 0)

        remaining_to_goal = max(goal_amount - total_raised, 0)
        progress_percent = min((total_raised / goal_amount) * 100, 100) if goal_amount > 0 else 0
        share_percent = (donation_amount / total_raised) * 100 if total_raised > 0 else 0

        payment_status = (donation['don_status'] or '').strip()
        current_lifecycle_status = None
        if status_history_rows:
            current_lifecycle_status = status_history_rows[-1].get('status')
        if current_lifecycle_status not in DONATION_FUND_STATUSES:
            current_lifecycle_status = 'Payment Confirmed' if payment_status == 'Paid' else 'Donation Received'

        fundraiser_completed = (donation.get('fund_status') or '').strip().lower() == 'completed'
        if fundraiser_completed and current_lifecycle_status != 'Completed / Used':
            current_lifecycle_status = 'Completed / Used'

        completion_proof = donation_completion_proof or fundraiser_completion_proof
        completion_proof_url = completion_proof.get('public_url') if completion_proof else None
        completion_proof_name = (
            completion_proof.get('original_filename')
            or completion_proof.get('proof_filename')
            if completion_proof else None
        )
        if current_lifecycle_status == 'Completed / Used' and completion_proof:
            status_timestamps['Completed / Used'] = (
                status_timestamps.get('Completed / Used')
                or completion_proof.get('uploaded_at')
            )

        current_lifecycle_index = DONATION_FUND_STATUSES.index(current_lifecycle_status)
        timeline_descriptions = {
            'Donation Received': 'Your donation has been recorded and is waiting for payment confirmation.',
            'Payment Confirmed': 'The payment has been verified and confirmed for allocation.',
            'Pending Allocation': 'The donation is queued for beneficiary allocation within the campaign.',
            'Funds Disbursed': 'The donation has been released for its intended relief use.',
            'Completed / Used': 'Your donation is now part of the completed relief effort.'
        }
        timeline = []
        for index, status_name in enumerate(DONATION_FUND_STATUSES):
            timestamp = status_timestamps.get(status_name)
            if status_name == 'Donation Received':
                timestamp = timestamp or donation['don_date']
            if status_name == 'Payment Confirmed':
                timestamp = timestamp or payment_confirmed_time
            timeline_item = {
                'title': status_name,
                'state': 'done' if index <= current_lifecycle_index else 'pending',
                'description': timeline_descriptions.get(status_name, ''),
                'timestamp': timestamp
            }
            if status_name == 'Completed / Used' and index <= current_lifecycle_index and completion_proof_url:
                timeline_item['completion_proof_url'] = completion_proof_url
                timeline_item['completion_proof_name'] = completion_proof_name
            timeline.append(timeline_item)

        if audit_rows:
            for row in audit_rows:
                action = (row.get('action') or '').strip()
                if action == 'DONATION_CREATED':
                    timeline[0]['timestamp'] = row.get('event_time')
                if action == 'DONATION_STATUS_UPDATED' and payment_status == 'Paid':
                    timeline[1]['timestamp'] = timeline[1]['timestamp'] or row.get('event_time')
                if action == 'DONATION_PAYMENT_CONFIRMED':
                    timeline[1]['timestamp'] = timeline[1]['timestamp'] or row.get('event_time')

        fundraiser_stats = {
            'goal_amount': goal_amount,
            'total_raised': total_raised,
            'remaining_to_goal': remaining_to_goal,
            'progress_percent': progress_percent,
            'donation_share_percent': share_percent,
            'paid_donations': paid_count
        }

        return render_template(
            'track_donation.html',
            query_ref=reference,
            donation=donation,
            fundraiser={
                'fund_id': donation['fund_id'],
                'fund_title': donation['fund_title'],
                'fund_status': donation['fund_status'],
                'fund_beneficiary': donation['fund_beneficiary'],
                'completion_proof_url': completion_proof_url,
                'completion_proof_name': completion_proof_name
            },
            fundraiser_stats=fundraiser_stats,
            beneficiary_stats=beneficiary_stats or {'total_beneficiaries': 0, 'verified_beneficiaries': 0},
            beneficiary_names=beneficiary_names,
            timeline=timeline,
            donation_history=donation_history,
            not_found=False,
            auto_loaded=auto_loaded,
            user_recent_donations=user_recent_donations
        )
    finally:
        cursor.close()
        connection.close()

@app.route('/fund-transparency')
def fund_transparency():
    page = request.args.get('page', 1, type=int)
    per_page = 12
    offset = (page - 1) * per_page
    search_query = (request.args.get('q') or '').strip()

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        params = []
        search_clause = ""
        if search_query:
            search_clause = """
                AND (
                    f.fund_title LIKE %s OR
                    f.fund_desc LIKE %s OR
                    COALESCE(f.fund_category, '') LIKE %s
                )
            """
            search_param = f"%{search_query}%"
            params.extend([search_param, search_param, search_param])

        count_query = f"""
            SELECT COUNT(*) AS total
            FROM fundraisers f
            WHERE f.fund_status IN ('Active', 'Completed')
            {search_clause}
        """
        cursor.execute(count_query, params)
        total_count = (cursor.fetchone() or {}).get('total', 0)

        fundraisers_query = f"""
            SELECT
                f.fund_id,
                f.fund_title,
                f.fund_desc,
                f.fund_category,
                f.fund_status,
                f.fund_goalamount,
                f.fund_startdate,
                f.fund_img,
                COALESCE(fp.proof_count, 0) + COALESCE(dp.proof_count, 0) AS proof_count,
                COALESCE(SUM(CASE WHEN d.don_status = 'Paid' THEN d.don_amount ELSE 0 END), 0) AS total_raised,
                COUNT(CASE WHEN d.don_status = 'Paid' THEN 1 END) AS paid_donations
            FROM fundraisers f
            LEFT JOIN donations d ON f.fund_id = d.fund_id
            LEFT JOIN (
                SELECT fund_id, COUNT(*) AS proof_count
                FROM fund_completion_proofs
                GROUP BY fund_id
            ) fp ON f.fund_id = fp.fund_id
            LEFT JOIN (
                SELECT fund_id, COUNT(*) AS proof_count
                FROM donation_completion_proofs
                GROUP BY fund_id
            ) dp ON f.fund_id = dp.fund_id
            WHERE f.fund_status IN ('Active', 'Completed')
            {search_clause}
            GROUP BY f.fund_id
            ORDER BY f.fund_startdate DESC
            LIMIT %s OFFSET %s
        """
        cursor.execute(fundraisers_query, params + [per_page, offset])
        fundraisers = cursor.fetchall()

        fundraiser_ids = [row['fund_id'] for row in fundraisers]
        beneficiary_stats_map = {}
        blockchain_counts_map = {}

        if fundraiser_ids:
            placeholders = ','.join(['%s'] * len(fundraiser_ids))

            cursor.execute("""
                SELECT COUNT(*) AS has_is_verified
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'beneficiaries'
                  AND COLUMN_NAME = 'is_verified'
            """)
            has_verified_col = ((cursor.fetchone() or {}).get('has_is_verified', 0) or 0) > 0

            if has_verified_col:
                cursor.execute(f"""
                    SELECT
                        fund_id,
                        COUNT(*) AS total_beneficiaries,
                        COUNT(CASE WHEN is_verified = 1 THEN 1 END) AS verified_beneficiaries
                    FROM beneficiaries
                    WHERE fund_id IN ({placeholders})
                    GROUP BY fund_id
                """, fundraiser_ids)
                for row in cursor.fetchall():
                    beneficiary_stats_map[row['fund_id']] = {
                        'total_beneficiaries': row.get('total_beneficiaries', 0) or 0,
                        'verified_beneficiaries': row.get('verified_beneficiaries', 0) or 0
                    }
            else:
                cursor.execute(f"""
                    SELECT
                        fund_id,
                        COUNT(*) AS total_beneficiaries
                    FROM beneficiaries
                    WHERE fund_id IN ({placeholders})
                    GROUP BY fund_id
                """, fundraiser_ids)
                for row in cursor.fetchall():
                    beneficiary_stats_map[row['fund_id']] = {
                        'total_beneficiaries': row.get('total_beneficiaries', 0) or 0,
                        'verified_beneficiaries': 0
                    }

            cursor.execute(f"""
                SELECT
                    fund_id,
                    COUNT(*) AS blockchain_records
                FROM donations
                WHERE fund_id IN ({placeholders})
                  AND don_status = 'Paid'
                  AND blockchain_tx_hash IS NOT NULL
                  AND TRIM(blockchain_tx_hash) <> ''
                GROUP BY fund_id
            """, fundraiser_ids)
            for row in cursor.fetchall():
                blockchain_counts_map[row['fund_id']] = row.get('blockchain_records', 0) or 0

        for fundraiser in fundraisers:
            goal_amount = float(fundraiser.get('fund_goalamount') or 0)
            total_raised = float(fundraiser.get('total_raised') or 0)
            progress_percent = min((total_raised / goal_amount) * 100, 100) if goal_amount > 0 else 0
            beneficiary_stats = beneficiary_stats_map.get(
                fundraiser['fund_id'],
                {'total_beneficiaries': 0, 'verified_beneficiaries': 0}
            )
            fundraiser['progress_percent'] = progress_percent
            fundraiser['transparency_stats'] = beneficiary_stats
            fundraiser['blockchain_records'] = blockchain_counts_map.get(fundraiser['fund_id'], 0)
            fundraiser['proof_count'] = int(fundraiser.get('proof_count') or 0)

        total_pages = max(1, math.ceil(total_count / per_page)) if total_count else 1
        pagination = {
            'page': page,
            'per_page': per_page,
            'total': total_count,
            'total_pages': total_pages,
            'has_prev': page > 1,
            'has_next': page < total_pages,
            'prev_num': page - 1 if page > 1 else None,
            'next_num': page + 1 if page < total_pages else None
        }

        return render_template(
            'fund_transparency.html',
            fundraisers=fundraisers,
            search_query=search_query,
            pagination=pagination
        )
    finally:
        cursor.close()
        connection.close()

@app.route('/fund-transparency/<int:fundraiser_id>')
def fund_transparency_detail(fundraiser_id):
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT
                f.*,
                u.name AS creator_name,
                u.email AS creator_email
            FROM fundraisers f
            LEFT JOIN users u ON f.fund_creatorid = u.id
            WHERE f.fund_id = %s
              AND f.fund_status IN ('Active', 'Completed')
        """, (fundraiser_id,))
        fundraiser = cursor.fetchone()

        if not fundraiser:
            return "Fundraiser not found", 404

        cursor.execute("""
            SELECT
                COUNT(CASE WHEN don_status = 'Paid' THEN 1 END) AS paid_donations,
                COALESCE(SUM(CASE WHEN don_status = 'Paid' THEN don_amount ELSE 0 END), 0) AS total_raised,
                COALESCE(AVG(CASE WHEN don_status = 'Paid' THEN don_amount END), 0) AS avg_donation,
                COALESCE(MAX(CASE WHEN don_status = 'Paid' THEN don_amount END), 0) AS top_donation
            FROM donations
            WHERE fund_id = %s
        """, (fundraiser_id,))
        fundraiser_totals = cursor.fetchone() or {}

        cursor.execute("""
            SELECT
                d.don_id,
                don_refnum,
                don_donorname,
                don_amount,
                don_date,
                don_paymethod,
                blockchain_tx_hash,
                COALESCE(dfs.current_status, 'Donation Received') AS fund_usage_status,
                dp.proof_count
            FROM donations d
            LEFT JOIN donation_fund_status dfs ON d.don_refnum = dfs.reference_number
            LEFT JOIN (
                SELECT donation_id, COUNT(*) AS proof_count
                FROM donation_completion_proofs
                GROUP BY donation_id
            ) dp ON d.don_id = dp.donation_id
            WHERE d.fund_id = %s
              AND d.don_status = 'Paid'
            ORDER BY d.don_date DESC
            LIMIT 8
        """, (fundraiser_id,))
        recent_paid_donations = cursor.fetchall()

        cursor.execute("""
            SELECT
                dp.proof_id,
                dp.donation_id,
                dp.proof_filename,
                dp.original_filename,
                dp.proof_note,
                dp.uploaded_at,
                d.don_refnum,
                d.don_donorname,
                d.don_amount
            FROM donation_completion_proofs dp
            JOIN donations d ON dp.donation_id = d.don_id
            WHERE dp.fund_id = %s
            ORDER BY dp.uploaded_at DESC, dp.proof_id DESC
        """, (fundraiser_id,))
        donation_completion_proofs = cursor.fetchall()
        for proof in donation_completion_proofs:
            proof['public_url'] = url_for('static', filename=f"uploads/{proof['proof_filename']}")

        cursor.execute("""
            SELECT COUNT(*) AS has_is_verified
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'beneficiaries'
              AND COLUMN_NAME = 'is_verified'
        """)
        has_verified_col = ((cursor.fetchone() or {}).get('has_is_verified', 0) or 0) > 0

        if has_verified_col:
            cursor.execute("""
                SELECT
                    COUNT(*) AS total_beneficiaries,
                    COUNT(CASE WHEN is_verified = 1 THEN 1 END) AS verified_beneficiaries
                FROM beneficiaries
                WHERE fund_id = %s
            """, (fundraiser_id,))
            beneficiary_stats = cursor.fetchone() or {
                'total_beneficiaries': 0,
                'verified_beneficiaries': 0
            }
        else:
            cursor.execute("""
                SELECT COUNT(*) AS total_beneficiaries
                FROM beneficiaries
                WHERE fund_id = %s
            """, (fundraiser_id,))
            row = cursor.fetchone() or {}
            beneficiary_stats = {
                'total_beneficiaries': row.get('total_beneficiaries', 0) or 0,
                'verified_beneficiaries': 0
            }

        cursor.execute("""
            SELECT beneficiary_name
            FROM beneficiaries
            WHERE fund_id = %s
              AND beneficiary_name IS NOT NULL
              AND TRIM(beneficiary_name) <> ''
            ORDER BY beneficiary_name ASC
            LIMIT 120
        """, (fundraiser_id,))
        beneficiary_names = [
            row.get('beneficiary_name')
            for row in cursor.fetchall()
            if row.get('beneficiary_name')
        ]

        cursor.execute("""
            SELECT
                COUNT(*) AS blockchain_records,
                MAX(don_date) AS latest_blockchain_entry
            FROM donations
            WHERE fund_id = %s
              AND don_status = 'Paid'
              AND blockchain_tx_hash IS NOT NULL
              AND TRIM(blockchain_tx_hash) <> ''
        """, (fundraiser_id,))
        blockchain_summary = cursor.fetchone() or {
            'blockchain_records': 0,
            'latest_blockchain_entry': None
        }

        cursor.execute("""
            SELECT
                proof_id,
                audit_id,
                proof_filename,
                original_filename,
                proof_mime_type,
                proof_note,
                uploaded_at
            FROM fund_completion_proofs
            WHERE fund_id = %s
            ORDER BY uploaded_at DESC, proof_id DESC
        """, (fundraiser_id,))
        completion_proofs = cursor.fetchall()
        for proof in completion_proofs:
            proof['public_url'] = url_for('static', filename=f"uploads/{proof['proof_filename']}")

        fundraiser_has_completion_proof = bool(completion_proofs)
        fundraiser_completion_is_public = (
            (fundraiser.get('fund_status') or '').strip().lower() == 'completed'
            and fundraiser_has_completion_proof
        )

        if fundraiser_completion_is_public:
            for donation in recent_paid_donations:
                donation['fund_usage_status'] = 'Completed / Used'

        fundraiser_audit_rows = []
        try:
            cursor.execute("""
                SELECT action, entity_type, entity_id, event_time, status, before_data, after_data, metadata
                FROM audit_trail_logs
                WHERE (
                    entity_type = 'fundraiser'
                    AND entity_id = %s
                )
                OR (
                    entity_type = 'donation'
                    AND entity_id IN (
                        SELECT CAST(don_id AS CHAR)
                        FROM donations
                        WHERE fund_id = %s
                    )
                )
                ORDER BY event_time ASC
                LIMIT 120
            """, (fundraiser_id, fundraiser_id))
            fundraiser_audit_rows = cursor.fetchall()
        except Exception as audit_error:
            print(f"Fund transparency audit lookup skipped: {audit_error}")
            fundraiser_audit_rows = []

        goal_amount = float(fundraiser.get('fund_goalamount') or 0)
        total_raised = float(fundraiser_totals.get('total_raised') or 0)
        paid_donations = int(fundraiser_totals.get('paid_donations') or 0)
        progress_percent = min((total_raised / goal_amount) * 100, 100) if goal_amount > 0 else 0
        remaining_to_goal = max(goal_amount - total_raised, 0)

        public_summary = {
            'goal_amount': goal_amount,
            'total_raised': total_raised,
            'remaining_to_goal': remaining_to_goal,
            'progress_percent': progress_percent,
            'paid_donations': paid_donations,
            'avg_donation': float(fundraiser_totals.get('avg_donation') or 0),
            'top_donation': float(fundraiser_totals.get('top_donation') or 0),
            'blockchain_records': int(blockchain_summary.get('blockchain_records') or 0),
            'completion_proofs': len(completion_proofs) + len(donation_completion_proofs)
        }

        transparency_timeline = [
            {
                'title': 'Fundraiser Published',
                'state': 'done',
                'description': 'This fundraiser is visible to donors and can receive support.',
                'timestamp': fundraiser.get('fund_startdate')
            },
            {
                'title': 'Donation Pool Tracking',
                'state': 'done' if paid_donations > 0 else 'pending',
                'description': 'Paid donations are added to the campaign total displayed on this page.',
                'timestamp': recent_paid_donations[-1]['don_date'] if recent_paid_donations else None
            },
            {
                'title': 'Beneficiary Records Maintained',
                'state': 'done' if beneficiary_stats.get('total_beneficiaries', 0) > 0 else 'pending',
                'description': 'Beneficiary records for this fundraiser are registered in the platform.',
                'timestamp': None
            },
            {
                'title': 'Fund Status Completed',
                'state': 'done' if fundraiser.get('fund_status') == 'Completed' else 'pending',
                'description': 'The fundraiser status changes are logged with date and time in the audit history.',
                'timestamp': None
            },
            {
                'title': 'Blockchain Transparency Available',
                'state': 'done' if public_summary['blockchain_records'] > 0 else 'pending',
                'description': 'Blockchain-backed donation records can be viewed for verified donation entries.',
                'timestamp': blockchain_summary.get('latest_blockchain_entry')
            },
            {
                'title': 'Completion Proof Published',
                'state': 'done' if fundraiser_has_completion_proof else 'pending',
                'description': 'Treasurer-uploaded receipt or activity proof is publicly available after completion.',
                'timestamp': completion_proofs[0]['uploaded_at'] if fundraiser_has_completion_proof else None
            }
        ]

        fund_history = []
        for row in fundraiser_audit_rows:
            after_data = {}
            try:
                after_data = json.loads(row.get('after_data') or '{}')
            except Exception:
                after_data = {}

            action = (row.get('action') or '').strip()
            if action == 'FUNDRAISER_CREATED':
                transparency_timeline[0]['timestamp'] = row.get('event_time')
            if action == 'FUNDRAISER_COMPLETED':
                transparency_timeline[3]['timestamp'] = row.get('event_time')
                transparency_timeline[3]['state'] = 'done'
            if action == 'FUND_COMPLETION_PROOF_UPLOADED':
                transparency_timeline[5]['state'] = 'done'
                transparency_timeline[5]['timestamp'] = row.get('event_time')

            public_details = {
                key: after_data.get(key)
                for key in (
                    'fund_id',
                    'don_id',
                    'don_refnum',
                    'don_status',
                    'fund_status',
                    'workflow_status',
                    'status_changed',
                    'don_amount',
                    'total_raised',
                    'proof_id',
                    'proof_note',
                    'action_datetime'
                )
                if key in after_data
            }

            fund_history.append({
                'timestamp': row.get('event_time'),
                'action': action.replace('_', ' ').title(),
                'status': (row.get('status') or '').strip() or 'SUCCESS',
                'details': public_details
            })

        return render_template(
            'fund_transparency_detail.html',
            fundraiser=fundraiser,
            public_summary=public_summary,
            beneficiary_stats=beneficiary_stats,
            beneficiary_names=beneficiary_names,
            recent_paid_donations=recent_paid_donations,
            transparency_timeline=transparency_timeline,
            fund_history=fund_history,
            completion_proofs=completion_proofs,
            donation_completion_proofs=donation_completion_proofs,
            fundraiser_completion_is_public=fundraiser_completion_is_public
        )
    finally:
        cursor.close()
        connection.close()

@app.route('/view_fundraiser/<int:fundraiser_id>')
def view_fundraiser(fundraiser_id):
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    cursor.execute("""
        SELECT f.*, u.name as creator_name, u.email as creator_email
        FROM fundraisers f
        LEFT JOIN users u ON f.fund_creatorid = u.id
        WHERE f.fund_id = %s
    """, (fundraiser_id,))
    fundraiser = cursor.fetchone()

    if not fundraiser:
        cursor.close()
        connection.close()
        return "Fundraiser not found", 404

    if 'email' in session:
        cursor.execute("SELECT id FROM users WHERE email = %s", (session['email'],))
        user = cursor.fetchone()
        
        if user and fundraiser['fund_creatorid'] == user['id']:
            cursor.close()
            connection.close()
            return redirect(url_for('manage_fundraiser', fundraiser_id=fundraiser_id))

    cursor.execute("SELECT * FROM donations WHERE fund_id = %s ORDER BY don_date ASC", (fundraiser_id,))
    donations = cursor.fetchall()

    cursor.execute("""
        SELECT
            proof_id,
            proof_filename,
            original_filename,
            proof_note,
            uploaded_at
        FROM fund_completion_proofs
        WHERE fund_id = %s
        ORDER BY uploaded_at DESC, proof_id DESC
        LIMIT 1
    """, (fundraiser_id,))
    completion_proof = cursor.fetchone()
    if completion_proof:
        completion_proof['public_url'] = url_for(
            'static',
            filename=f"uploads/{completion_proof['proof_filename']}"
        )

    def enrich_donation_record(donation):
        if not donation:
            return donation

        payload_hash = None
        try:
            notes = donation.get('don_notes')
            if notes:
                notes_json = json.loads(notes)
                payload_hash = notes_json.get('plaintext_sha256') if isinstance(notes_json, dict) else None
        except Exception:
            payload_hash = None

        tx_hash = donation.get('blockchain_tx_hash')
        if tx_hash:
            tx_hash = str(tx_hash)
            if not tx_hash.startswith('0x'):
                tx_hash = '0x' + tx_hash

        donation['amount'] = float(donation.get('don_amount') or 0)
        donation['refnum'] = donation.get('don_refnum')
        donation['status'] = donation.get('don_status')
        donation['date'] = donation.get('don_date')
        donation['wallet'] = donation.get('donor_wallet_address') or 'Not provided'
        donation['tx_hash'] = tx_hash
        donation['block_number'] = donation.get('block_number')
        donation['payload_hash'] = payload_hash
        return donation

    donations = [enrich_donation_record(donation) for donation in donations]

    cursor.execute("""
        SELECT image_id, image_filename, image_order, is_primary, uploaded_date
        FROM fundraiser_images 
        WHERE fund_id = %s 
        ORDER BY is_primary DESC, image_order ASC, uploaded_date ASC
    """, (fundraiser_id,))
    additional_images = cursor.fetchall()

    total_raised = sum(d['don_amount'] for d in donations if d['don_status'] == 'Paid') if donations else 0

    cursor.execute("SELECT * FROM donations WHERE fund_id = %s ORDER BY don_amount DESC, don_date ASC LIMIT 1", (fundraiser_id,))
    top_donation = enrich_donation_record(cursor.fetchone())

    cursor.execute("SELECT * FROM donations WHERE fund_id = %s ORDER BY don_date DESC LIMIT 1", (fundraiser_id,))
    recent_donation = enrich_donation_record(cursor.fetchone())

    cursor.execute("SELECT * FROM donations WHERE fund_id = %s ORDER BY don_date ASC LIMIT 1", (fundraiser_id,))
    first_donation = enrich_donation_record(cursor.fetchone())

    cursor.close()
    connection.close()

    return render_template(
        'fundraiser.html',
        fundraiser=fundraiser,
        donations=donations,
        total_raised=total_raised,
        top_donation=top_donation,
        recent_donation=recent_donation,
        first_donation=first_donation,
        additional_images=additional_images,
        completion_proof=completion_proof
    )


# -----------------------------------------------------------------------
# -------------------------------- ADMIN --------------------------------
# -----------------------------------------------------------------------

@app.route('/admin/dashboard', methods=['GET', 'POST'])
def admin():
    if 'email' not in session or session.get('role') != 'Admin':
        return redirect(url_for('goto_signin'))
    
    app.permanent_session_lifetime = timedelta(hours=10)

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT f.*, 
            COALESCE(SUM(CASE WHEN d.don_status = 'Paid' THEN d.don_amount ELSE 0 END), 0) AS total_raised
        FROM fundraisers f
        LEFT JOIN donations d ON f.fund_id = d.fund_id AND d.don_status = 'Paid'
        GROUP BY f.fund_id
        ORDER BY f.fund_startdate DESC
    """)
    fundraisers = cursor.fetchall()

    cursor.execute("SELECT * FROM users WHERE role != 'Admin' AND role != 'Bot' AND role != 'Treasurer' ORDER BY date_created DESC")
    users = cursor.fetchall()

    cursor.execute("""
        SELECT COUNT(*) as total_donations, 
            COALESCE(SUM(CASE WHEN don_status = 'Paid' THEN don_amount ELSE 0 END), 0) as total_amount,
            COUNT(DISTINCT don_donorid) as unique_donors
        FROM donations 
        WHERE don_status = 'Paid'
    """)
    donation_stats = cursor.fetchone()

    cursor.execute("""
        SELECT COUNT(*) as recent_fundraisers
        FROM fundraisers 
        WHERE fund_startdate >= DATE_SUB(NOW(), INTERVAL 30 DAY)
    """)
    recent_activity = cursor.fetchone()

    cursor.execute("""
        SELECT COUNT(*) as recent_users
        FROM users 
        WHERE date_created >= DATE_SUB(NOW(), INTERVAL 30 DAY)
        AND role != 'Admin' AND role != 'Bot' AND role != 'Treasurer'
    """)
    recent_users = cursor.fetchone()

    cursor.execute("""
        SELECT COUNT(*) as recent_donations
        FROM donations 
        WHERE don_date >= DATE_SUB(NOW(), INTERVAL 30 DAY)
        AND don_status = 'Paid'
    """)
    recent_donations = cursor.fetchone()

    pending_count = len([f for f in fundraisers if f['fund_status'] == 'Pending'])

    valid_categories = [
        'Animal Rescue & Welfare',
        'Community',
        'Disaster Relief',
        'Family',
        'Education',
        'Livelihood Support',
        'Medical',
        'Volunteer',
        'Other'
    ]

    category_counts = {category: 0 for category in valid_categories}

    for f in fundraisers:
        original_category = (f['fund_category'] or '').strip()

        if original_category in valid_categories:
            category = original_category
        else:
            category = 'Other'

        category_counts[category] = category_counts.get(category, 0) + 1

    incident_analytics = {}
    for f in fundraisers:
        original_category = (f['fund_category'] or '').strip()

        if original_category in valid_categories:
            category = original_category
        else:
            category = 'Other'
        
        if category not in incident_analytics:
            incident_analytics[category] = {
                'total_fundraisers': 0,
                'total_goal_amount': 0,
                'total_raised': 0,
                'active_fundraisers': 0,
                'pending_fundraisers': 0,
                'disapproved_fundraisers': 0,
                'avg_goal_amount': 0,
                'avg_raised_amount': 0,
                'success_rate': 0
            }
        
        incident_analytics[category]['total_fundraisers'] += 1
        incident_analytics[category]['total_goal_amount'] += float(f['fund_goalamount'] or 0)
        incident_analytics[category]['total_raised'] += float(f['total_raised'] or 0)
        
        if f['fund_status'] == 'Active':
            incident_analytics[category]['active_fundraisers'] += 1
        elif f['fund_status'] == 'Pending':
            incident_analytics[category]['pending_fundraisers'] += 1
        elif f['fund_status'] == 'Disapproved':
            incident_analytics[category]['disapproved_fundraisers'] += 1
    
    for category, data in incident_analytics.items():
        if data['total_fundraisers'] > 0:
            data['avg_goal_amount'] = data['total_goal_amount'] / data['total_fundraisers']
            data['avg_raised_amount'] = data['total_raised'] / data['total_fundraisers']
            data['success_rate'] = (data['total_raised'] / data['total_goal_amount'] * 100) if data['total_goal_amount'] > 0 else 0

    chart_data = {
        'status_counts': {
            'Active': len([f for f in fundraisers if f['fund_status'] == 'Active']),
            'Pending': pending_count,
            'Disapproved': len([f for f in fundraisers if f['fund_status'] == 'Disapproved']),
            'Completed': len([f for f in fundraisers if f['fund_status'] == 'Completed'])
        },
        'category_counts': category_counts,
        'incident_analytics': incident_analytics,
        'fundraisers_data': [
            {
                'fund_title': f['fund_title'],
                'fund_category': f['fund_category'],
                'fund_startdate': f['fund_startdate'].isoformat() if f['fund_startdate'] else '',
                'total_raised': float(f['total_raised']) if f['total_raised'] else 0
            } for f in fundraisers
        ]
    }

    admin_stats = {
        'total_fundraisers': len(fundraisers),
        'total_users': len(users),
        'active_campaigns': len([f for f in fundraisers if f['fund_status'] == 'Active']),
        'pending_approval': pending_count,
        'total_donations': donation_stats['total_donations'],
        'total_amount_raised': float(donation_stats['total_amount']),
        'unique_donors': donation_stats['unique_donors'],
        'recent_fundraisers': recent_activity['recent_fundraisers'],
        'recent_users': recent_users['recent_users'],
        'recent_donations': recent_donations['recent_donations']
    }

    cursor.close()
    conn.close()

    return render_template('admin.html', fundraisers=fundraisers, users=users, chart_data=chart_data, admin_stats=admin_stats)

@app.route('/admin/fundraisers')
def admin_funds():
    if 'email' not in session or session.get('role') != 'Admin':
        return redirect(url_for('goto_signin'))
    
    app.permanent_session_lifetime = timedelta(hours=10)

    page = request.args.get('page', 1, type=int)
    per_page = 15

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT COUNT(*) as total FROM fundraisers")
    total_count = cursor.fetchone()['total']
    
    total_pages = (total_count + per_page - 1) // per_page
    offset = (page - 1) * per_page

    cursor.execute("""
        SELECT f.*, 
            COALESCE(SUM(CASE WHEN d.don_status = 'Paid' THEN d.don_amount ELSE 0 END), 0) AS total_raised
        FROM fundraisers f
        LEFT JOIN donations d ON f.fund_id = d.fund_id AND d.don_status = 'Paid'
        GROUP BY f.fund_id
        ORDER BY f.fund_startdate DESC
        LIMIT %s OFFSET %s
    """, (per_page, offset))
    fundraisers = cursor.fetchall()

    cursor.close()
    conn.close()

    pagination = {
        'page': page,
        'per_page': per_page,
        'total': total_count,
        'total_pages': total_pages,
        'has_prev': page > 1,
        'has_next': page < total_pages,
        'prev_num': page - 1 if page > 1 else None,
        'next_num': page + 1 if page < total_pages else None
    }

    return render_template('admin_funds.html', fundraisers=fundraisers, pagination=pagination)

@app.route('/admin/users')
def admin_users():
    if 'email' not in session or session.get('role') != 'Admin':
        return redirect(url_for('goto_signin'))
    
    app.permanent_session_lifetime = timedelta(hours=10)

    page = request.args.get('page', 1, type=int)
    per_page = 15

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT COUNT(*) as total FROM users WHERE role != 'Admin' AND role != 'Bot'")
    total_count = cursor.fetchone()['total']
    
    total_pages = (total_count + per_page - 1) // per_page
    offset = (page - 1) * per_page

    cursor.execute("""
        SELECT * FROM users 
        WHERE role != 'Admin' AND role != 'Bot'
        ORDER BY date_created DESC
        LIMIT %s OFFSET %s
    """, (per_page, offset))
    users = cursor.fetchall()

    cursor.close()
    conn.close()

    pagination = {
        'page': page,
        'per_page': per_page,
        'total': total_count,
        'total_pages': total_pages,
        'has_prev': page > 1,
        'has_next': page < total_pages,
        'prev_num': page - 1 if page > 1 else None,
        'next_num': page + 1 if page < total_pages else None
    }

    return render_template('admin_users.html', users=users, pagination=pagination)

@app.route('/admin/reports')
def admin_reports():
    if 'email' not in session or session.get('role') != 'Admin':
        return redirect(url_for('goto_signin'))
    
    app.permanent_session_lifetime = timedelta(hours=10)

    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')
    incident_types = request.args.get('incident_types', '')
    fundraiser_statuses = request.args.get('fundraiser_statuses', '')
    report_types = request.args.get('report_types', 'fundraisers,users,donations,incidents')
    
    selected_types = [t.strip() for t in report_types.split(',') if t.strip()]
    
    if not start_date:
        start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    if not end_date:
        end_date = datetime.now().strftime('%Y-%m-%d')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    fundraisers = []
    users = []
    donations = []
    incidents = []
    incident_summary = {}
    
    if 'fundraisers' in selected_types:
        fundraiser_query = """
            SELECT f.*, 
                COALESCE(SUM(CASE WHEN d.don_status = 'Paid' THEN d.don_amount ELSE 0 END), 0) AS total_raised
            FROM fundraisers f
            LEFT JOIN donations d ON f.fund_id = d.fund_id AND d.don_status = 'Paid'
            WHERE f.fund_startdate >= %s AND f.fund_startdate <= %s
        """
        fundraiser_params = [start_date, end_date]

        selected_fundraiser_statuses = [s.strip() for s in fundraiser_statuses.split(',') if s.strip()]
        if selected_fundraiser_statuses:
            placeholders = ','.join(['%s'] * len(selected_fundraiser_statuses))
            fundraiser_query += f" AND f.fund_status IN ({placeholders})"
            fundraiser_params.extend(selected_fundraiser_statuses)

        fundraiser_query += """
            GROUP BY f.fund_id
            ORDER BY f.fund_startdate DESC
        """

        cursor.execute(fundraiser_query, fundraiser_params)
        fundraisers = cursor.fetchall()

    if 'users' in selected_types:
        cursor.execute("""
            SELECT * FROM users 
            WHERE role != 'Admin' AND role != 'Bot' AND role != 'Treasurer'
            AND date_created >= %s AND date_created <= %s
            ORDER BY date_created DESC
        """, (start_date, end_date))
        users = cursor.fetchall()

    if 'donations' in selected_types:
        cursor.execute("""
            SELECT d.*, f.fund_title
            FROM donations d
            JOIN fundraisers f ON d.fund_id = f.fund_id
            WHERE d.don_date >= %s AND d.don_date <= %s
            ORDER BY d.don_date DESC
        """, (start_date, end_date))
        donations = cursor.fetchall()

    if 'incidents' in selected_types:
        query = """
            SELECT f.*, 
                COALESCE(SUM(CASE WHEN d.don_status = 'Paid' THEN d.don_amount ELSE 0 END), 0) AS total_raised,
                f.fund_category
            FROM fundraisers f
            LEFT JOIN donations d ON f.fund_id = d.fund_id AND d.don_status = 'Paid'
            WHERE f.fund_startdate >= %s AND f.fund_startdate <= %s
        """
        params = [start_date, end_date]
        
        if incident_types:
            selected_incident_types = [t.strip() for t in incident_types.split(',') if t.strip()]
            if selected_incident_types:
                placeholders = ','.join(['%s'] * len(selected_incident_types))
                query += f" AND f.fund_category IN ({placeholders})"
                params.extend(selected_incident_types)
            
        query += " GROUP BY f.fund_id ORDER BY f.fund_startdate DESC"
        
        cursor.execute(query, params)
        incidents = cursor.fetchall()

    if incidents:
        summary_data = {}
        for incident in incidents:
            category = incident['fund_category'] or 'Other'
            if category not in summary_data:
                summary_data[category] = {
                    'count': 0,
                    'total_goal': 0,
                    'total_raised': 0
                }
            
            summary_data[category]['count'] += 1
            summary_data[category]['total_goal'] += incident['fund_goalamount'] or 0
            summary_data[category]['total_raised'] += incident['total_raised'] or 0
        
        for category, stats in summary_data.items():
            if stats['total_goal'] > 0:
                stats['completion_rate'] = (stats['total_raised'] / stats['total_goal']) * 100
            else:
                stats['completion_rate'] = 0
            incident_summary[category] = stats

    total_revenue = sum(d['don_amount'] for d in donations if d['don_status'] == 'Paid')

    def _format_report_date(date_str):
        try:
            parsed_date = datetime.strptime(date_str, '%Y-%m-%d')
            return f"{parsed_date.strftime('%B')} {parsed_date.day}, {parsed_date.year}"
        except (TypeError, ValueError):
            return date_str

    formatted_start_date = _format_report_date(start_date)
    formatted_end_date = _format_report_date(end_date)
    
    report_stats = {
        'total_fundraisers': len(fundraisers),
        'total_users': len(users),
        'total_donations': len(donations),
        'total_incidents': len(incidents),
        'total_revenue': total_revenue,
        'date_range': f"{formatted_start_date} - {formatted_end_date}",
        'generated_date': datetime.now().strftime('%B %d, %Y')
    }

    cursor.close()
    conn.close()

    selected_incident_types = []
    if incident_types:
        selected_incident_types = [t.strip() for t in incident_types.split(',') if t.strip()]

    selected_fundraiser_statuses = []
    if fundraiser_statuses:
        selected_fundraiser_statuses = [s.strip() for s in fundraiser_statuses.split(',') if s.strip()]

    return render_template('admin_reports.html', 
        fundraisers=fundraisers, 
        users=users, 
        donations=donations,
        incidents=incidents,
        incident_summary=incident_summary,
        report_stats=report_stats,
        start_date=start_date,
        end_date=end_date,
        selected_fundraiser_statuses=selected_fundraiser_statuses,
        selected_incident_types=selected_incident_types,
        selected_types=selected_types
    )

@app.route('/admin/fundraiser/<int:fundraiser_id>')
def admin_view_fundraiser(fundraiser_id):
    if 'email' not in session or session.get('role') != 'Admin':
        return redirect(url_for('goto_signin'))
    
    app.permanent_session_lifetime = timedelta(hours=10)

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute("SELECT * FROM fundraisers WHERE fund_id = %s", (fundraiser_id,))
        fundraiser = cursor.fetchone()

        if not fundraiser:
            return "Fundraiser not found", 404

        cursor.execute("""
            SELECT d.*, u.name as donor_name, u.email as donor_email
            FROM donations d
            LEFT JOIN users u ON d.don_donorid = u.id
            WHERE d.fund_id = %s
            ORDER BY d.don_date DESC
        """, (fundraiser_id,))
        donations = cursor.fetchall()

        cursor.execute("""
            SELECT 
                COALESCE(COUNT(*), 0) as total_donations,
                COALESCE(COUNT(CASE WHEN don_status = 'Paid' THEN 1 END), 0) as paid_donations,
                COALESCE(COUNT(CASE WHEN don_status = 'Pending' THEN 1 END), 0) as pending_donations,
                COALESCE(COUNT(CASE WHEN don_status = 'Failed' THEN 1 END), 0) as failed_donations,
                COALESCE(SUM(CASE WHEN don_status = 'Paid' THEN don_amount ELSE 0 END), 0) as total_raised,
                COALESCE(AVG(CASE WHEN don_status = 'Paid' THEN don_amount END), 0) as avg_donation,
                COALESCE(MAX(CASE WHEN don_status = 'Paid' THEN don_amount END), 0) as max_donation,
                COALESCE(MIN(CASE WHEN don_status = 'Paid' THEN don_amount END), 0) as min_donation
            FROM donations 
            WHERE fund_id = %s
        """, (fundraiser_id,))
        donation_stats = cursor.fetchone()
        
        if donation_stats is None:
            donation_stats = {
                'total_donations': 0,
                'paid_donations': 0,
                'pending_donations': 0,
                'failed_donations': 0,
                'total_raised': 0,
                'avg_donation': 0,
                'max_donation': 0,
                'min_donation': 0
            }

        cursor.execute("""
            SELECT don_donorname, SUM(CASE WHEN don_status = 'Paid' THEN don_amount ELSE 0 END) as total_donated, COUNT(*) as donation_count
            FROM donations 
            WHERE fund_id = %s AND don_status = 'Paid'
            GROUP BY don_donorname
            ORDER BY total_donated DESC
            LIMIT 10
        """, (fundraiser_id,))
        top_donors = cursor.fetchall()

        cursor.execute("""
            SELECT d.*, u.name as donor_name, u.email as donor_email
            FROM donations d
            LEFT JOIN users u ON d.don_donorid = u.id
            WHERE d.fund_id = %s
            ORDER BY d.don_date DESC
            LIMIT 20
        """, (fundraiser_id,))
        recent_donations = cursor.fetchall()

        cursor.execute("""
            SELECT name, email, number, date_created
            FROM users 
            WHERE id = %s
        """, (fundraiser['fund_creatorid'],))
        creator = cursor.fetchone()
        
        if not creator:
            creator = {
                'name': 'Unknown User',
                'email': 'N/A',
                'number': 'N/A',
                'date_created': None
            }

        cursor.execute("""
            SELECT 
                DATE(don_date) as donation_date,
                COUNT(*) as donation_count,
                SUM(CASE WHEN don_status = 'Paid' THEN don_amount ELSE 0 END) as daily_amount
            FROM donations 
            WHERE fund_id = %s
            GROUP BY DATE(don_date)
            ORDER BY donation_date DESC
            LIMIT 30
        """, (fundraiser_id,))
        donation_timeline = cursor.fetchall()

        try:
            cursor.execute("""
                SELECT * FROM beneficiaries 
                WHERE fund_id = %s 
                ORDER BY date_added ASC
            """, (fundraiser_id,))
            beneficiaries = cursor.fetchall()
        except mysql.connector.Error as e:
            print(f"Error fetching beneficiaries: {e}")
            beneficiaries = []

        goal_amount = float(fundraiser['fund_goalamount']) if fundraiser['fund_goalamount'] else 0
        total_raised = float(donation_stats['total_raised']) if donation_stats and donation_stats['total_raised'] else 0
        progress_percentage = (total_raised / goal_amount * 100) if goal_amount > 0 else 0

        fundraiser_report_data = _make_json_safe({
            key: value for key, value in fundraiser.items() if key != 'fund_img'
        })
        donation_stats_report_data = _make_json_safe(donation_stats)
        top_donors_report_data = _make_json_safe(top_donors)
        recent_donations_report_data = _make_json_safe(recent_donations)

        cursor.close()
        conn.close()

        return render_template('admin_funddets.html',
            fundraiser=fundraiser,
            donations=donations,
            donation_stats=donation_stats,
            top_donors=top_donors,
            recent_donations=recent_donations,
            fundraiser_report_data=fundraiser_report_data,
            donation_stats_report_data=donation_stats_report_data,
            top_donors_report_data=top_donors_report_data,
            recent_donations_report_data=recent_donations_report_data,
            creator=creator,
            donation_timeline=donation_timeline,
            beneficiaries=beneficiaries,
            total_raised=total_raised,
            progress_percentage=progress_percentage
        )

    except Exception as e:
        print(f"Error fetching fundraiser details: {e}")
        return "Error loading fundraiser details", 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/admin/cash-donations')
def admin_cash_donations():
    if 'email' not in session or session.get('role') != 'Admin':
        return redirect(url_for('goto_signin'))
    
    app.permanent_session_lifetime = timedelta(hours=10)
    page = request.args.get('page', 1, type=int)
    per_page = 15
    offset = (page - 1) * per_page

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        cursor.execute("""
            SELECT 
                COUNT(*) as total_cash_donations,
                COUNT(CASE WHEN don_paymethod = 'Cash' THEN 1 END) as cash_count,
                COUNT(CASE WHEN don_paymethod = 'Cheque' THEN 1 END) as cheque_count,
                COALESCE(SUM(CASE WHEN don_paymethod IN ('Cash', 'Cheque') THEN don_amount ELSE 0 END), 0) as total_amount,
                COALESCE(AVG(CASE WHEN don_paymethod IN ('Cash', 'Cheque') THEN don_amount END), 0) as avg_amount,
                COUNT(CASE WHEN DATE(don_date) = CURDATE() THEN 1 END) as today_count
            FROM donations 
            WHERE don_paymethod IN ('Cash', 'Cheque')
        """)
        stats = cursor.fetchone()
        
        cursor.execute("""
            SELECT d.*, f.fund_title, u.name as recorded_by_name
            FROM donations d
            LEFT JOIN fundraisers f ON d.fund_id = f.fund_id
            LEFT JOIN users u ON d.don_donorid = u.id
            WHERE d.don_paymethod IN ('Cash', 'Cheque')
            ORDER BY d.don_id DESC
            LIMIT %s OFFSET %s
        """, (per_page, offset))
        cash_donations = cursor.fetchall()

        total_count = int(stats.get('total_cash_donations') or 0)
        total_pages = (total_count + per_page - 1) // per_page if per_page > 0 else 1
        pagination = {
            'page': page,
            'per_page': per_page,
            'total': total_count,
            'total_pages': total_pages,
            'has_prev': page > 1,
            'has_next': page < total_pages,
            'prev_num': page - 1 if page > 1 else None,
            'next_num': page + 1 if page < total_pages else None
        }
        
        response = make_response(render_template(
            'admin_cash_donations.html',
            stats=stats,
            cash_donations=cash_donations,
            pagination=pagination
        ))
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response
    except Exception as e:
        print(f"Error fetching cash donations: {e}")
        return "Error loading cash donations", 500
    finally:
        cursor.close()
        conn.close()

@app.route('/admin/cash-donations/entry', methods=['GET', 'POST'])
def admin_cash_entry():
    if 'email' not in session or session.get('role') != 'Admin':
        return redirect(url_for('goto_signin'))
    
    app.permanent_session_lifetime = timedelta(hours=10)
    conn = None
    cursor = None

    if request.method == 'POST':
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            donor_name = request.form.get('donor_name', '').strip()
            contact_number = request.form.get('contact_number', '').strip()
            payment_type = request.form.get('donation_type') or request.form.get('payment_type', 'Cash')
            fund_id = int(request.form.get('fund_id', 0)) if request.form.get('fund_id') else 0
            recorder_user_id = int(session.get('user_id') or 0)
            donation_date = datetime.now()
            notes = request.form.get('notes', '').strip()

            if contact_number and not re.fullmatch(r'\d+', contact_number):
                raise ValueError("Contact number must contain numbers only.")

            if not fund_id:
                cursor.execute("""
                    SELECT fund_id
                    FROM fundraisers
                    WHERE LOWER(COALESCE(fund_status, '')) = 'active'
                    ORDER BY fund_startdate DESC, fund_id DESC
                    LIMIT 1
                """)
                fallback = cursor.fetchone()
                fund_id = int(fallback[0]) if fallback else 0

            if not fund_id:
                raise ValueError("No valid fundraiser available. Please select a fundraiser before recording donation.")

            if not recorder_user_id:
                raise ValueError("Invalid session user. Please sign in again.")

            if payment_type == 'In-Kind':
                estimated_value = (request.form.get('in_kind_estimated_value') or '').replace(',', '').strip()
                if estimated_value and not re.fullmatch(r'\d+', estimated_value):
                    raise ValueError("Estimated value must contain numbers only.")
                amount = float(estimated_value) if estimated_value else 0.0
                in_kind_description = request.form.get('in_kind_description', '').strip()
                in_kind_quantity = request.form.get('in_kind_quantity', '').strip()
                if not re.fullmatch(r'[A-Za-z0-9 ]+', in_kind_description):
                    raise ValueError("In-kind description must contain letters, numbers, and spaces only.")
                if not re.fullmatch(r'\d+', in_kind_quantity):
                    raise ValueError("Quantity must contain numbers only.")
                in_kind_note = f"In-Kind Donation - {in_kind_description} | Quantity: {in_kind_quantity}"
                notes = f"{in_kind_note}\n{notes}".strip() if notes else in_kind_note
            else:
                raw_amount = (request.form.get('amount') or '0').replace(',', '').strip()
                amount = float(raw_amount)
            
            ref_num = generate_reference_number()
            notes_payload = {
                'donor_id': recorder_user_id,
                'donor_name': donor_name or 'Anonymous',
                'receiver': 'Admin Office',
                'paymethod': payment_type,
                'amount': amount,
                'fund_id': fund_id,
                'reference': ref_num,
                'entry_mode': 'in_person_admin',
                'timestamp': datetime.now().isoformat()
            }
            if contact_number:
                notes_payload['contact_number'] = contact_number
            secure_notes = build_secure_donation_notes(notes_payload, notes)
            
            cursor.execute("""
                INSERT INTO donations (
                    fund_id, don_donorid, don_donorname, don_receiver, 
                    don_paymethod, don_amount, don_refnum, don_status, 
                    don_date, don_notes, recorded_by_admin
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                fund_id,
                recorder_user_id,
                donor_name or 'Anonymous',
                'Admin Office',
                payment_type,
                amount,
                ref_num,
                'Pending',
                donation_date,
                secure_notes,
                1
            ))

            donation_id = cursor.lastrowid
            log_audit_event(
                action='CASH_DONATION_RECEIVED',
                entity_type='donation',
                entity_id=ref_num,
                after_data={
                    'don_id': donation_id,
                    'don_refnum': ref_num,
                    'don_status': 'Pending',
                    'don_paymethod': payment_type,
                    'don_amount': amount,
                    'fund_id': fund_id
                },
                metadata={'source': 'admin_cash_entry'},
                conn=conn,
                cursor=cursor
            )
            record_donation_fund_status_update(
                cursor=cursor,
                reference_number=ref_num,
                donation_id=donation_id,
                new_status='Donation Received',
                previous_status=None,
                updated_by=session.get('user_id'),
                audit_id=None,
                note='Admin recorded in-person donation'
            )
            
            conn.commit()

            return redirect(url_for('admin_cash_receipt_by_ref', refnum=ref_num, new='1'))
            
        except Exception as e:
            if conn:
                conn.rollback()
            print(f"Error recording cash donation: {e}")
            try:
                error_conn = get_db_connection()
                error_cursor = error_conn.cursor(dictionary=True)
                error_cursor.execute("""
                    SELECT fund_id, fund_title, fund_status 
                    FROM fundraisers 
                    WHERE LOWER(COALESCE(fund_status, '')) = 'active'
                    ORDER BY fund_title
                """)
                fundraisers = error_cursor.fetchall()
            except Exception:
                fundraisers = []
            finally:
                if 'error_cursor' in locals() and error_cursor:
                    error_cursor.close()
                if 'error_conn' in locals() and error_conn:
                    error_conn.close()
            return render_template(
                'admin_cash_entry.html',
                fundraisers=fundraisers,
                error=f"Error recording donation: {str(e)}"
            ), 400
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        cursor.execute("""
            SELECT fund_id, fund_title, fund_status 
            FROM fundraisers 
            WHERE LOWER(COALESCE(fund_status, '')) = 'active'
            ORDER BY fund_title
        """)
        fundraisers = cursor.fetchall()
        
        return render_template('admin_cash_entry.html', fundraisers=fundraisers)
    except Exception as e:
        print(f"Error loading form: {e}")
        return "Error loading form", 500
    finally:
        cursor.close()
        conn.close()

@app.route('/admin/cash-donations/receipt/<int:donation_id>')
def admin_cash_receipt(donation_id):
    if 'email' not in session or session.get('role') != 'Admin':
        return redirect(url_for('goto_signin'))
    
    app.permanent_session_lifetime = timedelta(hours=10)

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        cursor.execute("""
            SELECT d.*, f.fund_title
            FROM donations d
            LEFT JOIN fundraisers f ON d.fund_id = f.fund_id
            WHERE d.don_id = %s AND d.don_paymethod IN ('Cash', 'Cheque', 'In-Kind')
        """, (donation_id,))
        donation = cursor.fetchone()
        
        if not donation:
            return "Donation not found", 404

        donation['don_notes'] = extract_display_notes(donation.get('don_notes'))
        
        return render_template(
            'admin_cash_receipt.html',
            donation=donation,
            is_new_receipt=request.args.get('new') == '1'
        )
    except Exception as e:
        print(f"Error fetching donation: {e}")
        return "Error loading receipt", 500
    finally:
        cursor.close()
        conn.close()

@app.route('/admin/cash-donations/receipt/ref/<refnum>')
def admin_cash_receipt_by_ref(refnum):
    if 'email' not in session or session.get('role') != 'Admin':
        return redirect(url_for('goto_signin'))

    app.permanent_session_lifetime = timedelta(hours=10)

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT d.*, f.fund_title
            FROM donations d
            LEFT JOIN fundraisers f ON d.fund_id = f.fund_id
            WHERE d.don_refnum = %s AND d.don_paymethod IN ('Cash', 'Cheque', 'In-Kind')
            ORDER BY d.don_id DESC
            LIMIT 1
        """, (refnum,))
        donation = cursor.fetchone()

        if not donation:
            return "Donation not found", 404

        donation['don_notes'] = extract_display_notes(donation.get('don_notes'))

        return render_template(
            'admin_cash_receipt.html',
            donation=donation,
            is_new_receipt=request.args.get('new') == '1'
        )
    except Exception as e:
        print(f"Error fetching donation by ref: {e}")
        return "Error loading receipt", 500
    finally:
        cursor.close()
        conn.close()

@app.route('/api/admin/endorse-cash-donation', methods=['POST'])
def admin_endorse_cash_donation():
    if 'email' not in session or session.get('role') != 'Admin':
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json(silent=True) or {}
    donation_id = data.get('donation_id')
    donation_refnum = (data.get('don_refnum') or '').strip()
    try:
        donation_id = int(donation_id)
    except (TypeError, ValueError):
        donation_id = None

    if donation_id is None and not donation_refnum:
        return jsonify({'error': 'Invalid donation reference'}), 400

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        if donation_refnum:
            cursor.execute("""
                SELECT don_id, don_refnum, don_status, don_paymethod, don_notes, don_amount, fund_id, don_donorid
                FROM donations
                WHERE don_refnum = %s
                ORDER BY don_id DESC
                LIMIT 1
            """, (donation_refnum,))
        else:
            cursor.execute("""
                SELECT don_id, don_refnum, don_status, don_paymethod, don_notes, don_amount, fund_id, don_donorid
                FROM donations
                WHERE don_id = %s
                LIMIT 1
            """, (donation_id,))
        donation = cursor.fetchone()

        if not donation:
            return jsonify({'error': 'Donation not found'}), 404

        if donation_id is not None and donation['don_id'] != donation_id:
            return jsonify({'error': 'Donation changed. Please refresh and try again.'}), 409

        if donation['don_paymethod'] not in ('Cash', 'Cheque', 'In-Kind'):
            return jsonify({'error': 'Only in-person donations can be endorsed from this workflow'}), 400

        current_status = (donation.get('don_status') or '').strip().lower()
        if current_status not in ('pending', 'paid'):
            return jsonify({'error': 'Only Pending or Paid in-person donations can be endorsed to Treasurer'}), 400

        actor_display = session.get('username') or session.get('email') or 'Admin'
        workflow_note = (
            f"[WORKFLOW] Admin endorsed to Treasurer by {actor_display} "
            f"on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        updated_notes = append_workflow_note(donation.get('don_notes'), workflow_note)

        cursor.execute("""
            UPDATE donations
            SET don_status = %s, don_notes = %s
            WHERE don_id = %s AND LOWER(TRIM(don_status)) IN ('pending', 'paid')
        """, ('Endorsed', updated_notes, donation['don_id']))

        if cursor.rowcount <= 0:
            conn.rollback()
            return jsonify({'error': 'Donation status changed. Please refresh and try again.'}), 409

        log_audit_event(
            action='CASH_DONATION_ENDORSED',
            entity_type='donation',
            entity_id=donation['don_id'],
            before_data={
                'don_id': donation['don_id'],
                'don_refnum': donation['don_refnum'],
                'don_status': donation['don_status'],
                'don_amount': float(donation['don_amount']) if donation['don_amount'] is not None else None,
                'fund_id': donation['fund_id'],
                'don_donorid': donation['don_donorid']
            },
            after_data={
                'don_id': donation['don_id'],
                'don_status': 'Endorsed',
                'workflow_note': workflow_note
            },
            metadata={'source': 'admin_endorse_cash_donation'},
            conn=conn,
            cursor=cursor
        )

        conn.commit()
        return jsonify({
            'success': True,
            'message': f"Donation {donation['don_refnum']} endorsed to Treasurer."
        })
    except Exception as e:
        conn.rollback()
        print(f"Error endorsing cash donation: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/admin/settings')
def admin_settings():
    if 'email' not in session or session.get('role') != 'Admin':
        return redirect(url_for('goto_signin'))
    
    app.permanent_session_lifetime = timedelta(hours=10)

    settings = get_all_settings()
    
    settings_data = {
        'backup_date': 'Jan 15, 2025',
        'active_sessions': 24,
        'storage_used': 67,
        'settings': settings
    }

    return render_template('admin_settings.html', **settings_data)

@app.route('/admin/audit-trail')
def admin_audit_trail():
    if 'email' not in session or session.get('role') != 'Admin':
        return redirect(url_for('goto_signin'))

    app.permanent_session_lifetime = timedelta(hours=10)
    return render_template('admin_audit_trail.html')

@app.route('/api/settings', methods=['GET'])
def get_settings_api():
    if 'email' not in session or session.get('role') != 'Admin':
        return jsonify({'error': 'Unauthorized'}), 401
    
    settings = get_all_settings()
    return jsonify({'success': True, 'settings': settings})

@app.route('/api/settings', methods=['POST'])
def update_settings_api():
    if 'email' not in session or session.get('role') != 'Admin':
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        data = request.get_json()
        setting_key = data.get('key')
        setting_value = data.get('value')
        setting_type = data.get('type', 'string')
        
        if not setting_key or setting_value is None:
            return jsonify({'error': 'Missing key or value'}), 400
        
        if setting_type == 'number':
            try:
                setting_value = int(setting_value) if '.' not in str(setting_value) else float(setting_value)
            except ValueError:
                return jsonify({'error': 'Invalid number format'}), 400
        elif setting_type == 'boolean':
            setting_value = bool(setting_value)
        
        success = update_setting(setting_key, setting_value, setting_type)
        
        if success:
            log_audit_event(
                action='SETTING_UPDATED',
                entity_type='platform_setting',
                entity_id=setting_key,
                after_data={'key': setting_key, 'value': setting_value, 'type': setting_type}
            )
            return jsonify({'success': True, 'message': 'Setting updated successfully'})
        else:
            return jsonify({'error': 'Failed to update setting'}), 500
            
    except Exception as e:
        print(f"Error updating setting: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/settings/bulk', methods=['POST'])
def update_settings_bulk():
    if 'email' not in session or session.get('role') != 'Admin':
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        data = request.get_json()
        settings = data.get('settings', [])
        
        if not settings:
            return jsonify({'error': 'No settings provided'}), 400
        
        updated_count = 0
        for setting in settings:
            key = setting.get('key')
            value = setting.get('value')
            setting_type = setting.get('type', 'string')
            
            if key and value is not None:
                if update_setting(key, value, setting_type):
                    log_audit_event(
                        action='SETTING_UPDATED',
                        entity_type='platform_setting',
                        entity_id=key,
                        after_data={'key': key, 'value': value, 'type': setting_type}
                    )
                    updated_count += 1
        
        return jsonify({
            'success': True, 
            'message': f'Updated {updated_count} settings successfully',
            'updated_count': updated_count
        })
        
    except Exception as e:
        print(f"Error updating settings: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/audit-trail', methods=['GET'])
def get_audit_trail():
    if 'email' not in session or session.get('role') not in ['Admin', 'Treasurer']:
        return jsonify({'error': 'Unauthorized'}), 401

    try:
        page = request.args.get('page', 1, type=int)
        page = max(1, page)
        limit = request.args.get('limit', 25, type=int)
        limit = max(1, min(limit, 500))
        offset = (page - 1) * limit
        action = request.args.get('action')
        entity_type = request.args.get('entity_type')
        status = request.args.get('status')
        actor_user_id = request.args.get('actor_user_id', type=int)

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        query = """
            SELECT
                audit_id, event_time, actor_user_id, actor_email, actor_role,
                action, entity_type, entity_id, request_method, request_path,
                ip_address, status, reason, before_data, after_data, metadata,
                previous_hash, entry_hash
            FROM audit_trail_logs
            WHERE 1=1
        """
        count_query = "SELECT COUNT(*) AS total FROM audit_trail_logs WHERE 1=1"
        params = []

        if action:
            query += " AND action = %s"
            count_query += " AND action = %s"
            params.append(action)
        if entity_type:
            query += " AND entity_type = %s"
            count_query += " AND entity_type = %s"
            params.append(entity_type)
        if status:
            query += " AND status = %s"
            count_query += " AND status = %s"
            params.append(status)
        if actor_user_id:
            query += " AND actor_user_id = %s"
            count_query += " AND actor_user_id = %s"
            params.append(actor_user_id)

        count_params = list(params)

        cursor.execute(count_query, count_params)
        total_row = cursor.fetchone() or {}
        total_count = total_row.get('total', 0) if isinstance(total_row, dict) else total_row[0]

        query += " ORDER BY audit_id DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])

        cursor.execute(query, params)
        logs = cursor.fetchall()
        cursor.close()
        conn.close()

        total_pages = max(1, math.ceil(total_count / limit)) if limit else 1

        return jsonify({
            'success': True,
            'count': len(logs),
            'logs': logs,
            'page': page,
            'per_page': limit,
            'total': total_count,
            'total_pages': total_pages,
            'has_prev': page > 1,
            'has_next': page < total_pages
        })
    except Exception as e:
        print(f"Error fetching audit trail: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/users/<int:user_id>/suspend', methods=['POST'])
def suspend_user(user_id):
    if 'email' not in session or session.get('role') != 'Admin':
        return jsonify({'error': 'Unauthorized'}), 401

    conn = None
    cursor = None

    try:
        data = request.get_json(silent=True) or {}
        reason = (data.get('reason') or '').strip()
        remarks = (data.get('remarks') or '').strip()

        if not reason:
            return jsonify({'error': 'Reason is required.'}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, name, email, role, id_verification_status
            FROM users
            WHERE id = %s
        """, (user_id,))
        user = cursor.fetchone()

        if not user:
            return jsonify({'error': 'User not found'}), 404

        if user[3] == 'Admin':
            return jsonify({'error': 'Cannot suspend admin users'}), 403

        current_role = (user[3] or '').strip()
        current_verification_status = (user[4] or 'not_verified').strip()
        if current_role == 'Suspended' or current_verification_status.lower() == 'suspended':
            return jsonify({'error': 'User is already suspended.'}), 400

        cursor.execute("""
            UPDATE users 
            SET role = 'Suspended', 
                id_verification_status = 'suspended',
                verification_notes = %s,
                verification_date = NOW(),
                verification_reviewed_by = %s,
                date_modified = NOW() 
            WHERE id = %s
        """, (
            remarks or reason,
            session.get('user_id'),
            user_id
        ))

        action_log_id = record_admin_user_action(
            user_id=user[0],
            user_email=user[2],
            action_type='suspend',
            previous_role=current_role,
            new_role='Suspended',
            previous_verification_status=current_verification_status,
            new_verification_status='suspended',
            reason=reason,
            remarks=remarks,
            conn=conn,
            cursor=cursor,
            acted_by=session.get('user_id')
        )
        if not action_log_id:
            raise RuntimeError('Failed to save suspension reason and remarks.')

        log_audit_event(
            action='USER_SUSPENDED',
            entity_type='user',
            entity_id=user_id,
            reason=reason,
            before_data={
                'id': user[0],
                'name': user[1],
                'email': user[2],
                'role': current_role,
                'id_verification_status': current_verification_status
            },
            after_data={
                'id': user[0],
                'name': user[1],
                'email': user[2],
                'role': 'Suspended',
                'id_verification_status': 'suspended'
            },
            metadata={
                'remarks': remarks,
                'notified_email': user[2]
            },
            conn=conn,
            cursor=cursor
        )

        conn.commit()

        email_sent, email_error = send_user_action_email(
            user_email=user[2],
            user_name=user[1],
            action_taken='suspended',
            reason=reason,
            remarks=remarks
        )

        message = f'User {user[1]} has been suspended successfully.'
        if not email_sent:
            message += ' Status was updated, but the email notification could not be sent.'

        return jsonify({
            'success': True,
            'message': message,
            'email_sent': email_sent,
            'email_error': email_error
        })

    except Exception as e:
        if conn:
            conn.rollback()
        print(f"Error suspending user: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/users/<int:user_id>/activate', methods=['POST'])
def activate_user(user_id):
    if 'email' not in session or session.get('role') != 'Admin':
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT id, name, role FROM users WHERE id = %s", (user_id,))
        user = cursor.fetchone()
        
        if not user:
            cursor.close()
            conn.close()
            return jsonify({'error': 'User not found'}), 404
        
        cursor.execute("""
            UPDATE users 
            SET role = 'User', 
                date_modified = NOW() 
            WHERE id = %s
        """, (user_id,))
        log_audit_event(
            action='USER_ACTIVATED',
            entity_type='user',
            entity_id=user_id,
            before_data={'id': user[0], 'name': user[1], 'role': user[2]},
            after_data={'id': user[0], 'name': user[1], 'role': 'User'},
            conn=conn,
            cursor=cursor
        )
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': f'User {user[1]} has been activated successfully'
        })
        
    except Exception as e:
        print(f"Error activating user: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/users/<int:user_id>/update', methods=['POST'])
def update_user(user_id):
    if 'email' not in session or session.get('role') != 'Admin':
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        data = request.get_json()
        name = data.get('name')
        email = data.get('email')
        number = data.get('number')
        role = data.get('role')
        
        if not all([name, email, number, role]):
            return jsonify({'error': 'All fields are required'}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT id, name, email, number, role FROM users WHERE id = %s", (user_id,))
        current_user = cursor.fetchone()
        if not current_user:
            cursor.close()
            conn.close()
            return jsonify({'error': 'User not found'}), 404
        
        cursor.execute("SELECT id FROM users WHERE email = %s AND id != %s", (email, user_id))
        if cursor.fetchone():
            cursor.close()
            conn.close()
            return jsonify({'error': 'Email already exists'}), 400
        
        cursor.execute("""
            UPDATE users 
            SET name = %s, email = %s, number = %s, role = %s, date_modified = NOW()
            WHERE id = %s
        """, (name, email, number, role, user_id))
        log_audit_event(
            action='USER_UPDATED',
            entity_type='user',
            entity_id=user_id,
            before_data={
                'id': current_user[0],
                'name': current_user[1],
                'email': current_user[2],
                'number': current_user[3],
                'role': current_user[4]
            },
            after_data={
                'id': user_id,
                'name': name,
                'email': email,
                'number': number,
                'role': role
            },
            conn=conn,
            cursor=cursor
        )
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': 'User details updated successfully'
        })
        
    except Exception as e:
        print(f"Error updating user: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/users/<int:user_id>/delete', methods=['DELETE'])
def delete_user(user_id):
    if 'email' not in session or session.get('role') != 'Admin':
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT id, name, role FROM users WHERE id = %s", (user_id,))
        user = cursor.fetchone()
        
        if not user:
            cursor.close()
            conn.close()
            return jsonify({'error': 'User not found'}), 404
        
        if user[2] == 'Admin':
            cursor.close()
            conn.close()
            return jsonify({'error': 'Cannot delete admin users'}), 403
        
        cursor.execute("SELECT COUNT(*) FROM donations WHERE don_donorid = %s", (user_id,))
        donation_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM fundraisers WHERE fund_creatorid = %s", (user_id,))
        fundraiser_count = cursor.fetchone()[0]
        
        if donation_count > 0 or fundraiser_count > 0:
            cursor.close()
            conn.close()
            return jsonify({
                'error': 'Cannot delete user with existing donations or fundraisers',
                'donation_count': donation_count,
                'fundraiser_count': fundraiser_count
            }), 400
        
        cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
        log_audit_event(
            action='USER_DELETED',
            entity_type='user',
            entity_id=user_id,
            before_data={'id': user[0], 'name': user[1], 'role': user[2]},
            after_data={'deleted': True},
            conn=conn,
            cursor=cursor
        )
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': f'User {user[1]} has been deleted successfully'
        })
        
    except Exception as e:
        print(f"Error deleting user: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/users/<int:user_id>/activity', methods=['GET'])
def get_user_activity(user_id):
    if 'email' not in session or session.get('role') != 'Admin':
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("""
            SELECT f.fund_id, f.fund_title, f.fund_status, f.fund_goalamount, f.fund_startdate,
                COALESCE(SUM(CASE WHEN d.don_status = 'Paid' THEN d.don_amount ELSE 0 END), 0) as total_raised
            FROM fundraisers f
            LEFT JOIN donations d ON f.fund_id = d.fund_id AND d.don_status = 'Paid'
            WHERE f.fund_creatorid = %s
            GROUP BY f.fund_id
            ORDER BY f.fund_startdate DESC
            LIMIT 10
        """, (user_id,))
        created_fundraisers = cursor.fetchall()
        
        cursor.execute("""
            SELECT d.don_amount, d.don_status, d.don_date, d.don_refnum, d.don_paymethod,
                f.fund_title, f.fund_id
            FROM donations d
            JOIN fundraisers f ON d.fund_id = f.fund_id
            WHERE d.don_donorid = %s
            ORDER BY d.don_date DESC
            LIMIT 15
        """, (user_id,))
        donations = cursor.fetchall()
        
        cursor.execute("""
            SELECT 
                COUNT(*) as total_donations,
                COUNT(CASE WHEN don_status = 'Paid' THEN 1 END) as paid_donations,
                COUNT(CASE WHEN don_status = 'Pending' THEN 1 END) as pending_donations,
                COALESCE(SUM(CASE WHEN don_status = 'Paid' THEN don_amount ELSE 0 END), 0) as total_donated
            FROM donations 
            WHERE don_donorid = %s
        """, (user_id,))
        donation_stats = cursor.fetchone()
        
        cursor.execute("""
            SELECT 
                COUNT(*) as total_fundraisers,
                COUNT(CASE WHEN f.fund_status = 'Active' THEN 1 END) as active_fundraisers,
                COUNT(CASE WHEN f.fund_status = 'Pending' THEN 1 END) as pending_fundraisers,
                COALESCE(SUM(f.fund_goalamount), 0) as total_goal_amount,
                COALESCE(SUM(
                    (SELECT COALESCE(SUM(d2.don_amount), 0) 
                    FROM donations d2 
                    WHERE d2.fund_id = f.fund_id AND d2.don_status = 'Paid')
                ), 0) as total_raised
            FROM fundraisers f
            WHERE f.fund_creatorid = %s
        """, (user_id,))
        fundraiser_stats = cursor.fetchone()
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'created_fundraisers': created_fundraisers,
            'donations': donations,
            'donation_stats': donation_stats,
            'fundraiser_stats': fundraiser_stats
        })
        
    except Exception as e:
        print(f"Error fetching user activity: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/users/<int:user_id>/id-document', methods=['GET'])
def get_user_id_document(user_id):
    if 'email' not in session or session.get('role') != 'Admin':
        return jsonify({'error': 'Unauthorized'}), 401

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id_document_image, id_document_filename
            FROM users
            WHERE id = %s
        """, (user_id,))
        result = cursor.fetchone()
        cursor.close()
        conn.close()

        if not result or not result[0]:
            return jsonify({'error': 'ID document not found'}), 404

        image_data, filename = result
        content_type = 'image/jpeg'
        if filename:
            ext = filename.lower().split('.')[-1]
            if ext == 'png':
                content_type = 'image/png'
            elif ext == 'gif':
                content_type = 'image/gif'
            elif ext == 'webp':
                content_type = 'image/webp'

        return Response(image_data, mimetype=content_type)
    except Exception as e:
        print(f"Error fetching user ID document: {e}")
        return jsonify({'error': 'Error fetching ID document'}), 500


@app.route('/api/users/<int:user_id>/approve', methods=['POST'])
def approve_user(user_id):
    if 'email' not in session or session.get('role') != 'Admin':
        return jsonify({'error': 'Unauthorized'}), 401

    conn = None
    cursor = None

    try:
        data = request.get_json(silent=True) or {}
        reason = (data.get('reason') or '').strip()
        remarks = (data.get('remarks') or '').strip()

        if not reason:
            return jsonify({'error': 'Reason is required.'}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, name, email, role, id_verification_status, id_document_image
            FROM users
            WHERE id = %s
        """, (user_id,))
        user = cursor.fetchone()

        if not user:
            return jsonify({'error': 'User not found'}), 404

        if user[3] == 'Admin':
            return jsonify({'error': 'Cannot approve admin users'}), 403

        current_role = (user[3] or '').strip()
        current_status = (user[4] or 'not_verified').strip().lower()
        if current_status != 'pending':
            return jsonify({'error': f"Only pending users can be approved. Current status: {current_status}"}), 400

        if not user[5]:
            return jsonify({'error': 'User has no uploaded ID document'}), 400

        cursor.execute("""
            UPDATE users
            SET id_verification_status = 'verified',
                verification_notes = %s,
                verification_date = NOW(),
                verification_reviewed_by = %s
            WHERE id = %s AND id_verification_status = 'pending'
        """, (
            remarks or reason,
            session.get('user_id'),
            user_id
        ))

        if cursor.rowcount <= 0:
            conn.rollback()
            return jsonify({'error': 'User verification status changed. Please refresh and try again.'}), 409

        action_log_id = record_admin_user_action(
            user_id=user[0],
            user_email=user[2],
            action_type='approve',
            previous_role=current_role,
            new_role=current_role,
            previous_verification_status=current_status,
            new_verification_status='verified',
            reason=reason,
            remarks=remarks,
            conn=conn,
            cursor=cursor,
            acted_by=session.get('user_id')
        )
        if not action_log_id:
            raise RuntimeError('Failed to save approval reason and remarks.')

        log_audit_event(
            action='USER_VERIFIED',
            entity_type='user',
            entity_id=user_id,
            reason=reason,
            before_data={
                'id': user[0],
                'name': user[1],
                'email': user[2],
                'role': current_role,
                'id_verification_status': current_status
            },
            after_data={
                'id': user[0],
                'name': user[1],
                'email': user[2],
                'role': current_role,
                'id_verification_status': 'verified',
                'verification_reviewed_by': session.get('user_id')
            },
            metadata={
                'remarks': remarks,
                'notified_email': user[2]
            },
            conn=conn,
            cursor=cursor
        )

        conn.commit()

        email_sent, email_error = send_user_action_email(
            user_email=user[2],
            user_name=user[1],
            action_taken='approved',
            reason=reason,
            remarks=remarks
        )

        message = f'User {user[1]} has been approved successfully.'
        if not email_sent:
            message += ' Status was updated, but the email notification could not be sent.'

        return jsonify({
            'success': True,
            'message': message,
            'email_sent': email_sent,
            'email_error': email_error
        })
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"Error approving user: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/pending-fundraisers', methods=['GET'])
def get_pending_fundraisers():
    if 'email' not in session or session.get('role') != 'Admin':
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        
        sql = """
        SELECT fund_id, fund_title, fund_desc, fund_goalamount, fund_link, 
            fund_startdate, fund_beneficiary
        FROM fundraisers 
        WHERE fund_status = 'Pending' 
        AND fund_startdate >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
        ORDER BY fund_startdate DESC
        """
        
        cursor.execute(sql)
        pending_fundraisers = cursor.fetchall()
        
        cursor.close()
        connection.close()
        
        return jsonify({
            'success': True,
            'fundraisers': pending_fundraisers
        })
        
    except Exception as e:
        print(f"Error fetching pending fundraisers: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/approve-scraped-fundraisers', methods=['POST'])
def approve_scraped_fundraisers():
    if 'email' not in session or session.get('role') != 'Admin':
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.get_json()
    fundraiser_ids = data.get('fundraiser_ids', [])
    
    if not fundraiser_ids:
        return jsonify({'error': 'No fundraisers selected'}), 400
    
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        
        placeholders = ','.join(['%s'] * len(fundraiser_ids))
        sql = f"""
        UPDATE fundraisers 
        SET fund_status = 'Active' 
        WHERE fund_id IN ({placeholders}) AND fund_status = 'Pending'
        """
        
        cursor.execute(sql, fundraiser_ids)
        approved_count = cursor.rowcount
        
        connection.commit()
        cursor.close()
        connection.close()
        
        return jsonify({
            'success': True,
            'approved_count': approved_count
        })
        
    except Exception as e:
        print(f"Error approving fundraisers: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ------------------------------------------------------------------------
# -------------------------------- SCRAPE --------------------------------
# ------------------------------------------------------------------------

@app.route('/crowdsource-from-facebook', methods=['POST'])
def scrape_and_filter():
    try:
        # SCRAPE FUNCTION
        client = ApifyClient(APIFY_TOKEN)

        actor_id = "apify/facebook-groups-scraper"
        actor_input = {
            "startUrls": [
                {"url": "https://www.facebook.com/groups/1234268423690679"},
                {"url": "https://www.facebook.com/groups/1356763145487505"},
                {"url": "https://www.facebook.com/groups/571766703572232"},
                {"url": "https://www.facebook.com/groups/3408312342792580"}
            ],
            "resultsLimit": 10,
            "viewOption": "CHRONOLOGICAL",
            "start_date": "2025-08-15",
            "simplified": True,
            "query": ""
        }

        print("Starting Facebook scraping...")
        run = client.actor(actor_id).call(run_input=actor_input)

        sample_texts = []
        for item in client.dataset(run["defaultDatasetId"]).iterate_items():
            if "text" in item and item["text"]:
                caption = item["text"]
                link = (item.get("facebookUrl") or 
                    item.get("postUrl") or 
                    item.get("url") or 
                    "No link available")
                sample_texts.append((caption, link))

        print(f"Scraped {len(sample_texts)} posts.")

        # ENHANCED ML FILTER FUNCTION
        try:
            models = []
            model_names = []
            
            try:
                model1 = joblib.load("final_disaster_model.pkl")
                models.append(model1)
                model_names.append("final_disaster_model")
                print("✅ Loaded final_disaster_model.pkl")
            except FileNotFoundError:
                print("⚠️ final_disaster_model.pkl not found")
            
            try:
                model2 = joblib.load("improved_disaster_model.pkl")
                models.append(model2)
                model_names.append("improved_disaster_model")
                print("✅ Loaded improved_disaster_model.pkl")
            except FileNotFoundError:
                print("⚠️ improved_disaster_model.pkl not found")
            
            if not models:
                raise FileNotFoundError("No ML models found")
            
            print(f"Loaded {len(models)} model(s) for ensemble prediction")
            
        except Exception as e:
            print(f"❌ Error loading ML models: {e}")
            return jsonify({
                'success': False,
                'error': f'Failed to load ML models: {str(e)}'
            }), 500

        captions = [caption for caption, _ in sample_texts]
        if not captions:
            return jsonify({
                'success': True,
                'count': 0,
                'fundraisers': [],
                'message': 'No posts found to analyze'
            })

        all_predictions = []
        all_probabilities = []
        
        for model in models:
            try:
                y_pred = model.predict(captions)
                y_proba = model.predict_proba(captions)
                all_predictions.append(y_pred)
                all_probabilities.append(y_proba)
            except Exception as e:
                print(f"⚠️ Error with model prediction: {e}")
                continue
        
        if not all_predictions:
            return jsonify({
                'success': False,
                'error': 'All models failed to make predictions'
            }), 500
        
        predictions_array = np.array(all_predictions)
        y_preds = []
        for i in range(len(captions)):
            votes = predictions_array[:, i]
            disaster_votes = np.sum(votes == "disaster")
            y_preds.append("disaster" if disaster_votes > len(votes) / 2 else "not_disaster")
        
        probas_array = np.array(all_probabilities)
        avg_probas = np.mean(probas_array, axis=0)
        
        if hasattr(models[0], 'classes_'):
            CATEGORIES = models[0].classes_.tolist()
        else:
            CATEGORIES = ["disaster", "not_disaster"]
        
        print(f"Model categories: {CATEGORIES}")
        print(f"Ensemble predictions: {y_preds[:5]}...")  # first 5
        print(f"Average probabilities shape: {avg_probas.shape}")

        def generate_funddata(caption: str) -> dict:
            load_dotenv()
            api_key = os.getenv("OPENAI_KEY")
            print("API Key loaded:", bool(api_key))

            prompt = f"""
            You are helping prepare fundraiser entries from Facebook posts.

            Post: {caption}

            Tasks:
            - Suggest a short fundraiser title (max 80 chars).
            - Expand into a clear fundraiser description (3-5 paragraphs that consists of 200-500 words) that explains: who it's for, what happened, and why help is needed.
            - If the post mentions money, extract a goal amount in Philippine Pesos (PHP), otherwise suggest a reasonable amount.
            - Choose the most appropriate disaster category from: "Fire", "Flood", "Earthquake", "Typhoon", "Other Disaster" based on the content of the post.
            - Ensure that all JSON values (title, description, category) are written ONLY in English, regardless of the original post's language.

            Return ONLY valid JSON with keys:
            title, description, goal, category
            """

            try:
                if api_key:
                    openai_client = OpenAI(api_key=api_key)
                    response = openai_client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.7
                    )
                    raw_output = response.choices[0].message.content.strip()
                else:
                   pass

                try:
                    data = json.loads(raw_output)
                except json.JSONDecodeError:
                    try:
                        json_str = raw_output[raw_output.find("{"):raw_output.rfind("}")+1]
                        data = json.loads(json_str)
                    except Exception:
                        raise ValueError(f"Model did not return valid JSON: {raw_output}")

                return data
            except Exception as e:
                print(f"Error in generate_funddata: {e}")
                return {
                    "title": f"Emergency Fundraiser - {caption[:50]}...",
                    "description": f"This is a fundraiser based on the following post: {caption}. Please review and edit the details as needed.",
                    "goal": 50000.00,
                    "category": "Other Disaster"
                }

        # OpenAI Secondary Filter Function
        def verify_disaster_with_openai(caption: str) -> dict:
            load_dotenv()
            api_key = os.getenv("OPENAI_KEY")
            
            if not api_key:
                print("⚠️ OpenAI API key not found, skipping OpenAI verification")
                return {"is_disaster": True, "confidence": 0.5, "reason": "API key missing"}
            
            verification_prompt = f"""
            Analyze the following Facebook post and determine if it is related to a REAL disaster or emergency situation that requires fundraising.

            Post: {caption}

            Evaluate:
            1. Is this about a genuine disaster/emergency (fire, flood, earthquake, typhoon, medical emergency, etc.)?
            2. Does it clearly indicate a need for financial assistance?
            3. Is it NOT about: general sales, business promotions, non-emergency requests, scams, or unrelated content?

            Return ONLY valid JSON with these keys:
            {{
                "is_disaster": true/false,
                "confidence": 0.0-1.0,
                "disaster_type": "Fire"|"Flood"|"Earthquake"|"Typhoon"|"Medical Emergency"|"Other Disaster"|"Not Disaster",
                "reason": "brief explanation of your decision"
            }}

            Be strict - only return is_disaster=true if it's clearly a legitimate disaster-related fundraising request.
            """
            
            try:
                openai_client = OpenAI(api_key=api_key)
                response = openai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": verification_prompt}],
                    temperature=0.3  # Lower temperature for more consistent verification
                )
                raw_output = response.choices[0].message.content.strip()
                
                # Parse JSON response
                try:
                    data = json.loads(raw_output)
                except json.JSONDecodeError:
                    # Try to extract JSON from markdown code blocks
                    import re
                    json_match = re.search(r'\{[^{}]*\}', raw_output, re.DOTALL)
                    if json_match:
                        data = json.loads(json_match.group())
                    else:
                        raise ValueError(f"Could not parse JSON: {raw_output}")
                
                return data
            except Exception as e:
                print(f"⚠️ Error in OpenAI verification: {e}")
                return {"is_disaster": False, "confidence": 0.0, "reason": f"Verification error: {str(e)}"}

        scraped_fundraisers = []
        ml_confidence_threshold = 0.75  # Slightly lower for ML, OpenAI will be stricter
        openai_confidence_threshold = 0.7  # OpenAI verification threshold
        
        print(f"\n🔍 Starting two-stage filtering process...")
        print(f"ML Confidence Threshold: {ml_confidence_threshold}")
        print(f"OpenAI Confidence Threshold: {openai_confidence_threshold}\n")
        
        ml_passed = 0
        openai_passed = 0
        
        for (caption, link), pred, proba in zip(sample_texts, y_preds, avg_probas):
            # Get disaster class probability
            disaster_idx = CATEGORIES.index("disaster") if "disaster" in CATEGORIES else 0
            max_confidence = float(proba[disaster_idx])
            
            # Stage 1: ML Filter
            if pred == "disaster" and max_confidence >= ml_confidence_threshold:
                ml_passed += 1
                print(f"\n✅ ML Filter Passed")
                print(f"Caption: {caption[:100]}...")
                print(f"ML Confidence: {max_confidence:.3f}")
                
                # Stage 2: OpenAI Verification Filter
                print(f"🔍 Verifying with OpenAI...")
                openai_verification = verify_disaster_with_openai(caption)
                
                is_disaster = openai_verification.get("is_disaster", False)
                openai_confidence = openai_verification.get("confidence", 0.0)
                disaster_type = openai_verification.get("disaster_type", "Not Disaster")
                reason = openai_verification.get("reason", "No reason provided")
                
                print(f"OpenAI Result: is_disaster={is_disaster}, confidence={openai_confidence:.3f}")
                print(f"Disaster Type: {disaster_type}")
                print(f"Reason: {reason}")
                
                # Both filters must pass
                if is_disaster and openai_confidence >= openai_confidence_threshold:
                    openai_passed += 1
                    print(f"✅ OpenAI Filter Passed - Processing fundraiser...")
                    
                    try:
                        enriched = generate_funddata(caption)
                        print(f"Enriched Data: {enriched}")

                        # Use OpenAI disaster type if available, otherwise use enriched category
                        final_category = disaster_type if disaster_type != "Not Disaster" else enriched.get("category", "Other Disaster")
                        
                        fundraiser_data = {
                            "original_caption": caption,
                            "facebook_link": link,
                            "title": enriched["title"],
                            "description": enriched["description"],
                            "goal_amount": float(enriched["goal"]),
                            "category": final_category,
                            "ml_prediction": pred,
                            "ml_confidence": max_confidence,
                            "openai_verified": True,
                            "openai_confidence": openai_confidence,
                            "openai_disaster_type": disaster_type,
                            "verification_reason": reason,
                            "disaster_type": "Emergency Relief"
                        }
                        scraped_fundraisers.append(fundraiser_data)
                        print(f"✅ Fundraiser added to list")
                    except Exception as e:
                        print(f"❌ Error processing caption: {e}")
                        traceback.print_exc()
                        continue
                else:
                    print(f"❌ OpenAI Filter Failed - Rejected")
                    print(f"   Reason: {reason}")
            elif pred == "disaster" and max_confidence < ml_confidence_threshold:
                print(f"⚠️ ML Low confidence: {max_confidence:.3f} - {caption[:50]}...")
            else:
                print(f"❌ ML Filter Failed: {pred} - {caption[:50]}...")
        
        print(f"\n📊 Filtering Summary:")
        print(f"   Total Posts: {len(sample_texts)}")
        print(f"   ML Filter Passed: {ml_passed}")
        print(f"   OpenAI Filter Passed: {openai_passed}")
        print(f"   Final Fundraisers: {len(scraped_fundraisers)}")

        print(f"Found {len(scraped_fundraisers)} high-confidence disaster-related fundraisers.")
        
        inserted_count = 0
        if scraped_fundraisers:
            try:
                connection = get_db_connection()
                cursor = connection.cursor()
                
                for fundraiser in scraped_fundraisers:
                    sql = """
                    INSERT INTO fundraisers
                    (fund_title, fund_desc, fund_category, fund_goalamount, 
                    fund_link, fund_status, fund_startdate, fund_creatorid, fund_beneficiary)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """
                    
                    values = (
                        fundraiser["title"],
                        fundraiser["description"],
                        fundraiser["category"],
                        fundraiser["goal_amount"],
                        fundraiser["facebook_link"],
                        "Pending",
                        datetime.now(),
                        202504,  # Bot ID
                        "Emergency Relief"  # Default beneficiary
                    )
                    cursor.execute(sql, values)
                    inserted_count += 1
                
                connection.commit()
                cursor.close()
                connection.close()
                
                print(f"✅ Successfully inserted {inserted_count} fundraisers with Pending status")
                
            except Exception as e:
                print(f"❌ Error inserting fundraisers: {e}")
                return jsonify({
                    'success': False,
                    'error': f'Failed to insert fundraisers: {str(e)}'
                }), 500
        
        return jsonify({
            'success': True,
            'count': len(scraped_fundraisers),
            'inserted_count': inserted_count,
            'fundraisers': scraped_fundraisers,
            'total_scraped': len(sample_texts),
            'ml_confidence_threshold': ml_confidence_threshold,
            'openai_confidence_threshold': openai_confidence_threshold,
            'ml_passed': ml_passed,
            'openai_passed': openai_passed
        })

    except Exception as e:
        print(f"Error during scraping: {e}")
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# -----------------------------------------------------------------------
# ------------------------------ TREASURER ------------------------------
# -----------------------------------------------------------------------

@app.route('/treasurer/dashboard', methods=['GET', 'POST'])
def treasurer():
    if 'email' not in session or session.get('role') != 'Treasurer':
        return redirect(url_for('goto_signin'))
    
    app.permanent_session_lifetime = timedelta(hours=10)

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT 
            COUNT(*) as total_donations,
            COALESCE(SUM(CASE WHEN don_status = 'Paid' THEN don_amount ELSE 0 END), 0) as total_revenue,
            COALESCE(SUM(CASE WHEN don_status = 'Pending' THEN don_amount ELSE 0 END), 0) as pending_amount,
            COALESCE(SUM(CASE WHEN don_status = 'Failed' THEN don_amount ELSE 0 END), 0) as failed_amount,
            COUNT(DISTINCT don_donorid) as unique_donors,
            COUNT(DISTINCT fund_id) as active_campaigns
        FROM donations
    """)
    financial_stats = cursor.fetchone()

    cursor.execute("""
        SELECT d.*, f.fund_title, u.name as donor_name
        FROM donations d
        LEFT JOIN fundraisers f ON d.fund_id = f.fund_id
        LEFT JOIN users u ON d.don_donorid = u.id
        ORDER BY d.don_date DESC
        LIMIT 10
    """)
    recent_transactions = cursor.fetchall()

    cursor.execute("""
        SELECT 
            DATE_FORMAT(don_date, '%Y-%m') as month,
            SUM(CASE WHEN don_status = 'Paid' THEN don_amount ELSE 0 END) as revenue,
            COUNT(CASE WHEN don_status = 'Paid' THEN 1 END) as transaction_count
        FROM donations
        WHERE don_date >= DATE_SUB(NOW(), INTERVAL 12 MONTH)
        GROUP BY DATE_FORMAT(don_date, '%Y-%m')
        ORDER BY month DESC
    """)
    monthly_revenue = cursor.fetchall()

    cursor.execute("""
        SELECT 
            don_paymethod,
            COUNT(*) as transaction_count,
            SUM(CASE WHEN don_status = 'Paid' THEN don_amount ELSE 0 END) as total_amount
        FROM donations
        GROUP BY don_paymethod
        ORDER BY total_amount DESC
    """)
    payment_methods = cursor.fetchall()

    cursor.execute("""
        SELECT 
            f.fund_id,
            f.fund_title,
            f.fund_goalamount,
            COALESCE(SUM(CASE WHEN d.don_status = 'Paid' THEN d.don_amount ELSE 0 END), 0) as total_raised,
            COUNT(CASE WHEN d.don_status = 'Paid' THEN 1 END) as donation_count
        FROM fundraisers f
        LEFT JOIN donations d ON f.fund_id = d.fund_id
        WHERE f.fund_status IN ('Active', 'Completed')
        GROUP BY f.fund_id
        ORDER BY total_raised DESC
        LIMIT 10
    """)
    top_fundraisers = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('treasurer.html', 
        financial_stats=financial_stats,
        recent_transactions=recent_transactions,
        monthly_revenue=monthly_revenue,
        payment_methods=payment_methods,
        top_fundraisers=top_fundraisers)

@app.route('/treasurer/financial-reports')
def treasurer_reports():
    if 'email' not in session or session.get('role') != 'Treasurer':
        return redirect(url_for('goto_signin'))
    
    app.permanent_session_lifetime = timedelta(hours=10)

    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')
    
    if not start_date:
        start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    if not end_date:
        end_date = datetime.now().strftime('%Y-%m-%d')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT 
            COUNT(*) as total_transactions,
            COALESCE(SUM(CASE WHEN don_status = 'Paid' THEN don_amount ELSE 0 END), 0) as total_revenue,
            COALESCE(SUM(CASE WHEN don_status = 'Pending' THEN don_amount ELSE 0 END), 0) as pending_amount,
            COALESCE(SUM(CASE WHEN don_status = 'Failed' THEN don_amount ELSE 0 END), 0) as failed_amount,
            COUNT(DISTINCT don_donorid) as unique_donors
        FROM donations
        WHERE don_date >= %s AND don_date <= %s
    """, (start_date, end_date))
    summary = cursor.fetchone()

    cursor.execute("""
        SELECT 
            DATE(don_date) as date,
            SUM(CASE WHEN don_status = 'Paid' THEN don_amount ELSE 0 END) as daily_revenue,
            COUNT(CASE WHEN don_status = 'Paid' THEN 1 END) as transaction_count
        FROM donations
        WHERE don_date >= %s AND don_date <= %s
        GROUP BY DATE(don_date)
        ORDER BY date DESC
    """, (start_date, end_date))
    daily_breakdown = cursor.fetchall()

    cursor.execute("""
        SELECT 
            f.fund_id,
            f.fund_title,
            f.fund_goalamount,
            f.fund_status,
            COALESCE(SUM(CASE WHEN d.don_status = 'Paid' THEN d.don_amount ELSE 0 END), 0) as total_raised,
            COUNT(CASE WHEN d.don_status = 'Paid' THEN 1 END) as donation_count,
            (COALESCE(SUM(CASE WHEN d.don_status = 'Paid' THEN d.don_amount ELSE 0 END), 0) / f.fund_goalamount * 100) as completion_rate
        FROM fundraisers f
        LEFT JOIN donations d ON f.fund_id = d.fund_id
        WHERE f.fund_startdate >= %s AND f.fund_startdate <= %s
        GROUP BY f.fund_id
        ORDER BY total_raised DESC
    """, (start_date, end_date))
    fundraiser_performance = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('treasurer_reports.html',
        summary=summary,
        daily_breakdown=daily_breakdown,
        fundraiser_performance=fundraiser_performance,
        start_date=start_date,
        end_date=end_date)

@app.route('/treasurer/audit-trail')
def treasurer_audit_trail():
    if 'email' not in session or session.get('role') != 'Treasurer':
        return redirect(url_for('goto_signin'))

    app.permanent_session_lifetime = timedelta(hours=10)
    page = request.args.get('page', 1, type=int)
    per_page = 10
    offset = (page - 1) * per_page
    status_filter = request.args.get('status', 'all')
    search_query = (request.args.get('search') or '').strip()
    fund_page = request.args.get('fund_page', 1, type=int)
    fund_per_page = 10
    fund_offset = (fund_page - 1) * fund_per_page
    fund_status_filter = request.args.get('fund_status', 'all')
    fund_search_query = (request.args.get('fund_search') or '').strip()
    recent_page = request.args.get('recent_page', 1, type=int)
    recent_per_page = 10
    recent_offset = (recent_page - 1) * recent_per_page
    audit_page = request.args.get('audit_page', 1, type=int)
    audit_per_page = 10
    audit_offset = (audit_page - 1) * audit_per_page

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        donation_conditions = []
        donation_params = []

        if status_filter != 'all':
            donation_conditions.append("COALESCE(dfs.current_status, 'Donation Received') = %s")
            donation_params.append(status_filter)

        if search_query:
            search_like = f"%{search_query}%"
            donation_conditions.append("""
                (
                    d.don_refnum LIKE %s OR
                    d.don_donorname LIKE %s OR
                    f.fund_title LIKE %s OR
                    CAST(d.don_id AS CHAR) LIKE %s
                )
            """)
            donation_params.extend([search_like, search_like, search_like, search_like])

        donation_where_clause = f"WHERE {' AND '.join(donation_conditions)}" if donation_conditions else ""

        cursor.execute(f"""
            SELECT COUNT(*) AS total
            FROM donations d
            LEFT JOIN fundraisers f ON d.fund_id = f.fund_id
            LEFT JOIN donation_fund_status dfs ON d.don_refnum = dfs.reference_number
            {donation_where_clause}
        """, donation_params)
        donation_total_count = (cursor.fetchone() or {}).get('total', 0) or 0

        cursor.execute(f"""
            SELECT
                d.don_id,
                d.don_refnum,
                d.don_donorid,
                d.don_donorname,
                d.don_amount,
                d.don_status,
                d.don_paymethod,
                d.don_date,
                d.blockchain_tx_hash,
                f.fund_id,
                f.fund_title,
                f.fund_category,
                COALESCE(dfs.current_status, 'Donation Received') AS fund_usage_status,
                dfs.updated_at AS fund_usage_updated_at,
                dfs.updated_by AS fund_usage_updated_by,
                dp.proof_count,
                dp.latest_proof_uploaded_at,
                dp.latest_proof_filename
            FROM donations d
            LEFT JOIN fundraisers f ON d.fund_id = f.fund_id
            LEFT JOIN donation_fund_status dfs ON d.don_refnum = dfs.reference_number
            LEFT JOIN (
                SELECT
                    donation_id,
                    COUNT(*) AS proof_count,
                    MAX(uploaded_at) AS latest_proof_uploaded_at,
                    SUBSTRING_INDEX(
                        GROUP_CONCAT(proof_filename ORDER BY uploaded_at DESC, proof_id DESC SEPARATOR '||'),
                        '||',
                        1
                    ) AS latest_proof_filename
                FROM donation_completion_proofs
                GROUP BY donation_id
            ) dp ON d.don_id = dp.donation_id
            {donation_where_clause}
            ORDER BY d.don_date DESC, d.don_id DESC
            LIMIT %s OFFSET %s
        """, donation_params + [per_page, offset])
        donations = cursor.fetchall()

        for donation in donations:
            usage_status = donation.get('fund_usage_status') or 'Donation Received'
            if usage_status not in DONATION_FUND_STATUSES:
                usage_status = 'Donation Received'
            donation['fund_usage_status'] = usage_status
            donation['fund_usage_step'] = DONATION_FUND_STATUSES.index(usage_status)
            donation['fund_usage_statuses'] = DONATION_FUND_STATUSES
            donation['allowed_fund_usage_statuses'] = get_allowed_donation_fund_targets(usage_status)
            donation['proof_count'] = int(donation.get('proof_count') or 0)

        cursor.execute("""
            SELECT COUNT(*) AS has_is_verified
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'beneficiaries'
              AND COLUMN_NAME = 'is_verified'
        """)
        has_verified_col = ((cursor.fetchone() or {}).get('has_is_verified', 0) or 0) > 0

        fundraiser_conditions = []
        fundraiser_params = []

        if fund_status_filter != 'all':
            fundraiser_conditions.append("COALESCE(fsw.current_status, f.fund_status) = %s")
            fundraiser_params.append(fund_status_filter)

        if fund_search_query:
            search_like = f"%{fund_search_query}%"
            fundraiser_conditions.append("""
                (
                    f.fund_title LIKE %s OR
                    COALESCE(f.fund_category, '') LIKE %s OR
                    CAST(f.fund_id AS CHAR) LIKE %s
                )
            """)
            fundraiser_params.extend([search_like, search_like, search_like])

        fundraiser_where_clause = f"WHERE {' AND '.join(fundraiser_conditions)}" if fundraiser_conditions else ""

        cursor.execute(f"""
            SELECT COUNT(*) AS total
            FROM fundraisers f
            LEFT JOIN fund_status_workflow fsw ON f.fund_id = fsw.fund_id
            {fundraiser_where_clause}
        """, fundraiser_params)
        fundraiser_total_count = (cursor.fetchone() or {}).get('total', 0) or 0

        cursor.execute(f"""
            SELECT
                f.fund_id,
                f.fund_title,
                f.fund_category,
                f.fund_status,
                COALESCE(fsw.current_status,
                    CASE
                        WHEN f.fund_status = 'Completed' THEN 'Completed'
                        WHEN f.fund_status = 'Active' THEN 'Approved'
                        ELSE 'Pending'
                    END
                ) AS workflow_status,
                fsw.updated_at AS workflow_updated_at,
                fsw.updated_by AS workflow_updated_by,
                f.fund_goalamount,
                f.fund_startdate,
                fp.proof_count,
                fp.latest_proof_uploaded_at,
                fp.latest_proof_filename,
                COALESCE(SUM(CASE WHEN d.don_status = 'Paid' THEN d.don_amount ELSE 0 END), 0) AS total_raised,
                COUNT(CASE WHEN d.don_status = 'Paid' THEN 1 END) AS paid_donations,
                MAX(CASE WHEN d.don_status = 'Paid' THEN d.don_date END) AS latest_paid_donation,
                COUNT(
                    CASE
                        WHEN d.don_status = 'Paid'
                         AND d.blockchain_tx_hash IS NOT NULL
                         AND TRIM(d.blockchain_tx_hash) <> ''
                        THEN 1
                    END
                ) AS blockchain_records
            FROM fundraisers f
            LEFT JOIN fund_status_workflow fsw ON f.fund_id = fsw.fund_id
            LEFT JOIN donations d ON f.fund_id = d.fund_id
            LEFT JOIN (
                SELECT
                    fund_id,
                    COUNT(*) AS proof_count,
                    MAX(uploaded_at) AS latest_proof_uploaded_at,
                    SUBSTRING_INDEX(
                        GROUP_CONCAT(proof_filename ORDER BY uploaded_at DESC, proof_id DESC SEPARATOR '||'),
                        '||',
                        1
                    ) AS latest_proof_filename
                FROM fund_completion_proofs
                GROUP BY fund_id
            ) fp ON f.fund_id = fp.fund_id
            {fundraiser_where_clause}
            GROUP BY f.fund_id
            ORDER BY total_raised DESC, f.fund_startdate DESC
            LIMIT %s OFFSET %s
        """, fundraiser_params + [fund_per_page, fund_offset])
        fundraisers = cursor.fetchall()

        fundraiser_ids = [fund['fund_id'] for fund in fundraisers]
        beneficiary_map = {}

        if fundraiser_ids:
            placeholders = ','.join(['%s'] * len(fundraiser_ids))
            if has_verified_col:
                cursor.execute(f"""
                    SELECT
                        fund_id,
                        COUNT(*) AS total_beneficiaries,
                        COUNT(CASE WHEN is_verified = 1 THEN 1 END) AS verified_beneficiaries
                    FROM beneficiaries
                    WHERE fund_id IN ({placeholders})
                    GROUP BY fund_id
                """, fundraiser_ids)
            else:
                cursor.execute(f"""
                    SELECT
                        fund_id,
                        COUNT(*) AS total_beneficiaries,
                        0 AS verified_beneficiaries
                    FROM beneficiaries
                    WHERE fund_id IN ({placeholders})
                    GROUP BY fund_id
                """, fundraiser_ids)

            for row in cursor.fetchall():
                beneficiary_map[row['fund_id']] = {
                    'total_beneficiaries': row.get('total_beneficiaries', 0) or 0,
                    'verified_beneficiaries': row.get('verified_beneficiaries', 0) or 0
                }

        for fund in fundraisers:
            goal_amount = float(fund.get('fund_goalamount') or 0)
            total_raised = float(fund.get('total_raised') or 0)
            fund['progress_percent'] = min((total_raised / goal_amount) * 100, 100) if goal_amount > 0 else 0
            fund['remaining_to_goal'] = max(goal_amount - total_raised, 0)
            fund['beneficiary_stats'] = beneficiary_map.get(
                fund['fund_id'],
                {'total_beneficiaries': 0, 'verified_beneficiaries': 0}
            )
            fund['proof_count'] = int(fund.get('proof_count') or 0)
            workflow_status = fund.get('workflow_status') or fund.get('fund_status') or 'Pending'
            if workflow_status not in FUND_WORKFLOW_STATUSES:
                workflow_status = 'Pending'
            fund['workflow_status'] = workflow_status
            fund['workflow_step'] = FUND_WORKFLOW_STATUSES.index(workflow_status)
            fund['workflow_statuses'] = FUND_WORKFLOW_STATUSES
            fund['allowed_workflow_statuses'] = get_allowed_fund_workflow_targets(workflow_status)

        cursor.execute("""
            SELECT
                COALESCE(SUM(CASE WHEN don_status = 'Paid' THEN don_amount ELSE 0 END), 0) AS total_managed_funds,
                COUNT(CASE WHEN don_status = 'Paid' THEN 1 END) AS paid_donations,
                COUNT(
                    CASE
                        WHEN don_status = 'Paid'
                         AND blockchain_tx_hash IS NOT NULL
                         AND TRIM(blockchain_tx_hash) <> ''
                        THEN 1
                    END
                ) AS blockchain_records
            FROM donations
        """)
        donation_summary = cursor.fetchone() or {}

        cursor.execute("""
            SELECT
                COUNT(CASE WHEN current_status = 'Donation Received' THEN 1 END) AS pending_usage,
                COUNT(CASE WHEN current_status IN ('Payment Confirmed', 'Pending Allocation', 'Funds Disbursed') THEN 1 END) AS in_progress_usage,
                COUNT(CASE WHEN current_status = 'Completed / Used' THEN 1 END) AS completed_usage
            FROM donation_fund_status
        """)
        usage_summary = cursor.fetchone() or {}

        cursor.execute("""
            SELECT COUNT(*) AS total_campaigns,
                   COUNT(CASE WHEN fund_status = 'Active' THEN 1 END) AS active_campaigns,
                   COUNT(CASE WHEN fund_status = 'Completed' THEN 1 END) AS completed_campaigns
            FROM fundraisers
        """)
        campaign_summary = cursor.fetchone() or {}

        if has_verified_col:
            cursor.execute("""
                SELECT
                    COUNT(*) AS total_beneficiaries,
                    COUNT(CASE WHEN is_verified = 1 THEN 1 END) AS verified_beneficiaries
                FROM beneficiaries
            """)
        else:
            cursor.execute("""
                SELECT
                    COUNT(*) AS total_beneficiaries,
                    0 AS verified_beneficiaries
                FROM beneficiaries
            """)
        beneficiary_summary = cursor.fetchone() or {}

        cursor.execute(f"""
            SELECT COUNT(*) AS total
            FROM donations d
            LEFT JOIN fundraisers f ON d.fund_id = f.fund_id
            LEFT JOIN fund_status_workflow fsw ON f.fund_id = fsw.fund_id
            {fundraiser_where_clause}
        """, fundraiser_params)
        recent_total_count = (cursor.fetchone() or {}).get('total', 0) or 0

        cursor.execute(f"""
            SELECT
                d.don_refnum,
                d.don_donorname,
                d.don_amount,
                d.don_status,
                d.don_paymethod,
                d.don_date,
                d.blockchain_tx_hash,
                f.fund_id,
                f.fund_title,
                f.fund_status
            FROM donations d
            LEFT JOIN fundraisers f ON d.fund_id = f.fund_id
            LEFT JOIN fund_status_workflow fsw ON f.fund_id = fsw.fund_id
            {fundraiser_where_clause}
            ORDER BY d.don_date DESC
            LIMIT %s OFFSET %s
        """, fundraiser_params + [recent_per_page, recent_offset])
        recent_donations = cursor.fetchall()

        cursor.execute("""
            SELECT COUNT(*) AS total
            FROM audit_trail_logs
            WHERE action IN (
                'DONATION_CREATED',
                'DONATION_STATUS_UPDATED',
                'DONATION_PAYMENT_CONFIRMED',
                'CASH_DONATION_RECEIVED',
                'CASH_DONATION_CONFIRMED',
                'DONATION_FUND_STATUS_UPDATED',
                'DONATION_COMPLETION_PROOF_UPLOADED',
                'FUNDRAISER_COMPLETED',
                'FUND_WORKFLOW_STATUS_UPDATED',
                'FUND_COMPLETION_PROOF_UPLOADED'
            )
        """)
        audit_total_count = (cursor.fetchone() or {}).get('total', 0) or 0

        cursor.execute("""
            SELECT
                audit_id,
                event_time,
                actor_email,
                actor_role,
                action,
                entity_type,
                entity_id,
                status,
                after_data,
                metadata
            FROM audit_trail_logs
            WHERE action IN (
                'DONATION_CREATED',
                'DONATION_STATUS_UPDATED',
                'DONATION_PAYMENT_CONFIRMED',
                'CASH_DONATION_RECEIVED',
                'CASH_DONATION_CONFIRMED',
                'DONATION_FUND_STATUS_UPDATED',
                'DONATION_COMPLETION_PROOF_UPLOADED',
                'FUNDRAISER_COMPLETED',
                'FUND_WORKFLOW_STATUS_UPDATED',
                'FUND_COMPLETION_PROOF_UPLOADED'
            )
            ORDER BY event_time DESC, audit_id DESC
            LIMIT %s OFFSET %s
        """, [audit_per_page, audit_offset])
        recent_audit_events = cursor.fetchall()
        for event in recent_audit_events:
            try:
                event['after_data_parsed'] = json.loads(event.get('after_data') or '{}')
            except Exception:
                event['after_data_parsed'] = {}

        donation_total_pages = max(1, math.ceil(donation_total_count / per_page)) if donation_total_count else 1
        pagination = {
            'page': page,
            'per_page': per_page,
            'total': donation_total_count,
            'total_pages': donation_total_pages,
            'has_prev': page > 1,
            'has_next': page < donation_total_pages,
            'prev_num': page - 1 if page > 1 else None,
            'next_num': page + 1 if page < donation_total_pages else None
        }

        fundraiser_total_pages = max(1, math.ceil(fundraiser_total_count / fund_per_page)) if fundraiser_total_count else 1
        fundraiser_pagination = {
            'page': fund_page,
            'per_page': fund_per_page,
            'total': fundraiser_total_count,
            'total_pages': fundraiser_total_pages,
            'has_prev': fund_page > 1,
            'has_next': fund_page < fundraiser_total_pages,
            'prev_num': fund_page - 1 if fund_page > 1 else None,
            'next_num': fund_page + 1 if fund_page < fundraiser_total_pages else None
        }

        recent_total_pages = max(1, math.ceil(recent_total_count / recent_per_page)) if recent_total_count else 1
        recent_pagination = {
            'page': recent_page,
            'per_page': recent_per_page,
            'total': recent_total_count,
            'total_pages': recent_total_pages,
            'has_prev': recent_page > 1,
            'has_next': recent_page < recent_total_pages,
            'prev_num': recent_page - 1 if recent_page > 1 else None,
            'next_num': recent_page + 1 if recent_page < recent_total_pages else None
        }

        audit_total_pages = max(1, math.ceil(audit_total_count / audit_per_page)) if audit_total_count else 1
        audit_pagination = {
            'page': audit_page,
            'per_page': audit_per_page,
            'total': audit_total_count,
            'total_pages': audit_total_pages,
            'has_prev': audit_page > 1,
            'has_next': audit_page < audit_total_pages,
            'prev_num': audit_page - 1 if audit_page > 1 else None,
            'next_num': audit_page + 1 if audit_page < audit_total_pages else None
        }

        summary = {
            'total_managed_funds': float(donation_summary.get('total_managed_funds') or 0),
            'paid_donations': int(donation_summary.get('paid_donations') or 0),
            'blockchain_records': int(donation_summary.get('blockchain_records') or 0),
            'total_campaigns': int(campaign_summary.get('total_campaigns') or 0),
            'active_campaigns': int(campaign_summary.get('active_campaigns') or 0),
            'completed_campaigns': int(campaign_summary.get('completed_campaigns') or 0),
            'total_beneficiaries': int(beneficiary_summary.get('total_beneficiaries') or 0),
            'verified_beneficiaries': int(beneficiary_summary.get('verified_beneficiaries') or 0),
            'pending_usage': int(usage_summary.get('pending_usage') or 0),
            'in_progress_usage': int(usage_summary.get('in_progress_usage') or 0),
            'completed_usage': int(usage_summary.get('completed_usage') or 0)
        }

        return render_template(
            'treasurer_audit_trail.html',
            summary=summary,
            donations=donations,
            fundraisers=fundraisers,
            recent_donations=recent_donations,
            recent_audit_events=recent_audit_events,
            search_query=search_query,
            status_filter=status_filter,
            pagination=pagination,
            donation_workflow_statuses=DONATION_FUND_STATUSES,
            workflow_statuses=FUND_WORKFLOW_STATUSES,
            fund_search_query=fund_search_query,
            fund_status_filter=fund_status_filter,
            fundraiser_pagination=fundraiser_pagination,
            recent_pagination=recent_pagination,
            audit_pagination=audit_pagination
        )
    finally:
        cursor.close()
        conn.close()

@app.route('/api/treasurer/update-donation-fund-status', methods=['POST'])
def treasurer_update_donation_fund_status():
    if 'email' not in session or session.get('role') != 'Treasurer':
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json(silent=True) or {}
    reference_number = (data.get('reference_number') or data.get('don_refnum') or '').strip()
    new_status = (data.get('status') or '').strip()

    if not reference_number:
        return jsonify({'error': 'Missing reference_number'}), 400

    if new_status not in DONATION_FUND_STATUSES:
        return jsonify({'error': 'Invalid donation fund status'}), 400

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT
                d.don_id,
                d.don_refnum,
                d.don_status,
                d.don_amount,
                d.don_donorid,
                d.don_donorname,
                d.fund_id,
                f.fund_title,
                COALESCE(dfs.current_status, 'Donation Received') AS fund_usage_status
            FROM donations d
            LEFT JOIN fundraisers f ON d.fund_id = f.fund_id
            LEFT JOIN donation_fund_status dfs ON d.don_refnum = dfs.reference_number
            WHERE d.don_refnum = %s
            LIMIT 1
        """, (reference_number,))
        donation = cursor.fetchone()

        if not donation:
            return jsonify({'error': 'Donation not found'}), 404

        donation_id = donation.get('don_id')
        current_status = donation.get('fund_usage_status') or 'Donation Received'
        if current_status not in DONATION_FUND_STATUSES:
            current_status = 'Payment Confirmed' if donation.get('don_status') == 'Paid' else 'Donation Received'

        if new_status != 'Donation Received' and donation.get('don_status') != 'Paid':
            return jsonify({'error': 'Payment must be confirmed before fund usage can progress.'}), 400

        allowed_targets = get_allowed_donation_fund_targets(current_status)
        if new_status not in allowed_targets:
            return jsonify({
                'error': (
                    f'Invalid donation fund progression. {current_status} can only move to '
                    f"{', '.join(allowed_targets)}."
                )
            }), 400

        if new_status == current_status:
            return jsonify({'success': True, 'message': f'Donation already at {new_status}'})

        audit_id = log_audit_event(
            action='DONATION_FUND_STATUS_UPDATED',
            entity_type='donation',
            entity_id=donation.get('don_refnum'),
            before_data={
                'don_id': donation_id,
                'don_refnum': donation.get('don_refnum'),
                'fund_usage_status': current_status
            },
            after_data={
                'don_id': donation_id,
                'don_refnum': donation.get('don_refnum'),
                'fund_id': donation.get('fund_id'),
                'fund_title': donation.get('fund_title'),
                'don_amount': float(donation.get('don_amount') or 0),
                'fund_usage_status': new_status,
                'status_changed': f'{current_status} -> {new_status}',
                'action_datetime': datetime.now(),
                'treasurer_user_id': session.get('user_id'),
                'treasurer_email': session.get('email')
            },
            metadata={
                'source': 'treasurer_update_donation_fund_status',
                'workflow': DONATION_FUND_STATUSES
            },
            conn=conn,
            cursor=cursor
        )

        record_donation_fund_status_update(
            cursor=cursor,
            reference_number=donation.get('don_refnum'),
            donation_id=donation_id,
            new_status=new_status,
            previous_status=current_status,
            updated_by=session.get('user_id'),
            audit_id=audit_id if isinstance(audit_id, int) else None,
            note='Treasurer status update'
        )

        conn.commit()
        return jsonify({
            'success': True,
            'message': f'Donation fund status updated to {new_status}',
            'status': new_status,
            'reference_number': donation.get('don_refnum'),
            'audit_id': audit_id if isinstance(audit_id, int) else None,
            'requires_proof': new_status == 'Completed / Used'
        })
    except Exception as e:
        conn.rollback()
        print(f"Error updating donation fund status: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/treasurer/donations/<int:donation_id>/completion-proof', methods=['POST'])
def treasurer_upload_donation_completion_proof(donation_id):
    if 'email' not in session or session.get('role') != 'Treasurer':
        return redirect(url_for('goto_signin'))

    proof_file = request.files.get('completion_proof')
    proof_note = (request.form.get('proof_note') or '').strip()[:500]

    if not proof_file or not proof_file.filename:
        return redirect(url_for('treasurer_audit_trail', error='missing_proof'))

    if not allowed_file(proof_file.filename):
        return redirect(url_for('treasurer_audit_trail', error='invalid_proof_type'))

    if PIL_AVAILABLE:
        try:
            Image.open(proof_file.stream).verify()
            proof_file.stream.seek(0)
        except Exception:
            return redirect(url_for('treasurer_audit_trail', error='invalid_proof_type'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT
                d.don_id,
                d.don_refnum,
                d.fund_id,
                COALESCE(dfs.current_status, 'Donation Received') AS fund_usage_status
            FROM donations d
            LEFT JOIN donation_fund_status dfs ON d.don_refnum = dfs.reference_number
            WHERE d.don_id = %s
        """, (donation_id,))
        donation = cursor.fetchone()

        if not donation:
            return redirect(url_for('treasurer_audit_trail', error='donation_not_found'))

        if (donation.get('fund_usage_status') or '').strip().lower() != 'completed / used':
            return redirect(url_for('treasurer_audit_trail', error='donation_not_completed'))

        original_filename = secure_filename(proof_file.filename)
        extension = original_filename.rsplit('.', 1)[1].lower()
        stored_filename = f"fund_completion_proofs/donation_{uuid.uuid4().hex}_{donation_id}.{extension}"
        stored_path = os.path.join(UPLOAD_FOLDER, stored_filename)
        proof_file.save(stored_path)

        cursor.execute("""
            INSERT INTO donation_completion_proofs (
                donation_id, fund_id, uploaded_by, proof_filename, original_filename,
                proof_mime_type, proof_note, uploaded_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
        """, (
            donation_id,
            donation.get('fund_id'),
            session.get('user_id'),
            stored_filename,
            original_filename,
            (proof_file.mimetype or '')[:120],
            proof_note or None
        ))
        proof_id = cursor.lastrowid

        audit_id = log_audit_event(
            action='DONATION_COMPLETION_PROOF_UPLOADED',
            entity_type='donation',
            entity_id=donation.get('don_refnum'),
            after_data={
                'don_id': donation_id,
                'don_refnum': donation.get('don_refnum'),
                'fund_id': donation.get('fund_id'),
                'fund_usage_status': donation.get('fund_usage_status'),
                'proof_id': proof_id,
                'proof_filename': stored_filename,
                'proof_note': proof_note or None,
                'uploaded_at': datetime.now()
            },
            metadata={
                'source': 'treasurer_upload_donation_completion_proof',
                'publicly_viewable': True
            },
            conn=conn,
            cursor=cursor
        )

        if isinstance(audit_id, int):
            cursor.execute(
                "UPDATE donation_completion_proofs SET audit_id = %s WHERE proof_id = %s",
                (audit_id, proof_id)
            )

        conn.commit()
        return redirect(url_for('treasurer_audit_trail', proof_uploaded='1'))
    except Exception as e:
        conn.rollback()
        print(f"Error uploading donation completion proof: {e}")
        return redirect(url_for('treasurer_audit_trail', error='proof_upload_failed'))
    finally:
        cursor.close()
        conn.close()

@app.route('/api/treasurer/update-fund-workflow-status', methods=['POST'])
def treasurer_update_fund_workflow_status():
    if 'email' not in session or session.get('role') != 'Treasurer':
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json(silent=True) or {}
    fund_id = data.get('fund_id')
    new_status = (data.get('status') or '').strip()

    try:
        fund_id = int(fund_id)
    except (TypeError, ValueError):
        return jsonify({'error': 'Invalid fund_id'}), 400

    if new_status not in FUND_WORKFLOW_STATUSES:
        return jsonify({'error': 'Invalid workflow status'}), 400

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT
                f.fund_id,
                f.fund_title,
                f.fund_status,
                COALESCE(fsw.current_status,
                    CASE
                        WHEN f.fund_status = 'Completed' THEN 'Completed'
                        WHEN f.fund_status = 'Active' THEN 'Approved'
                        ELSE 'Pending'
                    END
                ) AS workflow_status
            FROM fundraisers f
            LEFT JOIN fund_status_workflow fsw ON f.fund_id = fsw.fund_id
            WHERE f.fund_id = %s
        """, (fund_id,))
        fund = cursor.fetchone()

        if not fund:
            return jsonify({'error': 'Fund not found'}), 404

        current_status = fund.get('workflow_status') or 'Pending'
        if current_status not in FUND_WORKFLOW_STATUSES:
            current_status = 'Pending'

        allowed_targets = get_allowed_fund_workflow_targets(current_status)
        if new_status not in allowed_targets:
            return jsonify({
                'error': (
                    f'Invalid status progression. {current_status} can only move to '
                    f"{', '.join(allowed_targets)}."
                )
            }), 400

        if new_status == current_status:
            return jsonify({
                'success': True,
                'message': f'Fund already at {new_status}',
                'status': new_status
            })

        cursor.execute("""
            INSERT INTO fund_status_workflow (fund_id, current_status, updated_by, created_at, updated_at)
            VALUES (%s, %s, %s, NOW(), NOW())
            ON DUPLICATE KEY UPDATE
                current_status = VALUES(current_status),
                updated_by = VALUES(updated_by),
                updated_at = NOW()
        """, (fund_id, new_status, session.get('user_id')))

        public_status = FUND_WORKFLOW_PUBLIC_STATUS.get(new_status)
        if public_status:
            cursor.execute("""
                UPDATE fundraisers
                SET fund_status = %s
                WHERE fund_id = %s
            """, (public_status, fund_id))

        action_name = 'FUNDRAISER_COMPLETED' if new_status == 'Completed' else 'FUND_WORKFLOW_STATUS_UPDATED'
        audit_id = log_audit_event(
            action=action_name,
            entity_type='fundraiser',
            entity_id=fund_id,
            before_data={
                'fund_id': fund_id,
                'fund_status': fund.get('fund_status'),
                'workflow_status': current_status
            },
            after_data={
                'fund_id': fund_id,
                'fund_status': public_status or fund.get('fund_status'),
                'workflow_status': new_status,
                'status_changed': f'{current_status} -> {new_status}',
                'action_datetime': datetime.now(),
                'treasurer_user_id': session.get('user_id'),
                'treasurer_email': session.get('email')
            },
            metadata={
                'source': 'treasurer_update_fund_workflow_status',
                'workflow': FUND_WORKFLOW_STATUSES
            },
            conn=conn,
            cursor=cursor
        )

        conn.commit()
        return jsonify({
            'success': True,
            'message': f'Fund status updated to {new_status}',
            'status': new_status,
            'audit_id': audit_id if isinstance(audit_id, int) else None,
            'requires_proof': new_status == 'Completed'
        })
    except Exception as e:
        conn.rollback()
        print(f"Error updating fund workflow status: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/treasurer/fundraisers/<int:fundraiser_id>/completion-proof', methods=['POST'])
def treasurer_upload_completion_proof(fundraiser_id):
    if 'email' not in session or session.get('role') != 'Treasurer':
        return redirect(url_for('goto_signin'))

    proof_file = request.files.get('completion_proof')
    proof_note = (request.form.get('proof_note') or '').strip()[:500]

    if not proof_file or not proof_file.filename:
        return redirect(url_for('treasurer_audit_trail', error='missing_proof'))

    if not allowed_file(proof_file.filename):
        return redirect(url_for('treasurer_audit_trail', error='invalid_proof_type'))

    if PIL_AVAILABLE:
        try:
            Image.open(proof_file.stream).verify()
            proof_file.stream.seek(0)
        except Exception:
            return redirect(url_for('treasurer_audit_trail', error='invalid_proof_type'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT
                f.fund_id,
                f.fund_title,
                f.fund_status,
                f.fund_goalamount,
                COALESCE(fsw.current_status, f.fund_status) AS workflow_status
            FROM fundraisers f
            LEFT JOIN fund_status_workflow fsw ON f.fund_id = fsw.fund_id
            WHERE f.fund_id = %s
        """, (fundraiser_id,))
        fundraiser = cursor.fetchone()

        if not fundraiser:
            return redirect(url_for('treasurer_audit_trail', error='fund_not_found'))

        if (fundraiser.get('workflow_status') or fundraiser.get('fund_status') or '').strip().lower() != 'completed':
            return redirect(url_for('treasurer_audit_trail', error='fund_not_completed'))

        original_filename = secure_filename(proof_file.filename)
        extension = original_filename.rsplit('.', 1)[1].lower()
        stored_filename = f"fund_completion_proofs/{uuid.uuid4().hex}_{fundraiser_id}.{extension}"
        stored_path = os.path.join(UPLOAD_FOLDER, stored_filename)
        proof_file.save(stored_path)

        cursor.execute("""
            INSERT INTO fund_completion_proofs (
                fund_id, uploaded_by, proof_filename, original_filename,
                proof_mime_type, proof_note, uploaded_at
            ) VALUES (%s, %s, %s, %s, %s, %s, NOW())
        """, (
            fundraiser_id,
            session.get('user_id'),
            stored_filename,
            original_filename,
            (proof_file.mimetype or '')[:120],
            proof_note or None
        ))
        proof_id = cursor.lastrowid

        audit_id = log_audit_event(
            action='FUND_COMPLETION_PROOF_UPLOADED',
            entity_type='fundraiser',
            entity_id=fundraiser_id,
            before_data=None,
            after_data={
                'fund_id': fundraiser_id,
                'fund_status': fundraiser.get('fund_status'),
                'workflow_status': fundraiser.get('workflow_status'),
                'proof_id': proof_id,
                'proof_filename': stored_filename,
                'proof_note': proof_note or None,
                'uploaded_at': datetime.now()
            },
            metadata={
                'source': 'treasurer_upload_completion_proof',
                'publicly_viewable': True
            },
            conn=conn,
            cursor=cursor
        )

        if isinstance(audit_id, int):
            cursor.execute(
                "UPDATE fund_completion_proofs SET audit_id = %s WHERE proof_id = %s",
                (audit_id, proof_id)
            )

        cursor.execute("""
            SELECT
                d.don_id,
                d.don_refnum,
                d.don_amount,
                d.don_status,
                COALESCE(dfs.current_status,
                    CASE
                        WHEN d.don_status = 'Paid' THEN 'Payment Confirmed'
                        ELSE 'Donation Received'
                    END
                ) AS fund_usage_status
            FROM donations d
            LEFT JOIN donation_fund_status dfs ON d.don_refnum = dfs.reference_number
            WHERE d.fund_id = %s
              AND d.don_status = 'Paid'
        """, (fundraiser_id,))
        related_donations = cursor.fetchall()

        for donation in related_donations:
            current_status = donation.get('fund_usage_status') or 'Payment Confirmed'
            if current_status == 'Completed / Used':
                continue

            donation_audit_id = log_audit_event(
                action='DONATION_FUND_STATUS_UPDATED',
                entity_type='donation',
                entity_id=donation.get('don_refnum'),
                before_data={
                    'don_id': donation.get('don_id'),
                    'don_refnum': donation.get('don_refnum'),
                    'fund_usage_status': current_status
                },
                after_data={
                    'don_id': donation.get('don_id'),
                    'don_refnum': donation.get('don_refnum'),
                    'fund_id': fundraiser_id,
                    'fund_title': fundraiser.get('fund_title'),
                    'don_amount': float(donation.get('don_amount') or 0),
                    'fund_usage_status': 'Completed / Used',
                    'status_changed': f"{current_status} -> Completed / Used",
                    'action_datetime': datetime.now(),
                    'treasurer_user_id': session.get('user_id'),
                    'treasurer_email': session.get('email')
                },
                metadata={
                    'source': 'treasurer_upload_completion_proof',
                    'reason': 'Fundraiser completion proof uploaded'
                },
                conn=conn,
                cursor=cursor
            )

            record_donation_fund_status_update(
                cursor=cursor,
                reference_number=donation.get('don_refnum'),
                donation_id=donation.get('don_id'),
                new_status='Completed / Used',
                previous_status=current_status,
                updated_by=session.get('user_id'),
                audit_id=donation_audit_id if isinstance(donation_audit_id, int) else None,
                note='Marked completed after fundraiser completion proof upload'
            )

        conn.commit()
        return redirect(url_for('treasurer_audit_trail', proof_uploaded='1'))
    except Exception as e:
        conn.rollback()
        print(f"Error uploading completion proof: {e}")
        return redirect(url_for('treasurer_audit_trail', error='proof_upload_failed'))
    finally:
        cursor.close()
        conn.close()

@app.route('/treasurer/donations')
def treasurer_donations():
    if 'email' not in session or session.get('role') != 'Treasurer':
        return redirect(url_for('goto_signin'))
    
    app.permanent_session_lifetime = timedelta(hours=10)

    page = request.args.get('page', 1, type=int)
    per_page = 15
    offset = (page - 1) * per_page
    status_filter = request.args.get('status', 'all')
    search_query = request.args.get('search', '')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    conditions = []
    params = []
    
    if status_filter != 'all':
        conditions.append("d.don_status = %s")
        params.append(status_filter)
    
    if search_query:
        conditions.append("(d.don_donorname LIKE %s OR f.fund_title LIKE %s OR d.don_refnum LIKE %s)")
        search_param = f"%{search_query}%"
        params.extend([search_param, search_param, search_param])

    where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

    count_query = f"""
        SELECT COUNT(*) as total
        FROM donations d
        LEFT JOIN fundraisers f ON d.fund_id = f.fund_id
        {where_clause}
    """
    cursor.execute(count_query, params)
    total_donations = cursor.fetchone()['total']

    donations_query = f"""
        SELECT d.*, f.fund_title, u.name as donor_name, u.email as donor_email
        FROM donations d
        LEFT JOIN fundraisers f ON d.fund_id = f.fund_id
        LEFT JOIN users u ON d.don_donorid = u.id
        {where_clause}
        ORDER BY d.don_date DESC, d.don_id DESC
        LIMIT %s OFFSET %s
    """
    cursor.execute(donations_query, params + [per_page, offset])
    donations = cursor.fetchall()

    total_pages = (total_donations + per_page - 1) // per_page
    has_prev = page > 1
    has_next = page < total_pages

    pagination_info = {
        'page': page,
        'per_page': per_page,
        'total': total_donations,
        'total_pages': total_pages,
        'has_prev': has_prev,
        'has_next': has_next,
        'prev_num': page - 1 if has_prev else None,
        'next_num': page + 1 if has_next else None
    }

    cursor.close()
    conn.close()

    return render_template('treasurer_donations.html',
        donations=donations,
        pagination=pagination_info,
        status_filter=status_filter,
        search_query=search_query)

@app.route('/treasurer/analytics')
def treasurer_analytics():
    if 'email' not in session or session.get('role') != 'Treasurer':
        return redirect(url_for('goto_signin'))
    
    app.permanent_session_lifetime = timedelta(hours=10)

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT 
            DATE_FORMAT(don_date, '%Y-%m') as month,
            SUM(CASE WHEN don_status = 'Paid' THEN don_amount ELSE 0 END) as revenue,
            COUNT(CASE WHEN don_status = 'Paid' THEN 1 END) as transaction_count,
            AVG(CASE WHEN don_status = 'Paid' THEN don_amount END) as avg_donation
        FROM donations
        WHERE don_date >= DATE_SUB(NOW(), INTERVAL 12 MONTH)
        GROUP BY DATE_FORMAT(don_date, '%Y-%m')
        ORDER BY month
    """)
    revenue_analytics = cursor.fetchall()

    cursor.execute("""
        SELECT 
            don_donorname,
            COUNT(*) as donation_count,
            SUM(CASE WHEN don_status = 'Paid' THEN don_amount ELSE 0 END) as total_donated,
            MAX(don_date) as last_donation
        FROM donations
        WHERE don_status = 'Paid'
        GROUP BY don_donorname
        ORDER BY total_donated DESC
        LIMIT 20
    """)
    top_donors = cursor.fetchall()

    cursor.execute("""
        SELECT 
            don_paymethod,
            COUNT(*) as transaction_count,
            SUM(CASE WHEN don_status = 'Paid' THEN don_amount ELSE 0 END) as total_amount,
            AVG(CASE WHEN don_status = 'Paid' THEN don_amount END) as avg_amount,
            COUNT(CASE WHEN don_status = 'Paid' THEN 1 END) as successful_count,
            (COUNT(CASE WHEN don_status = 'Paid' THEN 1 END) * 100.0 / COUNT(*)) as success_rate
        FROM donations
        GROUP BY don_paymethod
        ORDER BY total_amount DESC
    """)
    payment_analytics = cursor.fetchall()

    cursor.execute("""
        SELECT 
            f.fund_category,
            COUNT(*) as fundraiser_count,
            SUM(f.fund_goalamount) as total_goal,
            SUM(COALESCE(d.total_raised, 0)) as total_raised,
            AVG(COALESCE(d.total_raised, 0) / f.fund_goalamount * 100) as avg_success_rate
        FROM fundraisers f
        LEFT JOIN (
            SELECT 
                fund_id,
                SUM(CASE WHEN don_status = 'Paid' THEN don_amount ELSE 0 END) as total_raised
            FROM donations
            GROUP BY fund_id
        ) d ON f.fund_id = d.fund_id
        WHERE f.fund_status IN ('Active', 'Completed')
        GROUP BY f.fund_category
        ORDER BY total_raised DESC
    """)
    category_analytics = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('treasurer_analytics.html',
        revenue_analytics=revenue_analytics,
        top_donors=top_donors,
        payment_analytics=payment_analytics,
        category_analytics=category_analytics)

@app.route('/treasurer/cash-donations')
def treasurer_cash_donations():
    if 'email' not in session or session.get('role') != 'Treasurer':
        return redirect(url_for('goto_signin'))
    
    page = request.args.get('page', 1, type=int)
    per_page = 15
    offset = (page - 1) * per_page

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    
    try:
        cursor.execute("""
            SELECT COUNT(*) AS total
            FROM donations d
            WHERE d.don_paymethod IN ('Cash', 'Cheque', 'In-Kind')
        """)
        total_count = cursor.fetchone()['total']

        cursor.execute("""
            SELECT d.*, f.fund_title, f.fund_id
            FROM donations d
            LEFT JOIN fundraisers f ON d.fund_id = f.fund_id
            WHERE d.don_paymethod IN ('Cash', 'Cheque', 'In-Kind')
            ORDER BY d.don_date DESC, d.don_id DESC
            LIMIT %s OFFSET %s
        """, (per_page, offset))
        cash_donations = cursor.fetchall()
        for donation in cash_donations:
            donation['don_notes'] = extract_display_notes(donation.get('don_notes'))

        total_pages = max(1, math.ceil(total_count / per_page)) if total_count else 1
        pagination_info = {
            'page': page,
            'per_page': per_page,
            'total': total_count,
            'total_pages': total_pages,
            'has_prev': page > 1,
            'has_next': page < total_pages,
            'prev_num': page - 1 if page > 1 else None,
            'next_num': page + 1 if page < total_pages else None
        }

        response = make_response(render_template(
            'treasurer_cash_donations.html',
            cash_donations=cash_donations,
            pagination=pagination_info
        ))
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response
    finally:
        cursor.close()
        connection.close()

@app.route('/treasurer/cash-donations/entry', methods=['GET', 'POST'])
def treasurer_cash_entry():
    if 'email' not in session or session.get('role') != 'Treasurer':
        return redirect(url_for('goto_signin'))
    
    app.permanent_session_lifetime = timedelta(hours=10)
    conn = None
    cursor = None

    if request.method == 'POST':
        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            donor_name = request.form.get('donor_name', '').strip()
            contact_number = request.form.get('contact_number', '').strip()
            payment_type = (
                request.form.get('type') or
                request.form.get('donation_type') or
                request.form.get('payment_type', 'Cash')
            )
            fund_id_raw = request.form.get('fundraiser_id') or request.form.get('fund_id')
            fund_id = int(fund_id_raw) if fund_id_raw else 0
            recorder_user_id = int(session.get('user_id') or 0)
            donation_date = datetime.now()
            notes = request.form.get('notes', '').strip()

            if payment_type not in ('Cash', 'Cheque', 'In-Kind'):
                raise ValueError("Invalid in-person donation type selected.")

            if contact_number and not re.fullmatch(r'\d+', contact_number):
                raise ValueError("Contact number must contain numbers only.")

            if not fund_id:
                cursor.execute("""
                    SELECT fund_id
                    FROM fundraisers
                    WHERE LOWER(COALESCE(fund_status, '')) = 'active'
                    ORDER BY fund_startdate DESC, fund_id DESC
                    LIMIT 1
                """)
                fallback = cursor.fetchone()
                fund_id = int(fallback[0]) if fallback else 0

            if not fund_id:
                raise ValueError("No valid fundraiser available. Please select a fundraiser before recording donation.")

            if not recorder_user_id:
                raise ValueError("Invalid session user. Please sign in again.")

            if payment_type == 'In-Kind':
                estimated_value = (request.form.get('in_kind_estimated_value') or '').replace(',', '').strip()
                if estimated_value and not re.fullmatch(r'\d+', estimated_value):
                    raise ValueError("Estimated value must contain numbers only.")
                amount = float(estimated_value) if estimated_value else 0.0
                in_kind_description = request.form.get('in_kind_description', '').strip()
                in_kind_quantity = request.form.get('in_kind_quantity', '').strip()
                if not re.fullmatch(r'[A-Za-z0-9 ]+', in_kind_description):
                    raise ValueError("In-kind description must contain letters, numbers, and spaces only.")
                if not re.fullmatch(r'\d+', in_kind_quantity):
                    raise ValueError("Quantity must contain numbers only.")
                in_kind_note = f"In-Kind Donation - {in_kind_description} | Quantity: {in_kind_quantity}"
                notes = f"{in_kind_note}\n{notes}".strip() if notes else in_kind_note
            else:
                raw_amount = (request.form.get('amount') or '0').replace(',', '').strip()
                amount = float(raw_amount)

            actor_display = session.get('username') or session.get('email') or 'Treasurer'
            workflow_note = (
                f"[WORKFLOW] Directly recorded by Treasurer {actor_display} "
                f"on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
            if contact_number:
                notes = f"[CONTACT] {contact_number}\n{notes}".strip() if notes else f"[CONTACT] {contact_number}"
            notes = f"{notes}\n{workflow_note}".strip() if notes else workflow_note

            ref_num = generate_reference_number()
            notes_payload = {
                'donor_id': recorder_user_id,
                'donor_name': donor_name or 'Anonymous',
                'receiver': "Treasurer's Office",
                'paymethod': payment_type,
                'amount': amount,
                'fund_id': fund_id,
                'reference': ref_num,
                'entry_mode': 'in_person_treasurer',
                'timestamp': datetime.now().isoformat()
            }
            if contact_number:
                notes_payload['contact_number'] = contact_number
            secure_notes = build_secure_donation_notes(notes_payload, notes)

            cursor.execute("""
                INSERT INTO donations (
                    fund_id, don_donorid, don_donorname, don_receiver,
                    don_paymethod, don_amount, don_refnum, don_status,
                    don_date, don_notes
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                fund_id,
                recorder_user_id,
                donor_name or 'Anonymous',
                "Treasurer's Office",
                payment_type,
                amount,
                ref_num,
                'Paid',
                donation_date,
                secure_notes
            ))

            donation_id = cursor.lastrowid
            log_audit_event(
                action='CASH_DONATION_RECEIVED',
                entity_type='donation',
                entity_id=ref_num,
                after_data={
                    'don_id': donation_id,
                    'don_refnum': ref_num,
                    'don_status': 'Paid',
                    'don_paymethod': payment_type,
                    'don_amount': amount,
                    'fund_id': fund_id
                },
                metadata={
                    'source': 'treasurer_cash_entry',
                    'entry_mode': 'direct_treasurer_recording'
                },
                conn=conn,
                cursor=cursor
            )
            record_donation_fund_status_update(
                cursor=cursor,
                reference_number=ref_num,
                donation_id=donation_id,
                new_status='Donation Received',
                previous_status=None,
                updated_by=session.get('user_id'),
                audit_id=None,
                note='Treasurer recorded in-person donation'
            )
            record_donation_fund_status_update(
                cursor=cursor,
                reference_number=ref_num,
                donation_id=donation_id,
                new_status='Payment Confirmed',
                previous_status='Donation Received',
                updated_by=session.get('user_id'),
                audit_id=None,
                note='Treasurer recorded paid in-person donation'
            )

            blockchain_recorded = record_donation_on_blockchain(
                ref_num,
                donation_data={
                    'fund_id': fund_id,
                    'blockchain_fund_id': None,
                    'don_amount': amount,
                    'donor_wallet_address': None
                },
                conn=conn,
                cursor=cursor
            )
            if not blockchain_recorded:
                raise ValueError("Donation was not saved because blockchain recording failed.")
            conn.commit()
            email_sent, email_error = send_fund_creator_donation_email(ref_num)
            if not email_sent:
                print(f"Donation creator email not sent for {ref_num}: {email_error}")
            check_and_update_fundraiser_status(ref_num)

            return redirect(url_for('treasurer_cash_receipt_by_ref', refnum=ref_num))

        except Exception as e:
            if conn:
                conn.rollback()
            print(f"Error recording treasurer in-person donation: {e}")
            try:
                error_conn = get_db_connection()
                error_cursor = error_conn.cursor(dictionary=True)
                error_cursor.execute("""
                    SELECT fund_id, fund_title, fund_status
                    FROM fundraisers
                    WHERE LOWER(COALESCE(fund_status, '')) = 'active'
                    ORDER BY fund_title
                """)
                fundraisers = error_cursor.fetchall()
            except Exception:
                fundraisers = []
            finally:
                if 'error_cursor' in locals() and error_cursor:
                    error_cursor.close()
                if 'error_conn' in locals() and error_conn:
                    error_conn.close()
            return render_template(
                'treasurer_cash_entry.html',
                fundraisers=fundraisers,
                error=f"Error recording donation: {str(e)}"
            ), 400
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT fund_id, fund_title, fund_status
            FROM fundraisers
            WHERE LOWER(COALESCE(fund_status, '')) = 'active'
            ORDER BY fund_title
        """)
        fundraisers = cursor.fetchall()

        return render_template('treasurer_cash_entry.html', fundraisers=fundraisers)
    except Exception as e:
        print(f"Error loading treasurer cash entry form: {e}")
        return "Error loading form", 500
    finally:
        cursor.close()
        conn.close()

@app.route('/treasurer/cash-donations/receipt/<int:donation_id>')
def treasurer_cash_receipt(donation_id):
    if 'email' not in session or session.get('role') != 'Treasurer':
        return redirect(url_for('goto_signin'))
    
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    
    try:
        cursor.execute("""
            SELECT d.*, f.fund_title, f.fund_id
            FROM donations d
            LEFT JOIN fundraisers f ON d.fund_id = f.fund_id
            WHERE d.don_id = %s AND d.don_paymethod IN ('Cash', 'Cheque', 'In-Kind')
        """, (donation_id,))
        donation = cursor.fetchone()
        
        if not donation:
            return "Donation not found", 404

        donation['don_notes'] = extract_display_notes(donation.get('don_notes'))
        
        return render_template('treasurer_cash_receipt.html', donation=donation)
    finally:
        cursor.close()
        connection.close()

@app.route('/treasurer/cash-donations/receipt/ref/<refnum>')
def treasurer_cash_receipt_by_ref(refnum):
    if 'email' not in session or session.get('role') != 'Treasurer':
        return redirect(url_for('goto_signin'))

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT d.*, f.fund_title, f.fund_id
            FROM donations d
            LEFT JOIN fundraisers f ON d.fund_id = f.fund_id
            WHERE d.don_refnum = %s AND d.don_paymethod IN ('Cash', 'Cheque', 'In-Kind')
            ORDER BY d.don_id DESC
            LIMIT 1
        """, (refnum,))
        donation = cursor.fetchone()

        if not donation:
            return "Donation not found", 404

        donation['don_notes'] = extract_display_notes(donation.get('don_notes'))

        return render_template('treasurer_cash_receipt.html', donation=donation)
    finally:
        cursor.close()
        connection.close()

@app.route('/api/treasurer/confirm-cash-donation', methods=['POST'])
def treasurer_confirm_cash_donation():
    if 'email' not in session or session.get('role') != 'Treasurer':
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json(silent=True) or {}
    donation_id = data.get('donation_id')
    donation_refnum = (data.get('don_refnum') or '').strip()
    try:
        donation_id = int(donation_id)
    except (TypeError, ValueError):
        donation_id = None

    if donation_id is None and not donation_refnum:
        return jsonify({'error': 'Invalid donation reference'}), 400

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        if donation_refnum:
            cursor.execute("""
                SELECT don_id, don_refnum, don_status, don_paymethod, don_notes, don_amount, fund_id, don_donorid
                FROM donations
                WHERE don_refnum = %s
                ORDER BY don_id DESC
                LIMIT 1
            """, (donation_refnum,))
        else:
            cursor.execute("""
                SELECT don_id, don_refnum, don_status, don_paymethod, don_notes, don_amount, fund_id, don_donorid
                FROM donations
                WHERE don_id = %s
                LIMIT 1
            """, (donation_id,))
        donation = cursor.fetchone()

        if not donation:
            return jsonify({'error': 'Donation not found'}), 404

        if donation_id is not None and donation['don_id'] != donation_id:
            return jsonify({'error': 'Donation changed. Please refresh and try again.'}), 409

        if donation['don_paymethod'] not in ('Cash', 'Cheque', 'In-Kind'):
            return jsonify({'error': 'Only in-person donations can be confirmed from this workflow'}), 400

        current_status = (donation.get('don_status') or '').strip().lower()
        if current_status != 'endorsed':
            return jsonify({'error': 'Only Endorsed donations can be confirmed by Treasurer'}), 400

        actor_display = session.get('username') or session.get('email') or 'Treasurer'
        workflow_note = (
            f"[WORKFLOW] Treasurer confirmed receipt by {actor_display} "
            f"on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        updated_notes = append_workflow_note(donation.get('don_notes'), workflow_note)

        cursor.execute("""
            UPDATE donations
            SET don_status = %s, don_notes = %s, don_receiver = %s
            WHERE don_id = %s AND LOWER(TRIM(don_status)) = 'endorsed'
        """, ('Paid', updated_notes, "Treasurer's Office", donation['don_id']))

        if cursor.rowcount <= 0:
            conn.rollback()
            return jsonify({'error': 'Donation status changed. Please refresh and try again.'}), 409

        log_audit_event(
            action='CASH_DONATION_CONFIRMED',
            entity_type='donation',
            entity_id=donation['don_id'],
            before_data={
                'don_id': donation['don_id'],
                'don_refnum': donation['don_refnum'],
                'don_status': donation['don_status'],
                'don_amount': float(donation['don_amount']) if donation['don_amount'] is not None else None,
                'fund_id': donation['fund_id'],
                'don_donorid': donation['don_donorid']
            },
            after_data={
                'don_id': donation['don_id'],
                'don_status': 'Paid',
                'workflow_note': workflow_note,
                'action_datetime': datetime.now()
            },
            metadata={'source': 'treasurer_confirm_cash_donation'},
            conn=conn,
            cursor=cursor
        )

        blockchain_recorded = record_donation_on_blockchain(
            donation['don_refnum'],
            donation_data={
                'fund_id': donation['fund_id'],
                'blockchain_fund_id': None,
                'don_amount': donation['don_amount'],
                'donor_wallet_address': None
            },
            conn=conn,
            cursor=cursor
        )

        conn.commit()
        email_sent, email_error = send_fund_creator_donation_email(donation['don_refnum'])
        if not email_sent:
            print(f"Donation creator email not sent for {donation['don_refnum']}: {email_error}")
        check_and_update_fundraiser_status(donation['don_refnum'])
        if blockchain_recorded:
            return jsonify({
                'success': True,
                'donation_id': donation['don_id'],
                'message': (
                    f"Donation {donation['don_refnum']} confirmed, officially recorded, "
                    "and anchored on blockchain."
                ),
                'blockchain_recorded': True
            })

        return jsonify({
            'success': True,
            'donation_id': donation['don_id'],
            'message': (
                f"Donation {donation['don_refnum']} confirmed and marked as paid. "
                "Blockchain anchoring failed and can be retried later."
            ),
            'blockchain_recorded': False
        })
    except Exception as e:
        conn.rollback()
        print(f"Error confirming cash donation: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/api/treasurer/update-donation-status', methods=['POST'])
def treasurer_update_donation_status():
    if 'email' not in session or session.get('role') != 'Treasurer':
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        data = request.get_json()
        reference_number = (data.get('reference_number') or data.get('don_refnum') or '').strip()
        new_status = data.get('status')
        
        if not reference_number or not new_status:
            return jsonify({'error': 'Missing reference_number or status'}), 400
        
        valid_statuses = ['Pending', 'Paid', 'Failed', 'Cancelled', 'Endorsed']
        if new_status not in valid_statuses:
            return jsonify({'error': f'Invalid status. Must be one of: {valid_statuses}'}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT don_id, don_refnum, don_status, don_amount, fund_id, don_donorid, don_paymethod
            FROM donations
            WHERE don_refnum = %s
            LIMIT 1
        """, (reference_number,))
        current_donation = cursor.fetchone()

        if not current_donation:
            cursor.close()
            conn.close()
            return jsonify({'error': 'Donation not found'}), 404

        donation_id = current_donation[0]

        if current_donation and current_donation[6] in ('Cash', 'Cheque', 'In-Kind'):
            cursor.close()
            conn.close()
            return jsonify({
                'error': 'In-person donations require Admin endorsement then Treasurer confirmation in the In-Person Donations page.'
            }), 400
        
        cursor.execute("""
            UPDATE donations 
            SET don_status = %s
            WHERE don_refnum = %s
        """, (new_status, reference_number))
        
        rows_affected = cursor.rowcount
        if rows_affected > 0:
            log_audit_event(
                action='DONATION_STATUS_UPDATED',
                entity_type='donation',
                entity_id=current_donation[1],
                before_data={
                    'don_id': current_donation[0] if current_donation else donation_id,
                    'don_refnum': current_donation[1] if current_donation else None,
                    'don_status': current_donation[2] if current_donation else None,
                    'don_amount': float(current_donation[3]) if current_donation and current_donation[3] is not None else None,
                    'fund_id': current_donation[4] if current_donation else None,
                    'don_donorid': current_donation[5] if current_donation else None,
                    'don_paymethod': current_donation[6] if current_donation else None
                },
                after_data={
                    'don_id': donation_id,
                    'don_refnum': current_donation[1],
                    'don_status': new_status,
                    'action_datetime': datetime.now()
                },
                metadata={'source': 'treasurer_update_donation_status'},
                conn=conn,
                cursor=cursor
            )
            if new_status == 'Paid':
                log_audit_event(
                    action='DONATION_PAYMENT_CONFIRMED',
                    entity_type='donation',
                    entity_id=current_donation[1],
                    after_data={
                        'don_id': donation_id,
                        'don_refnum': current_donation[1],
                        'don_status': new_status,
                        'action_datetime': datetime.now()
                    },
                    metadata={'source': 'treasurer_update_donation_status'},
                    conn=conn,
                    cursor=cursor
                )
                cursor.execute("""
                    SELECT current_status
                    FROM donation_fund_status
                    WHERE reference_number = %s
                    LIMIT 1
                """, (current_donation[1],))
                fund_status_row = cursor.fetchone()
                fund_current_status = fund_status_row[0] if fund_status_row else 'Donation Received'
                if fund_current_status == 'Donation Received':
                    record_donation_fund_status_update(
                        cursor=cursor,
                        reference_number=current_donation[1],
                        donation_id=donation_id,
                        new_status='Payment Confirmed',
                        previous_status='Donation Received',
                        updated_by=session.get('user_id'),
                        audit_id=None,
                        note='Payment confirmed by Treasurer'
                    )
        conn.commit()
        cursor.close()
        conn.close()
        
        if rows_affected > 0:
            if new_status == 'Paid' and current_donation:
                email_sent, email_error = send_fund_creator_donation_email(current_donation[1])
                if not email_sent:
                    print(f"Donation creator email not sent for {current_donation[1]}: {email_error}")
                check_and_update_fundraiser_status(current_donation[1])
            return jsonify({'success': True, 'message': f'Donation status updated to {new_status}'})
        else:
            return jsonify({'error': 'Donation not found'}), 404
            
    except Exception as e:
        print(f"Error updating donation status: {e}")
        return jsonify({'error': str(e)}), 500


# -----------------------------------------------------------------------
# -------------------------------- MSWDO --------------------------------
# -----------------------------------------------------------------------

# @app.route('/mswdo/dashboard')
# def mswdo_dashboard():
#     """MSWDO Dashboard - Central authority overview"""
#     if 'email' not in session:
#         return redirect(url_for('goto_signin'))
    
#     conn = get_db_connection()
#     cursor = conn.cursor(dictionary=True)
#     cursor.execute("SELECT role FROM users WHERE email = %s", (session['email'],))
#     user = cursor.fetchone()
    
#     if not user or user['role'] != 'MSWDO':
#         return "Access denied. MSWDO role required.", 403
    
#     cursor.execute("""
#         SELECT 
#             COALESCE(SUM(don_amount), 0) as total_donations,
#             COUNT(CASE WHEN don_status = 'Paid' THEN 1 END) as active_beneficiaries,
#             COUNT(CASE WHEN don_status = 'Pending' THEN 1 END) as pending_relief,
#             ROUND(COUNT(CASE WHEN don_status = 'Paid' THEN 1 END) * 100.0 / COUNT(*), 1) as relief_efficiency
#         FROM donations
#     """)
#     stats = cursor.fetchone()
    
#     cursor.close()
#     conn.close()
    
#     return render_template('mswdo_dashboard.html',
#                             total_donations=stats['total_donations'],
#                             active_beneficiaries=stats['active_beneficiaries'],
#                             pending_relief=stats['pending_relief'],
#                             relief_efficiency=stats['relief_efficiency'] or 0)

# @app.route('/mswdo/donations')
# def mswdo_donations():
#     """MSWDO Donation Management"""
#     if 'email' not in session:
#         return redirect(url_for('goto_signin'))
    
#     conn = get_db_connection()
#     cursor = conn.cursor(dictionary=True)
#     cursor.execute("SELECT role FROM users WHERE email = %s", (session['email'],))
#     user = cursor.fetchone()
    
#     if not user or user['role'] != 'MSWDO':
#         return "Access denied. MSWDO role required.", 403
    
#     cursor.execute("""
#         SELECT 
#             COALESCE(SUM(don_amount), 0) as total_received,
#             COUNT(CASE WHEN don_status = 'Pending' THEN 1 END) as pending_count,
#             COUNT(CASE WHEN DATE(don_date) = CURDATE() AND don_status = 'Paid' THEN 1 END) as processed_today,
#             ROUND(COUNT(CASE WHEN don_status = 'Paid' THEN 1 END) * 100.0 / COUNT(*), 1) as allocation_rate
#         FROM donations
#     """)
#     stats = cursor.fetchone()
    
#     cursor.execute("""
#         SELECT d.*, f.fund_title, f.fund_category
#         FROM donations d
#         LEFT JOIN fundraisers f ON d.fund_id = f.fund_id
#         ORDER BY d.don_date DESC
#         LIMIT 50
#     """)
#     donations = cursor.fetchall()
    
#     for donation in donations:
#         donation['type'] = 'Cash'
#         donation['status'] = donation['don_status']
#         donation['amount'] = donation['don_amount']
#         donation['refnum'] = donation['don_refnum']
#         donation['donor_name'] = donation['don_donorname']
#         donation['donor_email'] = donation.get('donor_email', '')
#         donation['date'] = donation['don_date']
#         donation['fundraiser_title'] = donation['fund_title'] or 'N/A'
    
#     cursor.close()
#     conn.close()
    
#     return render_template('mswdo_donations.html',
#                             total_received=stats['total_received'],
#                             pending_count=stats['pending_count'],
#                             processed_today=stats['processed_today'],
#                             allocation_rate=stats['allocation_rate'] or 0,
#                             donations=donations)

# @app.route('/mswdo/beneficiaries')
# def mswdo_beneficiaries():
#     """MSWDO Beneficiary Management"""
#     if 'email' not in session:
#         return redirect(url_for('goto_signin'))
    
#     # Check if user has MSWDO role
#     conn = get_db_connection()
#     cursor = conn.cursor(dictionary=True)
#     cursor.execute("SELECT role FROM users WHERE email = %s", (session['email'],))
#     user = cursor.fetchone()
    
#     if not user or user['role'] != 'MSWDO':
#         return "Access denied. MSWDO role required.", 403
    
#     # Get beneficiary statistics (using mock data for now since beneficiaries table structure differs)
#     # TODO: Update when MSWDO beneficiaries table is properly implemented
#     stats = {
#         'total_beneficiaries': 125,
#         'pending_verification': 25,
#         'verified_today': 8,
#         'coverage_rate': 80.0
#     }
    
#     # Get beneficiaries (mock data for now)
#     beneficiaries = [
#         {
#             'id': 1,
#             'name': 'Juan Dela Cruz',
#             'contact': '+63 912 345 6789',
#             'family_size': 4,
#             'barangay': 'San Jose',
#             'assistance_type': 'Food',
#             'status': 'Verified',
#             'priority': 'High',
#             'date_registered': datetime.now()
#         },
#         {
#             'id': 2,
#             'name': 'Maria Santos',
#             'contact': '+63 923 456 7890',
#             'family_size': 6,
#             'barangay': 'Poblacion',
#             'assistance_type': 'Medical',
#             'status': 'Pending',
#             'priority': 'Critical',
#             'date_registered': datetime.now()
#         },
#         {
#             'id': 3,
#             'name': 'Pedro Garcia',
#             'contact': '+63 934 567 8901',
#             'family_size': 3,
#             'barangay': 'Santa Maria',
#             'assistance_type': 'Housing',
#             'status': 'Active',
#             'priority': 'Medium',
#             'date_registered': datetime.now()
#         }
#     ]
    
#     cursor.close()
#     conn.close()
    
#     return render_template('mswdo_beneficiaries.html',
#         total_beneficiaries=stats.get('total_beneficiaries', 0),
#         pending_verification=stats.get('pending_verification', 0),
#         verified_today=stats.get('verified_today', 0),
#         coverage_rate=stats.get('coverage_rate', 0),
#         beneficiaries=beneficiaries,
#         barangays=BARANGAYS)

# @app.route('/mswdo/reports')
# def mswdo_reports():
#     """MSWDO Reports & Analytics"""
#     if 'email' not in session:
#         return redirect(url_for('goto_signin'))
    
#     # Check if user has MSWDO role
#     conn = get_db_connection()
#     cursor = conn.cursor(dictionary=True)
#     cursor.execute("SELECT role FROM users WHERE email = %s", (session['email'],))
#     user = cursor.fetchone()
    
#     if not user or user['role'] != 'MSWDO':
#         return "Access denied. MSWDO role required.", 403
    
#     # Get comprehensive statistics
#     cursor.execute("""
#         SELECT 
#             COALESCE(SUM(don_amount), 0) as total_funds,
#             COUNT(DISTINCT don_donorid) as families_served,
#             AVG(TIMESTAMPDIFF(HOUR, don_date, NOW())) as response_time,
#             ROUND(COUNT(CASE WHEN don_status = 'Paid' THEN 1 END) * 100.0 / COUNT(*), 1) as efficiency_rate
#         FROM donations
#     """)
#     kpi_stats = cursor.fetchone()
    
#     # Financial breakdown
#     cursor.execute("""
#         SELECT 
#             COALESCE(SUM(don_amount), 0) as total_donations,
#             COALESCE(SUM(CASE WHEN don_paymethod = 'GCash' OR don_paymethod = 'Credit Card' THEN don_amount END), 0) as cash_donations,
#             COALESCE(SUM(CASE WHEN don_paymethod = 'In-Kind' THEN don_amount END), 0) as inkind_donations,
#             COALESCE(SUM(don_amount) * 0.8, 0) as allocated_funds,
#             COALESCE(SUM(don_amount) * 0.6, 0) as distributed_funds,
#             COALESCE(SUM(don_amount) * 0.2, 0) as remaining_funds
#         FROM donations
#         WHERE don_status = 'Paid'
#     """)
#     financial_stats = cursor.fetchone()
    
#     # Beneficiary statistics (using mock data for now since beneficiaries table structure differs)
#     # TODO: Update when MSWDO beneficiaries table is properly implemented
#     beneficiary_stats = {
#         'total_beneficiaries': 125,
#         'verified_beneficiaries': 100,
#         'pending_beneficiaries': 25,
#         'coverage_percentage': 80.0
#     }
    
#     cursor.close()
#     conn.close()
    
#     return render_template('mswdo_reports.html',
#         # KPI data
#         total_funds=kpi_stats['total_funds'],
#         families_served=kpi_stats['families_served'] or 0,
#         response_time=round(kpi_stats['response_time'] or 0, 1),
#         efficiency_rate=kpi_stats['efficiency_rate'] or 0,
        
#         # Financial data
#         total_donations=financial_stats['total_donations'],
#         cash_donations=financial_stats['cash_donations'],
#         inkind_donations=financial_stats['inkind_donations'],
#         allocated_funds=financial_stats['allocated_funds'],
#         food_allocation=float(financial_stats['allocated_funds'] or 0) * 0.5,
#         medical_allocation=float(financial_stats['allocated_funds'] or 0) * 0.3,
#         distributed_funds=financial_stats['distributed_funds'],
#         remaining_funds=financial_stats['remaining_funds'],
        
#         # Beneficiary data
#         total_beneficiaries=beneficiary_stats.get('total_beneficiaries', 0),
#         verified_beneficiaries=beneficiary_stats.get('verified_beneficiaries', 0),
#         pending_beneficiaries=beneficiary_stats.get('pending_beneficiaries', 0),
#         coverage_percentage=beneficiary_stats.get('coverage_percentage', 0),
        
#         # Mock data for breakdowns
#         san_jose_count=35,
#         poblacion_count=28,
#         santa_maria_count=37,
        
#         # Transparency data
#         public_donations=float(financial_stats['total_donations'] or 0) * 0.7,
#         anonymous_donations=float(financial_stats['total_donations'] or 0) * 0.2,
#         corporate_donations=float(financial_stats['total_donations'] or 0) * 0.1,
        
#         # Barangays list
#         barangays=BARANGAYS
#     )

# # -----------------------------------------------------------------------
# # ----------------------------- BENEFICIARIES ---------------------------
# # -----------------------------------------------------------------------

# def check_fundraiser_ownership(fundraiser_id):
#     """Check if current user is the owner of the fundraiser or is Admin/Treasurer"""
#     if 'email' not in session:
#         return False, None
    
#     conn = get_db_connection()
#     cursor = conn.cursor(dictionary=True)
    
#     try:
#         cursor.execute("SELECT fund_creatorid FROM fundraisers WHERE fund_id = %s", (fundraiser_id,))
#         fundraiser = cursor.fetchone()
        
#         if not fundraiser:
#             return False, None
        
#         cursor.execute("SELECT id, role FROM users WHERE email = %s", (session['email'],))
#         user = cursor.fetchone()
        
#         if not user:
#             return False, None
        
#         is_owner = fundraiser['fund_creatorid'] == user['id']
#         is_admin = user['role'] in ['Admin', 'Treasurer']
        
#         return (is_owner or is_admin), user
#     finally:
#         cursor.close()
#         conn.close()

# BARANGAYS = [
#     'Aplaya', 'Bagong Pook', 'Bukal', 'Bulilan Norte (Poblacion)',
#     'Bulilan Sur (Poblacion)', 'Concepcion', 'Labuin', 'Linga', 'Masico',
#     'Mojon', 'Pansol', 'Pinagbayanan', 'San Antonio', 'San Miguel',
#     'Santa Clara Norte (Poblacion)', 'Santa Clara Sur (Poblacion)', 'Tubuan'
# ]

# @app.route('/api/barangays', methods=['GET'])
# def get_barangays():
#     return jsonify({'success': True, 'barangays': BARANGAYS})

# @app.route('/api/beneficiaries/<int:fundraiser_id>', methods=['GET'])
# def get_beneficiaries(fundraiser_id):
#     is_authorized, user = check_fundraiser_ownership(fundraiser_id)
#     if not is_authorized:
#         return jsonify({'error': 'Unauthorized'}), 401
    
#     conn = get_db_connection()
#     cursor = conn.cursor(dictionary=True)
    
#     try:
#         cursor.execute("""
#             SELECT * FROM beneficiaries 
#             WHERE fund_id = %s 
#             ORDER BY date_added ASC
#         """, (fundraiser_id,))
#         beneficiaries = cursor.fetchall()
        
#         return jsonify({'success': True, 'beneficiaries': beneficiaries})
#     except mysql.connector.Error as e:
#         print(f"Error fetching beneficiaries: {e}")
#         return jsonify({'success': False, 'error': 'Database error'}), 500
#     except Exception as e:
#         return jsonify({'error': str(e)}), 500
#     finally:
#         cursor.close()
#         conn.close()

# @app.route('/api/beneficiaries', methods=['POST'])
# def add_beneficiary():
#     try:
#         data = request.get_json()
#         fund_id = data.get('fund_id')
#         beneficiary_name = data.get('beneficiary_name')
#         beneficiary_contact = data.get('beneficiary_contact')
#         beneficiary_address = data.get('beneficiary_address')
#         beneficiary_age = data.get('beneficiary_age')
#         beneficiary_gender = data.get('beneficiary_gender')
        
#         if not fund_id or not beneficiary_name:
#             return jsonify({'error': 'Fund ID and beneficiary name are required'}), 400
        
#         is_authorized, user = check_fundraiser_ownership(fund_id)
#         if not is_authorized:
#             return jsonify({'error': 'Unauthorized'}), 401
        
#         conn = get_db_connection()
#         cursor = conn.cursor()
        
#         cursor.execute("""
#             INSERT INTO beneficiaries 
#             (fund_id, beneficiary_name, beneficiary_contact, 
#             beneficiary_address, beneficiary_age, beneficiary_gender)
#             VALUES (%s, %s, %s, %s, %s, %s)
#         """, (fund_id, beneficiary_name, beneficiary_contact,
#             beneficiary_address, beneficiary_age, beneficiary_gender))
        
#         beneficiary_id = cursor.lastrowid
#         log_audit_event(
#             action='BENEFICIARY_CREATED',
#             entity_type='beneficiary',
#             entity_id=beneficiary_id,
#             after_data={
#                 'beneficiary_id': beneficiary_id,
#                 'fund_id': fund_id,
#                 'beneficiary_name': beneficiary_name,
#                 'beneficiary_contact': beneficiary_contact,
#                 'beneficiary_address': beneficiary_address,
#                 'beneficiary_age': beneficiary_age,
#                 'beneficiary_gender': beneficiary_gender
#             },
#             conn=conn,
#             cursor=cursor
#         )
#         conn.commit()
        
#         cursor.close()
#         conn.close()
        
#         return jsonify({
#             'success': True, 
#             'message': 'Beneficiary added successfully',
#             'beneficiary_id': beneficiary_id
#         })
        
#     except Exception as e:
#         return jsonify({'error': str(e)}), 500

# @app.route('/api/beneficiaries/<int:beneficiary_id>', methods=['PUT'])
# def update_beneficiary(beneficiary_id):
#     try:
#         data = request.get_json()
        
#         conn = get_db_connection()
#         cursor = conn.cursor(dictionary=True)
        
#         # Get beneficiary snapshot and fundraiser ownership reference
#         cursor.execute("""
#             SELECT beneficiary_id, fund_id, beneficiary_name, beneficiary_contact,
#                 beneficiary_address, beneficiary_age, beneficiary_gender, is_verified, verification_notes
#             FROM beneficiaries
#             WHERE beneficiary_id = %s
#         """, (beneficiary_id,))
#         beneficiary = cursor.fetchone()
        
#         if not beneficiary:
#             cursor.close()
#             conn.close()
#             return jsonify({'error': 'Beneficiary not found'}), 404
        
#         is_authorized, user = check_fundraiser_ownership(beneficiary['fund_id'])
#         if not is_authorized:
#             cursor.close()
#             conn.close()
#             return jsonify({'error': 'Unauthorized'}), 401
        
#         before_snapshot = dict(beneficiary)
#         cursor = conn.cursor()
        
#         update_fields = []
#         values = []
        
#         for field in ['beneficiary_name', 'beneficiary_contact',
#                     'beneficiary_address', 'beneficiary_age', 'beneficiary_gender']:
#             if field in data:
#                 update_fields.append(f"{field} = %s")
#                 values.append(data[field])
        
#         if not update_fields:
#             return jsonify({'error': 'No fields to update'}), 400
        
#         # Add date_updated
#         update_fields.append("date_updated = NOW()")
#         values.append(beneficiary_id)
        
#         cursor.execute(f"""
#             UPDATE beneficiaries 
#             SET {', '.join(update_fields)}
#             WHERE beneficiary_id = %s
#         """, values)
#         after_snapshot = dict(before_snapshot)
#         for field in ['beneficiary_name', 'beneficiary_contact', 'beneficiary_address', 'beneficiary_age', 'beneficiary_gender']:
#             if field in data:
#                 after_snapshot[field] = data[field]
#         log_audit_event(
#             action='BENEFICIARY_UPDATED',
#             entity_type='beneficiary',
#             entity_id=beneficiary_id,
#             before_data=before_snapshot,
#             after_data=after_snapshot,
#             conn=conn,
#             cursor=cursor
#         )
#         conn.commit()
#         cursor.close()
#         conn.close()
        
#         return jsonify({'success': True, 'message': 'Beneficiary updated successfully'})
        
#     except Exception as e:
#         return jsonify({'error': str(e)}), 500

# @app.route('/api/beneficiaries/<int:beneficiary_id>', methods=['DELETE'])
# def delete_beneficiary(beneficiary_id):
#     try:
#         conn = get_db_connection()
#         cursor = conn.cursor(dictionary=True)
        
#         # Get beneficiary snapshot and fundraiser ownership reference
#         cursor.execute("""
#             SELECT beneficiary_id, fund_id, beneficiary_name, beneficiary_contact,
#                 beneficiary_address, beneficiary_age, beneficiary_gender, is_verified, verification_notes
#             FROM beneficiaries
#             WHERE beneficiary_id = %s
#         """, (beneficiary_id,))
#         beneficiary = cursor.fetchone()
        
#         if not beneficiary:
#             cursor.close()
#             conn.close()
#             return jsonify({'error': 'Beneficiary not found'}), 404
        
#         is_authorized, user = check_fundraiser_ownership(beneficiary['fund_id'])
#         if not is_authorized:
#             cursor.close()
#             conn.close()
#             return jsonify({'error': 'Unauthorized'}), 401
        
#         cursor = conn.cursor()
#         cursor.execute("DELETE FROM beneficiaries WHERE beneficiary_id = %s", (beneficiary_id,))
        
#         if cursor.rowcount == 0:
#             return jsonify({'error': 'Beneficiary not found'}), 404
#         log_audit_event(
#             action='BENEFICIARY_DELETED',
#             entity_type='beneficiary',
#             entity_id=beneficiary_id,
#             before_data=beneficiary,
#             after_data={'deleted': True},
#             conn=conn,
#             cursor=cursor
#         )
#         conn.commit()
#         cursor.close()
#         conn.close()
        
#         return jsonify({'success': True, 'message': 'Beneficiary deleted successfully'})
        
#     except Exception as e:
#         return jsonify({'error': str(e)}), 500

# @app.route('/api/beneficiaries/<int:beneficiary_id>/verify', methods=['POST'])
# def verify_beneficiary(beneficiary_id):
#     if 'email' not in session or session.get('role') not in ['Admin', 'Treasurer']:
#         return jsonify({'error': 'Unauthorized'}), 401
    
#     try:
#         data = request.get_json()
#         is_verified = data.get('is_verified', True)
#         verification_notes = data.get('verification_notes', '')
        
#         conn = get_db_connection()
#         cursor = conn.cursor()
        
#         cursor.execute("""
#             UPDATE beneficiaries 
#             SET is_verified = %s, verification_notes = %s
#             WHERE beneficiary_id = %s
#         """, (is_verified, verification_notes, beneficiary_id))
#         log_audit_event(
#             action='BENEFICIARY_VERIFIED',
#             entity_type='beneficiary',
#             entity_id=beneficiary_id,
#             after_data={
#                 'is_verified': bool(is_verified),
#                 'verification_notes': verification_notes
#             },
#             conn=conn,
#             cursor=cursor
#         )
#         conn.commit()
#         cursor.close()
#         conn.close()
        
#         return jsonify({'success': True, 'message': 'Beneficiary verification updated'})
        
#     except Exception as e:
#         return jsonify({'error': str(e)}), 500


def _get_table_columns(cursor, table_name):
    """Fetch available column names for a table in current schema."""
    cursor.execute("""
        SELECT COLUMN_NAME
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s
    """, (table_name,))
    rows = cursor.fetchall() or []
    columns = set()
    for row in rows:
        if isinstance(row, dict):
            columns.add(row.get('COLUMN_NAME'))
        else:
            columns.add(row[0])
    return columns

BARANGAYS = [
    'Aplaya', 'Bagong Pook', 'Bukal', 'Bulilan Norte (Poblacion)',
    'Bulilan Sur (Poblacion)', 'Concepcion', 'Labuin', 'Linga', 'Masico',
    'Mojon', 'Pansol', 'Pinagbayanan', 'San Antonio', 'San Miguel',
    'Santa Clara Norte (Poblacion)', 'Santa Clara Sur (Poblacion)', 'Tubuan'
]

@app.route('/api/barangays', methods=['GET'])
def get_barangays():
    return jsonify({'success': True, 'barangays': BARANGAYS})

def check_fundraiser_ownership(fundraiser_id):
    """Allow fundraiser owner, Admin, or Treasurer to manage beneficiaries."""
    if 'email' not in session:
        return False, None

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT fund_creatorid FROM fundraisers WHERE fund_id = %s", (fundraiser_id,))
        fundraiser = cursor.fetchone()
        if not fundraiser:
            return False, None

        cursor.execute("SELECT id, role FROM users WHERE email = %s", (session['email'],))
        user = cursor.fetchone()
        if not user:
            return False, None

        is_owner = fundraiser['fund_creatorid'] == user['id']
        is_admin_side = user['role'] in ['Admin', 'Treasurer']
        return (is_owner or is_admin_side), user
    finally:
        cursor.close()
        conn.close()

@app.route('/api/beneficiaries/<int:fundraiser_id>', methods=['GET'])
def get_beneficiaries(fundraiser_id):
    is_authorized, user = check_fundraiser_ownership(fundraiser_id)
    if not is_authorized:
        return jsonify({'error': 'Unauthorized'}), 401

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        table_cols = _get_table_columns(cursor, 'beneficiaries')
        order_col = 'date_added' if 'date_added' in table_cols else 'beneficiary_id'
        cursor.execute(f"""
            SELECT * FROM beneficiaries
            WHERE fund_id = %s
            ORDER BY {order_col} ASC
        """, (fundraiser_id,))
        beneficiaries = cursor.fetchall()
        return jsonify({'success': True, 'beneficiaries': beneficiaries})
    except Exception as e:
        print(f"Error fetching beneficiaries: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/api/beneficiaries', methods=['POST'])
def add_beneficiary():
    try:
        data = request.get_json() or {}
        fund_id = data.get('fund_id')
        beneficiary_name = data.get('beneficiary_name')

        if not fund_id or not beneficiary_name:
            return jsonify({'error': 'Fund ID and beneficiary name are required'}), 400

        is_authorized, user = check_fundraiser_ownership(fund_id)
        if not is_authorized:
            return jsonify({'error': 'Unauthorized'}), 401

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        table_cols = _get_table_columns(cursor, 'beneficiaries')

        data_map = {
            'fund_id': fund_id,
            'beneficiary_name': beneficiary_name,
            'beneficiary_contact': data.get('beneficiary_contact'),
            'beneficiary_relationship': data.get('beneficiary_relationship'),
            'beneficiary_address': data.get('beneficiary_address'),
            'beneficiary_age': data.get('beneficiary_age'),
            'beneficiary_gender': data.get('beneficiary_gender'),
            'beneficiary_condition': data.get('beneficiary_condition'),
            'beneficiary_priority': data.get('beneficiary_priority')
        }
        insert_columns = [col for col in data_map.keys() if col in table_cols]
        if 'fund_id' not in insert_columns or 'beneficiary_name' not in insert_columns:
            cursor.close()
            conn.close()
            return jsonify({'error': 'Beneficiaries table schema is incompatible.'}), 500

        placeholders = ", ".join(["%s"] * len(insert_columns))
        columns_sql = ", ".join(insert_columns)
        values = [data_map[col] for col in insert_columns]

        cursor = conn.cursor()
        cursor.execute(
            f"INSERT INTO beneficiaries ({columns_sql}) VALUES ({placeholders})",
            values
        )
        beneficiary_id = cursor.lastrowid

        log_audit_event(
            action='BENEFICIARY_CREATED',
            entity_type='beneficiary',
            entity_id=beneficiary_id,
            after_data={'beneficiary_id': beneficiary_id, **{k: v for k, v in data_map.items() if k in insert_columns}},
            conn=conn,
            cursor=cursor
        )

        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({'success': True, 'message': 'Beneficiary added successfully', 'beneficiary_id': beneficiary_id})
    except Exception as e:
        print(f"Error adding beneficiary: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/beneficiaries/<int:beneficiary_id>', methods=['PUT'])
def update_beneficiary(beneficiary_id):
    try:
        data = request.get_json() or {}

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM beneficiaries WHERE beneficiary_id = %s", (beneficiary_id,))
        beneficiary = cursor.fetchone()

        if not beneficiary:
            cursor.close()
            conn.close()
            return jsonify({'error': 'Beneficiary not found'}), 404

        is_authorized, user = check_fundraiser_ownership(beneficiary['fund_id'])
        if not is_authorized:
            cursor.close()
            conn.close()
            return jsonify({'error': 'Unauthorized'}), 401

        table_cols = _get_table_columns(cursor, 'beneficiaries')
        field_map = {
            'beneficiary_name': data.get('beneficiary_name'),
            'beneficiary_contact': data.get('beneficiary_contact'),
            'beneficiary_relationship': data.get('beneficiary_relationship'),
            'beneficiary_address': data.get('beneficiary_address'),
            'beneficiary_age': data.get('beneficiary_age'),
            'beneficiary_gender': data.get('beneficiary_gender'),
            'beneficiary_condition': data.get('beneficiary_condition'),
            'beneficiary_priority': data.get('beneficiary_priority')
        }

        update_fields = []
        values = []
        for field, value in field_map.items():
            if field in data and field in table_cols:
                update_fields.append(f"{field} = %s")
                values.append(value)

        if not update_fields:
            cursor.close()
            conn.close()
            return jsonify({'error': 'No fields to update'}), 400

        if 'date_updated' in table_cols:
            update_fields.append("date_updated = NOW()")

        values.append(beneficiary_id)
        before_snapshot = dict(beneficiary)
        after_snapshot = dict(beneficiary)
        for field, value in field_map.items():
            if field in data and field in table_cols:
                after_snapshot[field] = value

        cursor = conn.cursor()
        cursor.execute(f"""
            UPDATE beneficiaries
            SET {', '.join(update_fields)}
            WHERE beneficiary_id = %s
        """, values)

        log_audit_event(
            action='BENEFICIARY_UPDATED',
            entity_type='beneficiary',
            entity_id=beneficiary_id,
            before_data=before_snapshot,
            after_data=after_snapshot,
            conn=conn,
            cursor=cursor
        )

        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({'success': True, 'message': 'Beneficiary updated successfully'})
    except Exception as e:
        print(f"Error updating beneficiary: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/beneficiaries/<int:beneficiary_id>', methods=['DELETE'])
def delete_beneficiary(beneficiary_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM beneficiaries WHERE beneficiary_id = %s", (beneficiary_id,))
        beneficiary = cursor.fetchone()

        if not beneficiary:
            cursor.close()
            conn.close()
            return jsonify({'error': 'Beneficiary not found'}), 404

        is_authorized, user = check_fundraiser_ownership(beneficiary['fund_id'])
        if not is_authorized:
            cursor.close()
            conn.close()
            return jsonify({'error': 'Unauthorized'}), 401

        cursor = conn.cursor()
        cursor.execute("DELETE FROM beneficiaries WHERE beneficiary_id = %s", (beneficiary_id,))
        if cursor.rowcount == 0:
            cursor.close()
            conn.close()
            return jsonify({'error': 'Beneficiary not found'}), 404

        log_audit_event(
            action='BENEFICIARY_DELETED',
            entity_type='beneficiary',
            entity_id=beneficiary_id,
            before_data=beneficiary,
            after_data={'deleted': True},
            conn=conn,
            cursor=cursor
        )

        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({'success': True, 'message': 'Beneficiary deleted successfully'})
    except Exception as e:
        print(f"Error deleting beneficiary: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/beneficiaries/<int:beneficiary_id>/verify', methods=['POST'])
def verify_beneficiary(beneficiary_id):
    if 'email' not in session or session.get('role') not in ['Admin', 'Treasurer']:
        return jsonify({'error': 'Unauthorized'}), 401

    try:
        data = request.get_json() or {}
        is_verified = data.get('is_verified', True)
        verification_notes = data.get('verification_notes', '')

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        table_cols = _get_table_columns(cursor, 'beneficiaries')
        if 'is_verified' not in table_cols:
            cursor.close()
            conn.close()
            return jsonify({'error': 'Verification field is not available in current database schema.'}), 400

        cursor.execute("SELECT * FROM beneficiaries WHERE beneficiary_id = %s", (beneficiary_id,))
        beneficiary = cursor.fetchone()
        if not beneficiary:
            cursor.close()
            conn.close()
            return jsonify({'error': 'Beneficiary not found'}), 404

        update_sql = "UPDATE beneficiaries SET is_verified = %s"
        values = [is_verified]
        if 'verification_notes' in table_cols:
            update_sql += ", verification_notes = %s"
            values.append(verification_notes)
        if 'date_updated' in table_cols:
            update_sql += ", date_updated = NOW()"
        update_sql += " WHERE beneficiary_id = %s"
        values.append(beneficiary_id)

        cursor = conn.cursor()
        cursor.execute(update_sql, values)

        log_audit_event(
            action='BENEFICIARY_VERIFIED',
            entity_type='beneficiary',
            entity_id=beneficiary_id,
            before_data=beneficiary,
            after_data={'is_verified': bool(is_verified), 'verification_notes': verification_notes},
            conn=conn,
            cursor=cursor
        )

        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({'success': True, 'message': 'Beneficiary verification updated'})
    except Exception as e:
        print(f"Error verifying beneficiary: {e}")
        return jsonify({'error': str(e)}), 500

# -----------------------------------------------------------------------
# ------------------------------- BLOCKCHAIN ----------------------------
# -----------------------------------------------------------------------

def init_blockchain():
    """Initialize blockchain integration"""
    try:
        blockchain_manager = get_blockchain_manager()
        
        donation_contract = os.getenv('DONATION_CONTRACT_ADDRESS', '')
        fundraiser_contract = os.getenv('FUNDRAISER_CONTRACT_ADDRESS', '')
        
        if donation_contract and fundraiser_contract:
            donation_contract = to_checksum_address(donation_contract)
            fundraiser_contract = to_checksum_address(fundraiser_contract)
            
            init_blockchain_contracts(donation_contract, fundraiser_contract)
            print("✅ Blockchain integration initialized successfully")
        else:
            print("⚠️  Blockchain contracts not configured. Set DONATION_CONTRACT_ADDRESS and FUNDRAISER_CONTRACT_ADDRESS environment variables.")
            
    except Exception as e:
        print(f"❌ Error initializing blockchain: {e}")
        print("⚠️  Blockchain features will be disabled.")

init_blockchain()
init_audit_trail()
init_admin_user_action_logs()
init_fund_completion_proofs()
init_fund_status_workflow()
init_donation_fund_tracking()


# --------------------------------------------------------------------------
# ------------------------------- BLOCKCHAIN API ---------------------------
# --------------------------------------------------------------------------

def record_donation_on_blockchain(refnum, donation_data=None, conn=None, cursor=None):
    """Record a donation on the blockchain"""
    lookup_conn = None
    lookup_cursor = None
    try:
        blockchain_manager = get_blockchain_manager()
        
        if not blockchain_manager.is_connected():
            print("⚠️ Blockchain not connected, skipping blockchain recording")
            return False
        
        donation = donation_data
        if donation is None:
            lookup_conn = get_db_connection()
            lookup_cursor = lookup_conn.cursor(dictionary=True)
            
            lookup_cursor.execute("""
                SELECT d.*, f.blockchain_fund_id, f.fund_title
                FROM donations d
                LEFT JOIN fundraisers f ON d.fund_id = f.fund_id
                WHERE d.don_refnum = %s
            """, (refnum,))
            
            donation = lookup_cursor.fetchone()
        
        if not donation:
            print(f"❌ Donation {refnum} not found")
            return False
        
        # Convert amount to ETH (assuming amount is in PHP, convert to ETH)
        # This is a simplified conversion - in production, you'd use real exchange rates
        amount_eth = float(donation['don_amount']) * 0.000018  # Approximate PHP to ETH conversion
        
        # Record on blockchain
        result = blockchain_manager.record_donation(
            fundraiser_id=donation.get('blockchain_fund_id') or donation.get('fund_id'),
            donor_address=donation.get('donor_wallet_address') or '0x0000000000000000000000000000000000000000',
            amount=amount_eth,
            reference_number=refnum
        )
        
        if result['success']:
            info_updated = update_donation_blockchain_info(
                refnum,
                result['transaction_hash'],
                result['block_number'],
                result['gas_used'],
                conn=conn,
                cursor=cursor
            )
            if not info_updated:
                print(f"Failed to persist blockchain transaction details for donation {refnum}")
                return False
            print(f"Donation {refnum} recorded on blockchain: {result['transaction_hash']}")
            return True
        else:
            print(f"Failed to record donation {refnum} on blockchain: {result['error']}")
            return False
            
    except Exception as e:
        print(f"Error recording donation on blockchain: {e}")
        return False
    finally:
        if lookup_cursor:
            lookup_cursor.close()
        if lookup_conn:
            lookup_conn.close()

def update_donation_blockchain_info(refnum, tx_hash, block_number, gas_used, conn=None, cursor=None):
    """Update donation with blockchain transaction information"""
    owns_db_resources = conn is None or cursor is None
    if owns_db_resources:
        conn = get_db_connection()
        cursor = conn.cursor()
    
    try:
        if tx_hash and not str(tx_hash).startswith('0x'):
            tx_hash = '0x' + str(tx_hash)

        cursor.execute("""
            UPDATE donations 
            SET blockchain_tx_hash = %s, block_number = %s, gas_used = %s,
                verification_status = 'verified', verification_date = NOW()
            WHERE don_refnum = %s
        """, (tx_hash, block_number, gas_used, refnum))
        
        cursor.execute("""
            INSERT INTO blockchain_transactions 
            (transaction_type, related_id, blockchain_tx_hash, block_number, gas_used, status, confirmed_at)
            SELECT 'donation', d.don_id, %s, %s, %s, 'confirmed', NOW()
            FROM donations d
            WHERE d.don_refnum = %s
        """, (tx_hash, block_number, gas_used, refnum))

        cursor.execute("""
            SELECT d.don_id
            FROM donations d
            WHERE d.don_refnum = %s
            LIMIT 1
        """, (refnum,))
        row = cursor.fetchone()
        if row:
            if isinstance(row, dict):
                don_id = row.get('don_id')
            else:
                don_id = row[0]

            if don_id is None:
                raise ValueError(f"Could not resolve donation id for refnum {refnum}")

            try:
                cursor.execute("""
                    UPDATE donations d
                    SET
                        d.donation_row_hash_original = COALESCE(d.donation_row_hash_original, d.donation_row_hash),
                        d.original_tx_hash = COALESCE(d.original_tx_hash, d.blockchain_tx_hash)
                    WHERE d.don_id = %s
                """, (don_id,))
            except Exception as donation_baseline_err:
                if "donation_row_hash_original" not in str(donation_baseline_err) and "original_tx_hash" not in str(donation_baseline_err):
                    raise

            try:
                cursor.execute("""
                    UPDATE blockchain_transactions bt
                    SET
                        bt.tx_row_hash = fn_blockchain_tx_row_hash_v1(
                            bt.id,
                            bt.transaction_type,
                            bt.related_id,
                            bt.blockchain_tx_hash,
                            bt.block_number,
                            bt.gas_used,
                            bt.gas_price,
                            bt.status,
                            bt.confirmation_blocks,
                            bt.created_at,
                            bt.confirmed_at,
                            bt.error_message
                        ),
                        bt.tx_row_hash_original = COALESCE(bt.tx_row_hash_original, bt.tx_row_hash),
                        bt.original_tx_hash = COALESCE(bt.original_tx_hash, bt.blockchain_tx_hash)
                    WHERE bt.blockchain_tx_hash = %s
                      AND bt.transaction_type = 'donation'
                      AND bt.related_id = %s
                """, (tx_hash, don_id))
            except Exception as tx_update_err:
                if (
                    "tx_row_hash_original" in str(tx_update_err)
                    or "original_tx_hash" in str(tx_update_err)
                ):
                    cursor.execute("""
                        UPDATE blockchain_transactions bt
                        SET
                            bt.tx_row_hash = fn_blockchain_tx_row_hash_v1(
                                bt.id,
                                bt.transaction_type,
                                bt.related_id,
                                bt.blockchain_tx_hash,
                                bt.block_number,
                                bt.gas_used,
                                bt.gas_price,
                                bt.status,
                                bt.confirmation_blocks,
                                bt.created_at,
                                bt.confirmed_at,
                                bt.error_message
                            )
                        WHERE bt.blockchain_tx_hash = %s
                          AND bt.transaction_type = 'donation'
                          AND bt.related_id = %s
                    """, (tx_hash, don_id))
                else:
                    raise
        else:
            print(f"Unable to find donation for refnum {refnum} while post-writing blockchain tx metadata.")

        if owns_db_resources:
            conn.commit()
        return True
    except Exception as e:
        print(f"Error updating donation blockchain info: {e}")
        if owns_db_resources and conn:
            conn.rollback()
        return False
    finally:
        if owns_db_resources:
            cursor.close()
            conn.close()

def verify_donation_on_blockchain(tx_hash):
    try:
        blockchain_manager = get_blockchain_manager()
        
        if not blockchain_manager.is_connected():
            return {'success': False, 'error': 'Blockchain not connected'}
        
        result = blockchain_manager.verify_donation(tx_hash)
        
        if result['success'] and result['is_valid']:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE donations 
                SET verification_status = 'verified', verification_date = NOW()
                WHERE blockchain_tx_hash = %s
            """, (tx_hash,))
            
            conn.commit()
            cursor.close()
            conn.close()
        
        return result
        
    except Exception as e:
        return {'success': False, 'error': str(e)}

def get_user_wallet_address(user_id):
    """Get user's primary wallet address"""
    if user_id is None or user_id == 0:
        return None
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            SELECT wallet_address FROM wallet_addresses 
            WHERE user_id = %s AND is_primary = TRUE
        """, (user_id,))
        
        result = cursor.fetchone()
        if result:
            return to_checksum_address(result[0])
        return None
        
    except Exception as e:
        print(f"Error getting user wallet address: {e}")
        return None
    finally:
        cursor.close()
        conn.close()

def add_wallet_address(user_id, wallet_address, wallet_type='ethereum'):
    """Add a wallet address for a user"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        wallet_address = to_checksum_address(wallet_address)
        
        cursor.execute("SELECT COUNT(*) FROM wallet_addresses WHERE user_id = %s", (user_id,))
        is_first_wallet = cursor.fetchone()[0] == 0
        
        cursor.execute("""
            INSERT INTO wallet_addresses 
            (user_id, wallet_address, wallet_type, is_primary, is_verified)
            VALUES (%s, %s, %s, %s, FALSE)
        """, (user_id, wallet_address, wallet_type, is_first_wallet))
        
        conn.commit()
        return True
        
    except Exception as e:
        print(f"Error adding wallet address: {e}")
        return False
    finally:
        cursor.close()
        conn.close()

@app.route('/api/blockchain/verify-donation', methods=['POST'])
def api_verify_donation():
    try:
        data = request.get_json() or {}
        tx_hash = data.get('transaction_hash') or data.get('tx_hash') or data.get('tx') or data.get('hash')
        db_scan_only = bool(data.get('db_scan') or data.get('scan_only') or data.get('integrity_only'))

        if not tx_hash:
            return jsonify({'success': False, 'error': 'Transaction hash is required'}), 400

        if isinstance(tx_hash, str) and not tx_hash.startswith('0x'):
            tx_hash = '0x' + tx_hash

        tx_hash_norm = (tx_hash or '').strip().lower()
        tx_hash_noprefix = tx_hash_norm[2:] if tx_hash_norm.startswith('0x') else tx_hash_norm

        def format_value(value):
            if value is None:
                return None
            if hasattr(value, 'strftime'):
                return value.strftime('%Y-%m-%d %H:%M:%S')
            try:
                return float(value) if hasattr(value, 'as_tuple') else value
            except Exception:
                return str(value)

        def comparable(value):
            formatted = format_value(value)
            return '' if formatted is None else str(formatted).strip().lower()

        def run_tamper_aware_db_verification():
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            try:
                tracked_fields = [
                    ('fund_id', 'tampered_fund_id'),
                    ('don_donorid', 'tampered_don_donorid'),
                    ('don_donorname', 'tampered_don_donorname'),
                    ('don_paymethod', 'tampered_don_paymethod'),
                    ('don_amount', 'tampered_don_amount'),
                    ('don_refnum', 'tampered_don_refnum'),
                    ('don_date', 'tampered_don_date'),
                    ('donor_wallet_address', 'tampered_donor_wallet_address')
                ]

                cursor.execute("""
                    SELECT COLUMN_NAME
                    FROM information_schema.COLUMNS
                    WHERE TABLE_SCHEMA = DATABASE()
                      AND TABLE_NAME = 'donations'
                      AND COLUMN_NAME IN (
                        'tampered_fund_id',
                        'tampered_don_donorid',
                        'tampered_don_donorname',
                        'tampered_don_receiver',
                        'tampered_don_paymethod',
                        'tampered_don_amount',
                        'tampered_don_refnum',
                        'tampered_don_date',
                        'tampered_donor_wallet_address'
                      )
                """)
                existing_tampered_columns = {row['COLUMN_NAME'] for row in cursor.fetchall()}
                tampered_select_sql = ",\n".join(
                    f"                        d.{tampered_field}" if tampered_field in existing_tampered_columns
                    else f"                        NULL AS {tampered_field}"
                    for _, tampered_field in tracked_fields
                )

                cursor.execute("""
                    SELECT
                        d.don_id,
                        d.fund_id,
                        d.don_donorid,
                        d.don_donorname,
                        d.don_receiver,
                        d.don_paymethod,
                        d.don_amount,
                        d.don_refnum,
                        d.don_date,
                        d.donor_wallet_address,
                        d.blockchain_tx_hash,
                        d.original_tx_hash,
                        d.verification_status,
                        COALESCE(d.is_tampered, 0) AS donation_is_tampered,
{tampered_select_sql},
                        b.id AS blockchain_tx_id
                    FROM donations d
                    LEFT JOIN blockchain_transactions b
                      ON d.don_id = b.related_id
                     AND b.transaction_type = 'donation'
                    WHERE (
                        LOWER(COALESCE(d.blockchain_tx_hash, '')) IN (%s, %s)
                        OR LOWER(COALESCE(d.original_tx_hash, '')) IN (%s, %s)
                    )
                    ORDER BY b.id DESC, d.don_id DESC
                    LIMIT 1
                """.format(tampered_select_sql=tampered_select_sql), (tx_hash_norm, tx_hash_noprefix, tx_hash_norm, tx_hash_noprefix))
                row = cursor.fetchone()

                if not row:
                    return {
                        'found': False,
                        'response': {
                            'success': False,
                            'is_valid': False,
                            'status': 'failed',
                            'message': 'Verification Failed: No matching donation record was found.',
                            'transaction_hash': tx_hash,
                            'is_tampered': 0,
                            'differences': {}
                        }
                    }

                differences = {}
                for original_field, tampered_field in tracked_fields:
                    tampered_value = row.get(tampered_field)
                    if tampered_value is None:
                        continue

                    original_value = row.get(original_field)
                    if comparable(original_value) != comparable(tampered_value):
                        differences[original_field] = {
                            'original': format_value(original_value),
                            'tampered': format_value(tampered_value)
                        }

                current_hash = comparable(row.get('blockchain_tx_hash'))
                original_hash = comparable(row.get('original_tx_hash'))
                hash_matches = bool(current_hash) and bool(original_hash) and current_hash == original_hash

                if not hash_matches:
                    differences['blockchain_tx_hash'] = {
                        'original': format_value(row.get('original_tx_hash')),
                        'tampered': format_value(row.get('blockchain_tx_hash'))
                    }

                is_tampered = 1 if differences else 0
                final_status = 'verified' if is_tampered == 0 and hash_matches else 'failed'

                cursor.execute("""
                    UPDATE donations
                    SET is_tampered = %s,
                        verification_status = %s,
                        verification_date = NOW()
                    WHERE don_id = %s
                """, (is_tampered, final_status, row['don_id']))

                if row.get('blockchain_tx_id'):
                    cursor.execute("""
                        UPDATE blockchain_transactions
                        SET is_tampered = %s
                        WHERE id = %s
                    """, (1 if is_tampered == 1 else 0, row['blockchain_tx_id']))

                conn.commit()

                return {
                    'found': True,
                    'response': {
                        'success': True,
                        'is_valid': final_status == 'verified',
                        'status': final_status,
                        'message': 'Verification Successful' if final_status == 'verified' else 'Verification Failed: Data has been tampered',
                        'transaction_hash': tx_hash,
                        'is_tampered': is_tampered,
                        'differences': differences,
                        'donation_id': row.get('don_id'),
                        'verification_status': final_status
                    }
                }
            finally:
                cursor.close()
                conn.close()

        db_check = run_tamper_aware_db_verification()

        if not db_check['found']:
            return jsonify(db_check['response']), 404

        if db_scan_only:
            return jsonify(db_check['response'])

        if not db_check['response']['is_valid']:
            return jsonify(db_check['response'])

        try:
            manager = get_blockchain_manager()
            if not manager.is_connected():
                return jsonify({'success': False, 'error': 'Blockchain node not connected'}), 503
        except Exception as e:
            return jsonify({'success': False, 'error': f'Could not get blockchain manager: {e}'}), 500

        result = verify_donation_on_blockchain(tx_hash)
        if not isinstance(result, dict):
            return jsonify({'success': False, 'error': 'Unexpected verification result format', 'raw': str(result)}), 500

        if not result.get('success') or result.get('is_valid') is False:
            return jsonify({
                'success': False,
                'is_valid': False,
                'status': 'failed',
                'message': result.get('error') or 'Transaction invalid on-chain.',
                'transaction_hash': tx_hash,
                'is_tampered': db_check['response'].get('is_tampered', 0),
                'differences': db_check['response'].get('differences', {})
            })

        result['status'] = 'verified'
        result['message'] = 'Verification Successful'
        result['transaction_hash'] = tx_hash
        result['is_tampered'] = 0
        result['differences'] = {}
        return jsonify(result)

    except Exception as e:
        print(f"api_verify_donation error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/blockchain/add-wallet', methods=['POST'])
def api_add_wallet():
    """Add a wallet address for the current user"""
    if 'email' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        data = request.get_json()
        wallet_address = data.get('wallet_address')
        wallet_type = data.get('wallet_type', 'ethereum')
        
        if not wallet_address:
            return jsonify({'error': 'Wallet address is required'}), 400
        
        if not wallet_address.startswith('0x') or len(wallet_address) != 42:
            return jsonify({'error': 'Invalid wallet address format'}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE email = %s", (session['email'],))
        user = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        success = add_wallet_address(user[0], wallet_address, wallet_type)
        
        if success:
            return jsonify({'success': True, 'message': 'Wallet address added successfully'})
        else:
            return jsonify({'error': 'Failed to add wallet address'}), 500
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/blockchain/get-wallets')
def api_get_wallets():
    """Get wallet addresses for the current user"""
    if 'email' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("""
            SELECT wa.*, u.email
            FROM wallet_addresses wa
            JOIN users u ON wa.user_id = u.id
            WHERE u.email = %s
            ORDER BY wa.is_primary DESC, wa.created_at DESC
        """, (session['email'],))
        
        wallets = cursor.fetchall()
        cursor.close()
        conn.close()
        
        return jsonify({'wallets': wallets})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/blockchain/transaction-status/<tx_hash>')
def api_transaction_status(tx_hash):
    """Get the status of a blockchain transaction"""
    if 'email' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        blockchain_manager = get_blockchain_manager()
        result = blockchain_manager.get_transaction_status(tx_hash)
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/blockchain/fundraiser-donations/<int:fundraiser_id>')
def api_fundraiser_donations(fundraiser_id):
    """Get blockchain donations for a specific fundraiser"""
    if 'email' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        blockchain_manager = get_blockchain_manager()
        donations = blockchain_manager.get_fundraiser_donations(fundraiser_id)
        return jsonify({'donations': donations})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/blockchain/verify-all-pending')
def api_verify_all_pending():
    """Verify all pending blockchain transactions (admin/treasurer only)"""
    if 'email' not in session or session.get('role') not in ['Admin', 'Treasurer']:
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("""
            SELECT don_refnum, blockchain_tx_hash
            FROM donations 
            WHERE verification_status = 'pending' 
            AND blockchain_tx_hash IS NOT NULL
        """)
        
        pending_donations = cursor.fetchall()
        cursor.close()
        conn.close()
        
        verified_count = 0
        failed_count = 0
        
        for donation in pending_donations:
            result = verify_donation_on_blockchain(donation['blockchain_tx_hash'])
            if result['success'] and result['is_valid']:
                verified_count += 1
            else:
                failed_count += 1
        
        return jsonify({
            'success': True,
            'verified': verified_count,
            'failed': failed_count,
            'total': len(pending_donations)
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/blockchain/transactions')
def api_blockchain_transactions():
    """API endpoint for fetching blockchain transaction data"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 20, type=int), 50)
        offset = (page - 1) * per_page
        
        search_query = request.args.get('search', '')
        status_filter = request.args.get('status', 'all')
        fundraiser_filter = request.args.get('fundraiser', 'all')
        
        where_conditions = ["d.blockchain_tx_hash IS NOT NULL"]
        params = []
        
        if search_query:
            where_conditions.append("(d.don_refnum LIKE %s OR d.don_donorname LIKE %s OR f.fund_title LIKE %s)")
            search_param = f"%{search_query}%"
            params.extend([search_param, search_param, search_param])
        
        if status_filter != 'all':
            where_conditions.append("d.don_status = %s")
            params.append(status_filter)
        
        if fundraiser_filter != 'all':
            where_conditions.append("d.fund_id = %s")
            params.append(int(fundraiser_filter))
        
        where_clause = " AND ".join(where_conditions)
        
        count_query = f"""
            SELECT COUNT(*) as total
            FROM donations d
            LEFT JOIN fundraisers f ON d.fund_id = f.fund_id
            WHERE {where_clause}
        """
        cursor.execute(count_query, params)
        total_count = cursor.fetchone()['total']
        
        query = f"""
            SELECT 
                d.don_id, d.don_refnum, d.don_donorname, d.don_amount,
                d.don_status, d.don_date, d.blockchain_tx_hash, d.block_number,
                d.gas_used, d.verification_status, d.verification_date,
                f.fund_id, f.fund_title, f.fund_category,
                u.name as donor_name, u.email as donor_email
            FROM donations d
            LEFT JOIN fundraisers f ON d.fund_id = f.fund_id
            LEFT JOIN users u ON d.don_donorid = u.id
            WHERE {where_clause}
            ORDER BY d.don_date DESC
            LIMIT %s OFFSET %s
        """
        params.extend([per_page, offset])
        cursor.execute(query, params)
        transactions = cursor.fetchall()
        
        stats_query = f"""
            SELECT 
                COUNT(*) as total_transactions,
                SUM(CASE WHEN d.don_status = 'Paid' THEN d.don_amount ELSE 0 END) as total_amount,
                COUNT(DISTINCT d.fund_id) as unique_fundraisers,
                COUNT(DISTINCT d.don_donorid) as unique_donors,
                AVG(d.don_amount) as avg_donation
            FROM donations d
            WHERE {where_clause}
        """
        cursor.execute(stats_query, params[:-2])
        stats = cursor.fetchone()
        
        cursor.close()
        conn.close()
        
        total_pages = (total_count + per_page - 1) // per_page
        has_prev = page > 1
        has_next = page < total_pages
        
        pagination = {
            'page': page,
            'per_page': per_page,
            'total': total_count,
            'total_pages': total_pages,
            'has_prev': has_prev,
            'has_next': has_next,
            'prev_num': page - 1 if has_prev else None,
            'next_num': page + 1 if has_next else None
        }
        
        return jsonify({
            'success': True,
            'transactions': transactions,
            'stats': stats,
            'pagination': pagination
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/blockchain/transaction/<tx_hash>')
def blockchain_transaction_details(tx_hash):
    """Display detailed blockchain transaction information"""
    try:
        # Ensure tx_hash starts with '0x'
        if tx_hash and not tx_hash.startswith('0x'):
            tx_hash = '0x' + tx_hash
        tx_hash_norm = (tx_hash or '').strip().lower()
        tx_hash_noprefix = tx_hash_norm[2:] if tx_hash_norm.startswith('0x') else tx_hash_norm
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("""
            SELECT d.*, f.fund_title, u.name as donor_name, b.id AS blockchain_tx_id
            FROM blockchain_transactions b
            LEFT JOIN donations d
              ON d.don_id = b.related_id
            LEFT JOIN fundraisers f
              ON d.fund_id = f.fund_id
            LEFT JOIN users u
              ON d.don_donorid = u.id
            WHERE b.transaction_type = 'donation'
              AND (
                LOWER(COALESCE(b.blockchain_tx_hash, '')) IN (%s, %s)
                OR LOWER(COALESCE(d.blockchain_tx_hash, '')) IN (%s, %s)
              )
            ORDER BY b.id DESC
            LIMIT 1
        """, (tx_hash_norm, tx_hash_noprefix, tx_hash_norm, tx_hash_noprefix))
        
        donation = cursor.fetchone()

        if not donation:
            # Backward-compatible fallback for schema/rows where blockchain_transactions
            # row may not exist yet.
            cursor.execute("""
                SELECT d.*, f.fund_title, u.name as donor_name
                FROM donations d
                LEFT JOIN fundraisers f ON d.fund_id = f.fund_id
                LEFT JOIN users u ON d.don_donorid = u.id
                WHERE LOWER(COALESCE(d.blockchain_tx_hash, '')) IN (%s, %s)
            """, (tx_hash_norm, tx_hash_noprefix))
            donation = cursor.fetchone()

        if not donation:
            cursor.close()
            conn.close()
            return jsonify({'success': False, 'message': 'Transaction not found'}), 404
        cursor.close()
        conn.close()
        
        verification_result = verify_donation_on_blockchain(tx_hash) or {}

        if not isinstance(verification_result, dict):
            verification_result = {'success': False, 'is_valid': False, 'error': 'Invalid verification response'}

        if verification_result.get('fundraiser_id') in (None, 0):
            verification_result['fundraiser_id'] = donation.get('fund_id') or donation.get('fundraiser_id')

        if not verification_result.get('donor_address'):
            verification_result['donor_address'] = donation.get('donor_wallet_address') or donation.get('donor_address')

        if verification_result.get('amount') in (None, 0):
            try:
                php_amt = float(donation.get('don_amount') or 0)
                verification_result['amount'] = round(php_amt * 0.000018, 8)
            except Exception:
                verification_result['amount'] = None

        if not verification_result.get('reference_number'):
            verification_result['reference_number'] = donation.get('don_refnum')

        if not verification_result.get('timestamp'):
            d = donation.get('don_date')
            try:
                verification_result['timestamp'] = d.isoformat() if hasattr(d, 'isoformat') else d
            except Exception:
                verification_result['timestamp'] = str(d)

        # Try to fetch a simple ETH -> PHP conversion rate to show local currency immediately
        def fetch_eth_to_php_rate():
            try:
                resp = requests.get('https://api.coingecko.com/api/v3/simple/price', params={
                    'ids': 'ethereum',
                    'vs_currencies': 'php'
                }, timeout=5)
                if resp.status_code == 200:
                    j = resp.json()
                    return j.get('ethereum', {}).get('php')
            except Exception:
                return None
            return None

        eth_to_php_rate = fetch_eth_to_php_rate()

        return render_template('blockchain_transaction.html',
            donation=donation,
            verification=verification_result,
            tx_hash=tx_hash,
            eth_to_php_rate=eth_to_php_rate)
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500


@app.route('/api/blockchain/records')
def api_blockchain_records():
    """Return recent donation records with blockchain info and payload hash."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT d.don_id, d.fund_id, d.don_amount, d.don_refnum, d.don_status, d.don_date, d.don_notes, d.donor_wallet_address, d.blockchain_tx_hash, d.block_number,
                    f.fund_title
            FROM donations d
            LEFT JOIN fundraisers f ON d.fund_id = f.fund_id
            ORDER BY d.don_date DESC
            LIMIT 200
        """)
        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        results = []
        for r in rows:
            payload_hash = None
            try:
                if r.get('don_notes'):
                    j = json.loads(r.get('don_notes'))
                    payload_hash = j.get('plaintext_sha256') if isinstance(j, dict) else None
            except Exception:
                payload_hash = None

            tx_hash = r.get('blockchain_tx_hash')
            if tx_hash and not tx_hash.startswith('0x'):
                tx_hash = '0x' + tx_hash

            results.append({
                'don_id': r.get('don_id'),
                'fund_id': r.get('fund_id'),
                'fund_title': r.get('fund_title'),
                'amount': float(r.get('don_amount') or 0),
                'refnum': r.get('don_refnum'),
                'status': r.get('don_status'),
                'date': r.get('don_date').isoformat() if r.get('don_date') else None,
                'wallet': r.get('donor_wallet_address') or 'Not provided',
                'tx_hash': tx_hash,
                'block_number': r.get('block_number'),
                'payload_hash': payload_hash
            })

        return jsonify({'success': True, 'records': results})
    except Exception as e:
        print(f"Error fetching blockchain records: {e}")
        return jsonify({'succes-error': str(e)}), 500


def log_payload_change(donation_id, refnum, payload_hash, payload_data, previous_hash=None, change_type='updated', change_reason=None, changed_by=None):
    """Manually log a payload hash change"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        validated_changed_by = None
        if changed_by and changed_by > 0:
            cursor.execute("SELECT id FROM users WHERE id = %s", (changed_by,))
            if cursor.fetchone():
                validated_changed_by = changed_by
        
        cursor.execute("""
            INSERT INTO payload_history (
                donation_id, don_refnum, payload_hash, payload_data,
                previous_hash, change_type, change_reason, changed_by
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            donation_id, refnum, payload_hash, payload_data,
            previous_hash, change_type, change_reason, validated_changed_by
        ))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return True
        
    except Exception as e:
        print(f"Error logging payload change: {e}")
        return False

@app.route('/api/payload-history/<int:donation_id>')
def get_payload_history(donation_id):
    """Get payload hash history for a specific donation"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("""
            SELECT don_refnum, don_notes FROM donations WHERE don_id = %s
        """, (donation_id,))
        
        donation = cursor.fetchone()
        if not donation:
            cursor.close()
            conn.close()
            return jsonify({'success': False, 'error': 'Donation not found'}), 404
        
        cursor.execute("""
            SELECT ph.*, u.name as changed_by_name, u.email as changed_by_email
            FROM payload_history ph
            LEFT JOIN users u ON ph.changed_by = u.id
            WHERE ph.donation_id = %s
            ORDER BY ph.created_at DESC
        """, (donation_id,))
        
        history = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'donation_id': donation_id,
            'refnum': donation['don_refnum'],
            'history': history,
            'total_changes': len(history)
        })
        
    except Exception as e:
        print(f"Error fetching payload history: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

def _resolve_donation_id_by_refnum(refnum):
    """Resolve a reference number to the latest matching donation ID."""
    normalized_ref = (refnum or '').strip()
    if not normalized_ref:
        return None

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT don_id
            FROM donations
            WHERE UPPER(TRIM(don_refnum)) = UPPER(TRIM(%s))
            ORDER BY don_id DESC
            LIMIT 1
        """, (normalized_ref,))
        row = cursor.fetchone()
        if row:
            return row['don_id']

        # Fallback: resolve by payload history reference if donation ref formatting is inconsistent.
        cursor.execute("""
            SELECT donation_id AS don_id
            FROM payload_history
            WHERE UPPER(TRIM(don_refnum)) = UPPER(TRIM(%s))
            ORDER BY created_at DESC
            LIMIT 1
        """, (normalized_ref,))
        history_row = cursor.fetchone()
        return history_row['don_id'] if history_row else None
    finally:
        cursor.close()
        conn.close()

@app.route('/api/payload-history/ref/<refnum>')
def get_payload_history_by_ref(refnum):
    """Get payload history by donation reference number."""
    donation_id = _resolve_donation_id_by_refnum(refnum)
    if not donation_id:
        return jsonify({'success': False, 'error': 'Donation not found'}), 404
    return get_payload_history(donation_id)

@app.route('/api/payload-history/verify/<int:donation_id>')
def verify_payload_integrity(donation_id):
    """Verify the integrity of a donation's payload by comparing hashes"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("""
            SELECT d.*, f.fund_title
            FROM donations d
            LEFT JOIN fundraisers f ON d.fund_id = f.fund_id
            WHERE d.don_id = %s
        """, (donation_id,))
        
        donation = cursor.fetchone()
        if not donation:
            cursor.close()
            conn.close()
            return jsonify({'success': False, 'error': 'Donation not found'}), 404
        
        stored_hash = None
        encrypted_payload = None
        if donation['don_notes']:
            try:
                notes = json.loads(donation['don_notes'])
                stored_hash = notes.get('plaintext_sha256')
                encrypted_payload = notes.get('enc')
            except:
                pass
        
        is_valid = True
        integrity_status = "No history to verify"
        original_hash = None
        latest_hash = None
        
        if stored_hash:
            cursor.execute("""
                SELECT payload_hash FROM payload_history
                WHERE donation_id = %s
                ORDER BY created_at DESC
                LIMIT 1
            """, (donation_id,))
            result = cursor.fetchone()
            latest_hash = result['payload_hash'] if result else None
            if latest_hash and latest_hash != stored_hash:
                is_valid = False
                integrity_status = "Stored hash doesn't match history"
            else:
                integrity_status = "Integrity verified against history"

            try:
                cursor.execute("""
                    SELECT payload_hash FROM payload_history
                    WHERE donation_id = %s
                    ORDER BY created_at ASC
                    LIMIT 1
                """, (donation_id,))
                first_row = cursor.fetchone()
                original_hash = first_row['payload_hash'] if first_row else None
            except Exception as _:
                original_hash = None
        else:
            is_valid = False
            integrity_status = "No stored hash found"
        
        cursor.execute("""
            SELECT payload_hash, created_at, change_type, change_reason
            FROM payload_history
            WHERE donation_id = %s
            ORDER BY created_at DESC
        """, (donation_id,))
        
        history = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'is_valid': is_valid,
            'current_hash': stored_hash,
            'original_hash': original_hash,
            'latest_hash': latest_hash,
            'hashes_match': (stored_hash == original_hash) if (stored_hash and original_hash) else False,
            'modified_but_verified': bool(stored_hash and original_hash and latest_hash and stored_hash == latest_hash and stored_hash != original_hash),
            'donation_id': donation_id,
            'refnum': donation['don_refnum'],
            'verification_timestamp': datetime.now().isoformat(),
            'history': history,
            'tamper_detected': not is_valid,
            'integrity_status': integrity_status,
            'history_count': len(history)
        })
        
    except Exception as e:
        print(f"Error verifying payload integrity: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/payload-history/verify/ref/<refnum>')
def verify_payload_integrity_by_ref(refnum):
    """Verify payload integrity by donation reference number."""
    donation_id = _resolve_donation_id_by_refnum(refnum)
    if not donation_id:
        return jsonify({'success': False, 'error': 'Donation not found'}), 404
    return verify_payload_integrity(donation_id)

@app.route('/payload-history/<int:donation_id>')
def view_payload_history(donation_id):
    """Display payload history page for a specific donation"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("""
            SELECT d.*, f.fund_title
            FROM donations d
            LEFT JOIN fundraisers f ON d.fund_id = f.fund_id
            WHERE d.don_id = %s
        """, (donation_id,))
        
        donation = cursor.fetchone()
        if not donation:
            cursor.close()
            conn.close()
            return "Donation not found", 404
        
        cursor.execute("""
            SELECT ph.*, u.name as changed_by_name
            FROM payload_history ph
            LEFT JOIN users u ON ph.changed_by = u.id
            WHERE ph.donation_id = %s
            ORDER BY ph.created_at DESC
        """, (donation_id,))
        
        history = cursor.fetchall()
        
        current_hash = None
        if donation['don_notes']:
            try:
                notes = json.loads(donation['don_notes'])
                current_hash = notes.get('plaintext_sha256')
            except:
                pass
        
        cursor.close()
        conn.close()
        
        settings = get_all_settings()
        
        return render_template('payload_history.html',
            donation=donation,
            history=history,
            current_hash=current_hash,
            settings=settings)
        
    except Exception as e:
        print(f"Error loading payload history: {e}")
        return f"Error loading payload history: {str(e)}", 500

@app.route('/payload-history/ref/<refnum>')
def view_payload_history_by_ref(refnum):
    """Display payload history page for a specific donation reference number."""
    donation_id = _resolve_donation_id_by_refnum(refnum)
    if not donation_id:
        return "Donation not found", 404
    return view_payload_history(donation_id)

@app.route('/blockchain/records')
def blockchain_records():
    try:
        page = request.args.get('page', 1, type=int)
        per_page = 20
        offset = (page - 1) * per_page
        start_date = (request.args.get('start_date') or '').strip()
        end_date = (request.args.get('end_date') or '').strip()
        fundraiser_id = request.args.get('fundraiser_id', 'all')

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT fund_id, fund_title
            FROM fundraisers
            ORDER BY fund_title ASC
        """)
        fundraiser_options = cursor.fetchall()

        conditions = []
        params = []

        if start_date:
            conditions.append("DATE(d.don_date) >= %s")
            params.append(start_date)

        if end_date:
            conditions.append("DATE(d.don_date) <= %s")
            params.append(end_date)

        if fundraiser_id != 'all':
            try:
                fundraiser_id_int = int(fundraiser_id)
                conditions.append("d.fund_id = %s")
                params.append(fundraiser_id_int)
            except (TypeError, ValueError):
                fundraiser_id = 'all'

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        cursor.execute(f"""
            SELECT COUNT(*) as total
            FROM donations d
            LEFT JOIN fundraisers f ON d.fund_id = f.fund_id
            {where_clause}
        """, params)
        total_count = cursor.fetchone().get('total', 0)

        cursor.execute(f"""
            SELECT d.don_id, d.fund_id, d.don_amount, d.don_refnum, d.don_status, d.don_date, d.don_notes, d.donor_wallet_address, d.blockchain_tx_hash, d.block_number, f.fund_title
            FROM donations d
            LEFT JOIN fundraisers f ON d.fund_id = f.fund_id
            {where_clause}
            ORDER BY d.don_date DESC
            LIMIT %s OFFSET %s
        """, params + [per_page, offset])

        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        results = []
        for r in rows:
            payload_hash = None
            try:
                if r.get('don_notes'):
                    j = json.loads(r.get('don_notes'))
                    payload_hash = j.get('plaintext_sha256') if isinstance(j, dict) else None
            except Exception:
                payload_hash = None

            tx_hash = r.get('blockchain_tx_hash')
            if tx_hash and not tx_hash.startswith('0x'):
                tx_hash = '0x' + tx_hash

            results.append({
                'don_id': r.get('don_id'),
                'fund_id': r.get('fund_id'),
                'fund_title': r.get('fund_title'),
                'amount': float(r.get('don_amount') or 0),
                'refnum': r.get('don_refnum'),
                'status': r.get('don_status'),
                'date': r.get('don_date').strftime('%m/%d/%y %H:%M') if r.get('don_date') else None,
                'wallet': r.get('donor_wallet_address') or 'Not provided',
                'tx_hash': tx_hash,
                'block_number': r.get('block_number'),
                'payload_hash': payload_hash
            })

        total_pages = (total_count + per_page - 1) // per_page if per_page > 0 else 1
        has_prev = page > 1
        has_next = page < total_pages

        pagination = {
            'page': page,
            'per_page': per_page,
            'total': total_count,
            'total_pages': total_pages,
            'has_prev': has_prev,
            'has_next': has_next,
            'prev_num': page - 1 if has_prev else None,
            'next_num': page + 1 if has_next else None
        }

        settings = get_all_settings()
        return render_template(
            'blockchain_records.html',
            settings=settings,
            records=results,
            pagination=pagination,
            fundraiser_options=fundraiser_options,
            filters={
                'start_date': start_date,
                'end_date': end_date,
                'fundraiser_id': fundraiser_id
            }
        )
    except Exception as e:
        print(f"Error in blockchain_records view: {e}")
        settings = get_all_settings()
        return render_template(
            'blockchain_records.html',
            settings=settings,
            records=[],
            pagination={},
            fundraiser_options=[],
            filters={'start_date': '', 'end_date': '', 'fundraiser_id': 'all'}
        )

@app.route('/blockchain/transactions')
def blockchain_transactions_display():
    """Display all blockchain transactions transparently from actual blockchain data"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = 15
        limit = per_page * 2
        
        search_query = request.args.get('search', '').lower()
        status_filter = request.args.get('status', 'all')
        tx_type_filter = request.args.get('type', 'all')
        
        start_block = None
        if page > 1:
            start_block = max(0, 1000 * (page - 1))
        
        print(f"Fetching blockchain transactions - Page {page}, Limit {limit}")
        
        blockchain_txs = get_wallet_transactions_from_blockchain(
            wallet_address=None,
            limit=limit,
            start_block=start_block
        )
        
        print(f"Retrieved {len(blockchain_txs)} raw blockchain transactions")
        
        filtered_txs = []
        for tx in blockchain_txs:
            if search_query:
                searchable_text = f"{tx['hash']} {tx['from_address']} {tx['to_address']} {tx['function_name'] or ''}".lower()
                if search_query not in searchable_text:
                    continue
            
            if status_filter != 'all':
                if status_filter == 'success' and tx['status'] != 'success':
                    continue
                elif status_filter == 'failed' and tx['status'] != 'failed':
                    continue
            
            if tx_type_filter != 'all':
                if tx_type_filter == 'contract' and not tx['is_contract_tx']:
                    continue
                elif tx_type_filter == 'transfer' and tx['is_contract_tx']:
                    continue
            
            filtered_txs.append(tx)
        
        print(f"{len(filtered_txs)} transactions after filtering")
        
        total_count = len(filtered_txs)
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        paginated_txs = filtered_txs[start_idx:end_idx]
        
        total_value = sum(tx['value'] for tx in filtered_txs)
        contract_txs = [tx for tx in filtered_txs if tx['is_contract_tx']]
        unique_addresses = len(set(tx['from_address'] for tx in filtered_txs))
        
        stats = {
            'total_transactions': total_count,
            'total_value': total_value,
            'contract_transactions': len(contract_txs),
            'unique_addresses': unique_addresses,
            'avg_value': total_value / total_count if total_count > 0 else 0
        }
        
        total_pages = (total_count + per_page - 1) // per_page
        has_prev = page > 1
        has_next = page < total_pages
        
        pagination = {
            'page': page,
            'per_page': per_page,
            'total': total_count,
            'total_pages': total_pages,
            'has_prev': has_prev,
            'has_next': has_next,
            'prev_num': page - 1 if has_prev else None,
            'next_num': page + 1 if has_next else None
        }
        
        return render_template('blockchain_transactions.html',
            transactions=paginated_txs,
            stats=stats,
            pagination=pagination,
            search_query=search_query,
            status_filter=status_filter,
            tx_type_filter=tx_type_filter,
            wallet_address=get_wallet_address())
        
    except Exception as e:
        print(f"Error in blockchain transactions display: {e}")
    return jsonify({'success': False, 'message': f'Error loading blockchain transactions: {str(e)}'}), 500


# -----------------------------------------------------------------------
# ------------------------------- FILTERS -------------------------------
# -----------------------------------------------------------------------

def time_ago(dt):
    try:
        now = datetime.now()
        if dt is None:
            return "just now"
        if not isinstance(dt, datetime):
            return str(dt)

        if dt > now:
            return "just now"

        delta = now - dt
        seconds = int(delta.total_seconds())
        minutes = seconds // 60
        hours = minutes // 60
        days = hours // 24
        weeks = days // 7
        months = days // 30
        years = days // 365

        if seconds < 60:
            return "just now"
        if minutes < 60:
            return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
        if hours < 24:
            return f"{hours} hour{'s' if hours != 1 else ''} ago"
        if days < 7:
            return f"{days} day{'s' if days != 1 else ''} ago"
        if weeks < 5:
            return f"{weeks} week{'s' if weeks != 1 else ''} ago"
        if months < 12:
            return f"{months} month{'s' if months != 1 else ''} ago"
        return f"{years} year{'s' if years != 1 else ''} ago"
    except Exception:
        return "just now"

app.jinja_env.filters['time_ago'] = time_ago

def b64encode_filter(data):
    if data:
        return b64encode(data).decode('utf-8')
    return None

def strftime_filter(timestamp, format_string):
    from datetime import datetime
    if isinstance(timestamp, (int, float)):
        return datetime.fromtimestamp(timestamp).strftime(format_string)
    return str(timestamp)

app.jinja_env.filters['b64encode'] = b64encode_filter
app.jinja_env.filters['strftime'] = strftime_filter


# -----------------------------------------------------------------------
# ------------------------------- RUN APP -------------------------------
# -----------------------------------------------------------------------

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
