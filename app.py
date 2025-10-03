# app.py

from flask import Flask, render_template, request, redirect, url_for, session, flash, g
import sqlite3
import os
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
import json

# NEW: Imports for scheduling and database backup
from threading import Thread
import time
import shutil

app = Flask(__name__)
app.secret_key = b'clave_fija_produccion_123456'
app.config['DATABASE'] = 'hospital_checklist.db'
app.config['BACKUP_FOLDER'] = 'BACKUP_BD' # NEW: Define the backup folder

# Database setup
def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(app.config['DATABASE'])
        db.row_factory = sqlite3.Row
    return db

def init_db():
    with app.app_context():
        db = get_db()
        cursor = db.cursor()
        
        # Create existing tables (users, reports)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role TEXT NOT NULL,
                hospital_id TEXT
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                hospital_id TEXT NOT NULL,
                date TEXT NOT NULL,
                checklist_data TEXT NOT NULL,
                observations TEXT,
                met_goal INTEGER,
                operations_performed INTEGER,
                submitted_by INTEGER,
                submitted_at TEXT,
                FOREIGN KEY (submitted_by) REFERENCES users(id)
            )
        ''')
        
        # NEW: Create logs table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                action TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                ip_address TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')
        
        # Insert initial data if tables are empty
        if cursor.execute('SELECT COUNT(*) FROM users').fetchone()[0] == 0:
            users = [
                ('admin', generate_password_hash('admin123'), 'admin', None),
                ('hgz24', generate_password_hash('pass24'), 'hospital', 'hgz24'),
                ('hgz27', generate_password_hash('pass27'), 'hospital', 'hgz27'),
                ('hgz29', generate_password_hash('pass29'), 'hospital', 'hgz29'),
                ('hgz48', generate_password_hash('pass48'), 'hospital', 'hgz48'),
                ('gineco3a', generate_password_hash('pass3a'), 'hospital', 'gineco3a')
            ]
            cursor.executemany('INSERT INTO users (username, password, role, hospital_id) VALUES (?, ?, ?, ?)', users)
            db.commit()

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

# Helper function to log actions
def log_action(user_id, action, ip_address=None):
    db = get_db()
    try:
        db.execute(
            'INSERT INTO logs (user_id, action, timestamp, ip_address) VALUES (?, ?, ?, ?)',
            (user_id, action, datetime.now().isoformat(), ip_address)
        )
        db.commit()
    except Exception as e:
        print(f"Error logging action: {e}")
        db.rollback()

# Constants (unchanged)
HOSPITAL_NAMES = {
    'hgz24': 'HGZ24',
    'hgz27': 'HGZ27',
    'hgz29': 'HGZ29',
    'hgz48': 'HGZ48',
    'gineco3a': 'Gineco 3A'
}

CHECKLIST_ITEMS = {
    'Conservación': ['maquina de anestesia', 'aire acondicionado', 'agua', 'limpieza'],
    'Personal': ['vacaciones', 'ausentismo'],
    'Finanzas': ['pagos a proveedores', 'facturas pendientes'],
    'Abasto': ['kits', 'medicamentos'],
    'Tics': ['red', 'sistema', 'impresora', 'equipo dañado']
}

OPERATIONS_PER_FORTNIGHT = 112
OPERATIONS_PER_WEEK = OPERATIONS_PER_FORTNIGHT / 2
OPERATIONS_PER_DAY = 7

# Utility functions (unchanged)
def format_date(date=None):
    date = date or datetime.now()
    return date.strftime('%Y-%m-%d')

def get_default_checklist():
    default_items = {item: False for category in CHECKLIST_ITEMS.values() for item in category}
    for category in CHECKLIST_ITEMS:
        default_items[category + '_otro_checkbox'] = False
        default_items[category + '_otro_text'] = ''
    return default_items

# Routes
@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user_ip = request.remote_addr # Get user's IP address
        
        db = get_db()
        user = db.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            session['hospital_id'] = user['hospital_id']
            log_action(user['id'], 'successful login', user_ip) # Log successful login
            
            if user['role'] == 'admin':
                return redirect(url_for('dashboard'))
            else:
                return redirect(url_for('hospital_checklist'))
        else:
            flash('Usuario o contraseña incorrectos.', 'error')
            # Log failed login attempt (user_id is None since login failed)
            log_action(None, f'failed login attempt for username: {username}', user_ip)
    
    return render_template('login.html', hospital_names=HOSPITAL_NAMES)

@app.route('/logout')
def logout():
    user_id = session.get('user_id')
    user_ip = request.remote_addr
    if user_id:
        log_action(user_id, 'logout', user_ip) # Log logout
    session.clear()
    return redirect(url_for('login'))

@app.route('/checklist', methods=['GET', 'POST'])
def hospital_checklist():
    if 'user_id' not in session or session['role'] != 'hospital':
        return redirect(url_for('login'))
    
    hospital_id = session['hospital_id']
    today = format_date()
    user_id = session['user_id']
    user_ip = request.remote_addr
    
    db = get_db()
    
    if request.method == 'POST':
        # Process form submission
        checklist_data = {}
        for category, items in CHECKLIST_ITEMS.items():
            for item in items:
                checklist_data[item] = request.form.get(item) == 'on'
            # Handle 'Otro' checkbox and text
            otro_checkbox_name = f"{category}_otro_checkbox"
            otro_text_name = f"{category}_otro_text"
            checklist_data[otro_checkbox_name] = request.form.get(otro_checkbox_name) == 'on'
            checklist_data[otro_text_name] = request.form.get(otro_text_name, '')
        
        observations = request.form.get('observations', '')
        met_goal_str = request.form.get('met_goal')
        
        operations_performed = None
        if met_goal_str is None:
            flash('Por favor, indique si se cumplió con la meta.', 'error')
            # Re-render form with existing data to show error
            report = db.execute(
                'SELECT * FROM reports WHERE hospital_id = ? AND date = ?',
                (hospital_id, today)
            ).fetchone()
            if report:
                checklist_data = json.loads(report['checklist_data'])
                observations = report['observations'] or ''
                met_goal = report['met_goal']
                operations_performed = report['operations_performed']
            else:
                checklist_data = get_default_checklist()
                observations = ''
                met_goal = None
                operations_performed = None
            
            # Calculate unit percentage for re-render
            total_items = 0
            checked_items_count = 0
            for category, items in CHECKLIST_ITEMS.items():
                for item in items:
                    total_items += 1
                    if checklist_data.get(item):
                        checked_items_count += 1
                
                otro_checkbox_name = f"{category}_otro_checkbox"
                otro_text_name = f"{category}_otro_text"
                
                if checklist_data.get(otro_text_name):
                    total_items += 1
                    if checklist_data.get(otro_checkbox_name):
                        checked_items_count += 1

            unit_percentage = (checked_items_count / total_items) * 100 if total_items > 0 else 0

            return render_template(
                'checklist.html',
                hospital_name=HOSPITAL_NAMES.get(hospital_id, hospital_id),
                today=today,
                checklist_items=CHECKLIST_ITEMS,
                checklist_data=checklist_data,
                observations=observations,
                met_goal=met_goal,
                operations_performed=operations_performed,
                unit_percentage=unit_percentage
            )


        met_goal = met_goal_str == 'true'

        if not met_goal:
            operations_str = request.form.get('operations_performed')
            if not operations_str:
                flash('Por favor, ingrese el número de operaciones realizadas si la meta no se cumplió.', 'error')
                report = db.execute(
                    'SELECT * FROM reports WHERE hospital_id = ? AND date = ?',
                    (hospital_id, today)
                ).fetchone()
                if report:
                    checklist_data = json.loads(report['checklist_data'])
                    observations = report['observations'] or ''
                    met_goal = report['met_goal']
                    operations_performed = report['operations_performed']
                else:
                    checklist_data = get_default_checklist()
                    observations = ''
                    met_goal = None
                    operations_performed = None

                total_items = 0
                checked_items_count = 0
                for category, items in CHECKLIST_ITEMS.items():
                    for item in items:
                        total_items += 1
                        if checklist_data.get(item):
                            checked_items_count += 1
                    
                    otro_checkbox_name = f"{category}_otro_checkbox"
                    otro_text_name = f"{category}_otro_text"
                    
                    if checklist_data.get(otro_text_name):
                        total_items += 1
                        if checklist_data.get(otro_checkbox_name):
                            checked_items_count += 1

                unit_percentage = (checked_items_count / total_items) * 100 if total_items > 0 else 0

                return render_template(
                    'checklist.html',
                    hospital_name=HOSPITAL_NAMES.get(hospital_id, hospital_id),
                    today=today,
                    checklist_items=CHECKLIST_ITEMS,
                    checklist_data=checklist_data,
                    observations=observations,
                    met_goal=met_goal,
                    operations_performed=operations_performed,
                    unit_percentage=unit_percentage
                )
            try:
                operations_performed = int(operations_str)
                if operations_performed > 7 or operations_performed < 0:
                    flash('El número de operaciones no puede ser mayor a 7 ni negativo.', 'error')
                    report = db.execute(
                        'SELECT * FROM reports WHERE hospital_id = ? AND date = ?',
                        (hospital_id, today)
                    ).fetchone()
                    if report:
                        checklist_data = json.loads(report['checklist_data'])
                        observations = report['observations'] or ''
                        met_goal = report['met_goal']
                        operations_performed = report['operations_performed']
                    else:
                        checklist_data = get_default_checklist()
                        observations = ''
                        met_goal = None
                        operations_performed = None

                    total_items = 0
                    checked_items_count = 0
                    for category, items in CHECKLIST_ITEMS.items():
                        for item in items:
                            total_items += 1
                            if checklist_data.get(item):
                                checked_items_count += 1
                        
                        otro_checkbox_name = f"{category}_otro_checkbox"
                        otro_text_name = f"{category}_otro_text"
                        
                        if checklist_data.get(otro_text_name):
                            total_items += 1
                            if checklist_data.get(otro_checkbox_name):
                                checked_items_count += 1

                    unit_percentage = (checked_items_count / total_items) * 100 if total_items > 0 else 0

                    return render_template(
                        'checklist.html',
                        hospital_name=HOSPITAL_NAMES.get(hospital_id, hospital_id),
                        today=today,
                        checklist_items=CHECKLIST_ITEMS,
                        checklist_data=checklist_data,
                        observations=observations,
                        met_goal=met_goal,
                        operations_performed=operations_performed,
                        unit_percentage=unit_percentage
                    )
            except ValueError:
                flash('El número de operaciones debe ser un valor numérico.', 'error')
                report = db.execute(
                    'SELECT * FROM reports WHERE hospital_id = ? AND date = ?',
                    (hospital_id, today)
                ).fetchone()
                if report:
                    checklist_data = json.loads(report['checklist_data'])
                    observations = report['observations'] or ''
                    met_goal = report['met_goal']
                    operations_performed = report['operations_performed']
                else:
                    checklist_data = get_default_checklist()
                    observations = ''
                    met_goal = None
                    operations_performed = None

                total_items = 0
                checked_items_count = 0
                for category, items in CHECKLIST_ITEMS.items():
                    for item in items:
                        total_items += 1
                        if checklist_data.get(item):
                            checked_items_count += 1
                    
                    otro_checkbox_name = f"{category}_otro_checkbox"
                    otro_text_name = f"{category}_otro_text"
                    
                    if checklist_data.get(otro_text_name):
                        total_items += 1
                        if checklist_data.get(otro_checkbox_name):
                            checked_items_count += 1

                unit_percentage = (checked_items_count / total_items) * 100 if total_items > 0 else 0

                return render_template(
                    'checklist.html',
                    hospital_name=HOSPITAL_NAMES.get(hospital_id, hospital_id),
                    today=today,
                    checklist_items=CHECKLIST_ITEMS,
                    checklist_data=checklist_data,
                    observations=observations,
                    met_goal=met_goal,
                    operations_performed=operations_performed,
                    unit_percentage=unit_percentage
                )
        
        try:
            checklist_data_json = json.dumps(checklist_data)

            existing_report = db.execute(
                'SELECT id FROM reports WHERE hospital_id = ? AND date = ?',
                (hospital_id, today)
            ).fetchone()
            
            if existing_report:
                db.execute('''
                    UPDATE reports 
                    SET checklist_data = ?, observations = ?, met_goal = ?, operations_performed = ?, submitted_at = ?
                    WHERE id = ?
                ''', (
                    checklist_data_json,
                    observations,
                    met_goal,
                    operations_performed,
                    datetime.now().isoformat(),
                    existing_report['id']
                ))
                log_action(user_id, f'updated daily report for {hospital_id} on {today}', user_ip) # Log update
            else:
                db.execute('''
                    INSERT INTO reports (
                        hospital_id, date, checklist_data, observations, met_goal, operations_performed, submitted_by, submitted_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    hospital_id,
                    today,
                    checklist_data_json,
                    observations,
                    met_goal,
                    operations_performed,
                    session['user_id'],
                    datetime.now().isoformat()
                ))
                log_action(user_id, f'submitted daily report for {hospital_id} on {today}', user_ip) # Log submission
            
            db.commit()
            flash('¡Reporte guardado exitosamente!', 'success')
        except Exception as e:
            db.rollback()
            flash(f'Error al guardar el reporte: {e}. Intente de nuevo.', 'error')
            log_action(user_id, f'error saving report for {hospital_id} on {today}: {e}', user_ip) # Log error
    
    report = db.execute(
        'SELECT * FROM reports WHERE hospital_id = ? AND date = ?',
        (hospital_id, today)
    ).fetchone()
    
    if report:
        checklist_data = json.loads(report['checklist_data'])
        observations = report['observations'] or ''
        met_goal = report['met_goal']
        operations_performed = report['operations_performed']
    else:
        checklist_data = get_default_checklist()
        observations = ''
        met_goal = None
        operations_performed = None

    total_items = 0
    checked_items_count = 0
    for category, items in CHECKLIST_ITEMS.items():
        for item in items:
            total_items += 1
            if checklist_data.get(item):
                checked_items_count += 1
        
        otro_checkbox_name = f"{category}_otro_checkbox"
        otro_text_name = f"{category}_otro_text"
        
        if checklist_data.get(otro_text_name) and checklist_data[otro_text_name].strip() != '':
            total_items += 1
            if checklist_data.get(otro_checkbox_name):
                checked_items_count += 1
    
    unit_percentage = (checked_items_count / total_items) * 100 if total_items > 0 else 0
    
    return render_template(
        'checklist.html',
        hospital_name=HOSPITAL_NAMES.get(hospital_id, hospital_id),
        today=today,
        checklist_items=CHECKLIST_ITEMS,
        checklist_data=checklist_data,
        observations=observations,
        met_goal=met_goal,
        operations_performed=operations_performed,
        unit_percentage=unit_percentage
    )

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    
    # Optional: Log access to dashboard
    log_action(session['user_id'], 'accessed dashboard', request.remote_addr)

    db = get_db()
    today = datetime.now()
    today_str = today.strftime('%Y-%m-%d')

    fortnight_start_date = today - timedelta(days=13)
    fortnight_start_date_str = fortnight_start_date.strftime('%Y-%m-%d')

    daily_reports = db.execute(
        'SELECT * FROM reports WHERE date = ?', (today_str,)
    ).fetchall()

    submitted_hospitals = {r['hospital_id'] for r in daily_reports}
    
    missing_reports = []
    for hospital_id in HOSPITAL_NAMES:
        if hospital_id not in submitted_hospitals:
            missing_reports.append(f"¡Atención! {HOSPITAL_NAMES[hospital_id]} no ha enviado su reporte diario.")
    
    total_hospitals = len(HOSPITAL_NAMES)
    completed_reports = len(daily_reports)
    progress_percentage = (completed_reports / total_hospitals) * 100 if total_hospitals > 0 else 0
    
    if progress_percentage >= 100:
        progress_status = 'green'
    elif progress_percentage >= 50:
        progress_status = 'yellow'
    else:
        progress_status = 'red'

    hospital_daily_status = {}
    for hospital_id in HOSPITAL_NAMES:
        report_today = next((r for r in daily_reports if r['hospital_id'] == hospital_id), None)
        if report_today:
            hospital_daily_status[hospital_id] = {
                'met_goal': report_today['met_goal'],
                'operations_performed': report_today['operations_performed']
            }
        else:
            hospital_daily_status[hospital_id] = None

    total_daily_operations = 0
    for report in daily_reports:
        met_goal = report['met_goal']
        operations_performed = report['operations_performed']
        
        if operations_performed is not None:
            total_daily_operations += operations_performed
        elif met_goal == 1:
            total_daily_operations += OPERATIONS_PER_DAY

    # NEW: Calculate total operations for the last 7 days (weekly)
    week_start_date = today - timedelta(days=6) # 7 days including today
    week_start_date_str = week_start_date.strftime('%Y-%m-%d')

    weekly_reports = db.execute(
        'SELECT met_goal, operations_performed FROM reports WHERE date BETWEEN ? AND ?',
        (week_start_date_str, today_str)
    ).fetchall()

    total_weekly_operations = 0
    for report in weekly_reports:
        operations_count = report['operations_performed']
        if report['met_goal'] == 1:
            operations_count = OPERATIONS_PER_DAY
        
        if operations_count is not None:
            total_weekly_operations += operations_count
    
    fortnight_reports = db.execute(
        'SELECT hospital_id, date, met_goal, operations_performed FROM reports WHERE date BETWEEN ? AND ?',
        (fortnight_start_date_str, today_str)
    ).fetchall()

    total_fortnight_operations = 0
    # Initialize dictionary to store accumulated operations per hospital for the fortnight
    hospital_fortnight_operations = {h_id: {'name': HOSPITAL_NAMES[h_id], 'total_operations': 0} for h_id in HOSPITAL_NAMES.keys()}

    for report in fortnight_reports:
        operations_count = report['operations_performed']
        if report['met_goal'] == 1:
            operations_count = OPERATIONS_PER_DAY
        
        if operations_count is not None:
            total_fortnight_operations += operations_count
            hospital_fortnight_operations[report['hospital_id']]['total_operations'] += operations_count

    fortnight_goal_percentage = (total_fortnight_operations / OPERATIONS_PER_FORTNIGHT) * 100 if OPERATIONS_PER_FORTNIGHT > 0 else 0

    hospital_reports = {}
    for hospital_id in HOSPITAL_NAMES:
        report = db.execute('''
            SELECT * FROM reports 
            WHERE hospital_id = ? 
            ORDER BY date DESC 
            LIMIT 1
        ''', (hospital_id,)).fetchone()
        
        if report:
            loaded_checklist_data = json.loads(report['checklist_data'])
            
            total_items = 0
            checked_items_count = 0
            for category, items in CHECKLIST_ITEMS.items():
                for item in items:
                    total_items += 1
                    if loaded_checklist_data.get(item):
                        checked_items_count += 1
                
                otro_checkbox_name = f"{category}_otro_checkbox"
                otro_text_name = f"{category}_otro_text"
                
                if loaded_checklist_data.get(otro_text_name) and loaded_checklist_data[otro_text_name].strip() != '':
                    total_items += 1
                    if loaded_checklist_data.get(otro_checkbox_name):
                        checked_items_count += 1

            unit_percentage_hospital = (checked_items_count / total_items) * 100 if total_items > 0 else 0

            hospital_reports[hospital_id] = {
                'date': report['date'],
                'checklist_data': loaded_checklist_data,
                'observations': report['observations'] or '',
                'met_goal': report['met_goal'],
                'operations_performed': report['operations_performed'],
                'unit_percentage': unit_percentage_hospital
            }
        else:
            hospital_reports[hospital_id] = {
                'date': 'N/A',
                'checklist_data': {},
                'observations': 'N/A',
                'met_goal': None,
                'operations_performed': None,
                'unit_percentage': 0
            }


    return render_template(
        'dashboard.html',
        today=today_str,
        hospital_names=HOSPITAL_NAMES,
        operations_fortnight=OPERATIONS_PER_FORTNIGHT,
        operations_week=OPERATIONS_PER_WEEK,
        operations_day=OPERATIONS_PER_DAY,
        missing_reports=missing_reports,
        progress_percentage=round(progress_percentage, 1),
        progress_status=progress_status,
        completed_reports=completed_reports,
        total_hospitals=total_hospitals,
        hospital_reports=hospital_reports,
        checklist_items_structure=CHECKLIST_ITEMS,
        total_daily_operations=total_daily_operations,
        total_weekly_operations=total_weekly_operations, # Added for weekly goal
        total_fortnight_operations=total_fortnight_operations,
        fortnight_goal_percentage=round(fortnight_goal_percentage, 1),
        hospital_daily_status=hospital_daily_status,
        hospital_fortnight_operations=hospital_fortnight_operations # NEW: Pass this to the template
    )

@app.route('/statistics', methods=['GET', 'POST'])
def statistics():
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))

    # Optional: Log access to statistics page
    log_action(session['user_id'], 'accessed statistics page', request.remote_addr)

    db = get_db()
    
    start_date_str = request.form.get('start_date')
    end_date_str = request.form.get('end_date')

    if not start_date_str or not end_date_str:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=6)
        start_date_str = start_date.strftime('%Y-%m-%d')
        end_date_str = end_date.strftime('%Y-%m-%d')
    else:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
            if start_date > end_date:
                flash('La fecha de inicio no puede ser posterior a la fecha de fin.', 'error')
                end_date = datetime.now()
                start_date = end_date - timedelta(days=6)
                start_date_str = start_date.strftime('%Y-%m-%d')
                end_date_str = end_date.strftime('%Y-%m-%d')

        except ValueError:
            flash('Formato de fecha inválido. Use AAAA-MM-DD.', 'error')
            end_date = datetime.now()
            start_date = end_date - timedelta(days=6)
            start_date_str = start_date.strftime('%Y-%m-%d')
            end_date_str = end_date.strftime('%Y-%m-%d')
    
    query = """
        SELECT hospital_id, date, checklist_data, observations, met_goal, operations_performed
        FROM reports
        WHERE date BETWEEN ? AND ?
        ORDER BY date ASC, hospital_id ASC
    """
    raw_reports = db.execute(query, (start_date_str, end_date_str)).fetchall()

    processed_reports = []
    daily_total_operations = {}
    daily_unit_completion = {}
    # historical_goals_data is now structured for counting 'met goals' per hospital
    historical_goals_data = {hospital_id: {'labels': [], 'data': []} for hospital_id in HOSPITAL_NAMES.keys()}
    checklist_item_analysis = {}

    all_checklist_items = []
    for category, items in CHECKLIST_ITEMS.items():
        for item in items:
            all_checklist_items.append(item)
        all_checklist_items.append(f"{category}_otro_checkbox")

    for item_name in all_checklist_items:
        checklist_item_analysis[item_name] = {'checked': 0, 'total': 0}


    for report in raw_reports:
        hospital_id = report['hospital_id']
        report_date = report['date']
        loaded_checklist_data = json.loads(report['checklist_data'])

        total_items_report = 0
        checked_items_count_report = 0
        for category, items in CHECKLIST_ITEMS.items():
            for item in items:
                total_items_report += 1
                if loaded_checklist_data.get(item):
                    checked_items_count_report += 1
            
            otro_checkbox_name = f"{category}_otro_checkbox"
            otro_text_name = f"{category}_otro_text"
            
            if loaded_checklist_data.get(otro_text_name) and loaded_checklist_data[otro_text_name].strip() != '':
                total_items_report += 1
                if loaded_checklist_data.get(otro_checkbox_name):
                    checked_items_count_report += 1

        unit_percentage = (checked_items_count_report / total_items_report) * 100 if total_items_report > 0 else 0


        operations_count = report['operations_performed']
        if report['met_goal'] == 1:
            operations_count = OPERATIONS_PER_DAY

        processed_reports.append({
            'hospital_id': hospital_id,
            'hospital_name': HOSPITAL_NAMES.get(hospital_id, hospital_id),
            'date': report_date,
            'met_goal': report['met_goal'],
            'operations_performed': operations_count,
            'unit_percentage': round(unit_percentage, 1),
            'observations': report['observations'],
            'checklist_data': loaded_checklist_data
        })

        if report_date not in daily_total_operations:
            daily_total_operations[report_date] = 0
        if operations_count is not None:
            daily_total_operations[report_date] += operations_count

        if report_date not in daily_unit_completion:
            daily_unit_completion[report_date] = {'total_percentage': 0, 'count': 0}
        daily_unit_completion[report_date]['total_percentage'] += unit_percentage
        daily_unit_completion[report_date]['count'] += 1

        # For historical goals: store 1 for met goal, 0 for not met. We'll count these on the frontend.
        # This structure is maintained for flexibility, even if the current chart just counts '1's.
        if report_date not in historical_goals_data[hospital_id]['labels']:
            historical_goals_data[hospital_id]['labels'].append(report_date)
            historical_goals_data[hospital_id]['data'].append(1 if report['met_goal'] == 1 else 0)
        else:
            # If a hospital has multiple reports on the same day (shouldn't happen with current logic, but for robustness)
            # we'll just keep the last one.
            idx = historical_goals_data[hospital_id]['labels'].index(report_date)
            historical_goals_data[hospital_id]['data'][idx] = 1 if report['met_goal'] == 1 else 0

        for category, items in CHECKLIST_ITEMS.items():
            for item in items:
                checklist_item_analysis[item]['total'] += 1
                if loaded_checklist_data.get(item) == True:
                    checklist_item_analysis[item]['checked'] += 1
            
            otro_checkbox_name = f"{category}_otro_checkbox"
            otro_text_name = f"{category}_otro_text"
            
            if loaded_checklist_data.get(otro_text_name) and loaded_checklist_data[otro_text_name].strip() != '':
                checklist_item_analysis[otro_checkbox_name]['total'] += 1
                if loaded_checklist_data.get(otro_checkbox_name) == True:
                    checklist_item_analysis[otro_checkbox_name]['checked'] += 1
    
    for date, data in daily_unit_completion.items():
        if data['count'] > 0:
            daily_unit_completion[date] = round(data['total_percentage'] / data['count'], 1)
        else:
            daily_unit_completion[date] = 0

    chart_data_operations = {
        'labels': sorted(daily_total_operations.keys()),
        'data': [daily_total_operations[date] for date in sorted(daily_total_operations.keys())]
    }

    chart_data_unit_completion = {
        'labels': sorted(daily_unit_completion.keys()),
        'data': [daily_unit_completion[date] for date in sorted(daily_unit_completion.keys())]
    }

    # Prepare data for the new bar chart. We need to iterate through all hospitals
    # and for each, count how many times 'met_goal' was true (1)
    chart_data_historical_goals = {
        'labels': [], # This will be filled with hospital names
        'datasets': [] # This will contain one dataset for the bar chart
    }

    hospital_met_goal_counts = {}
    for hospital_id in HOSPITAL_NAMES.keys():
        hospital_met_goal_counts[hospital_id] = 0
    
    # Iterate through all raw reports in the date range to count met goals per hospital
    for report in raw_reports:
        if report['met_goal'] == 1:
            hospital_met_goal_counts[report['hospital_id']] = hospital_met_goal_counts.get(report['hospital_id'], 0) + 1
    
    # Populate the chart_data_historical_goals for the bar chart
    chart_data_historical_goals['labels'] = [HOSPITAL_NAMES.get(h_id, h_id) for h_id in sorted(hospital_met_goal_counts.keys())]
    chart_data_historical_goals['datasets'].append({
        'label': 'Veces Meta Cumplida',
        'data': [hospital_met_goal_counts[h_id] for h_id in sorted(hospital_met_goal_counts.keys())],
        # Colors can be handled on the frontend or fixed here if desired
    })


    detailed_checklist_percentages = []
    for item_name, counts in checklist_item_analysis.items():
        if counts['total'] > 0:
            percentage = (counts['checked'] / counts['total']) * 100 if counts['total'] > 0 else 0
            display_name = item_name.replace('_otro_checkbox', ' (Otro)').replace('_', ' ').capitalize()
            detailed_checklist_percentages.append({
                'item': display_name,
                'percentage': round(percentage, 1),
                'checked_count': counts['checked'],
                'total_count': counts['total']
            })
    detailed_checklist_percentages.sort(key=lambda x: x['percentage'], reverse=True)


    return render_template(
        'statistics.html',
        hospital_names=HOSPITAL_NAMES,
        reports=processed_reports,
        start_date=start_date_str,
        end_date=end_date_str,
        chart_data_operations=json.dumps(chart_data_operations),
        chart_data_unit_completion=json.dumps(chart_data_unit_completion),
        chart_data_historical_goals=json.dumps(chart_data_historical_goals),
        detailed_checklist_percentages=detailed_checklist_percentages,
        checklist_items_structure=CHECKLIST_ITEMS
    )

@app.route('/hospital_trends', methods=['GET', 'POST'])
def hospital_trends():
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))

    # Optional: Log access to hospital trends page
    log_action(session['user_id'], 'accessed hospital trends page', request.remote_addr)

    db = get_db()
    
    selected_hospital_id = request.form.get('hospital_id') or request.args.get('hospital_id')
    start_date_str = request.form.get('start_date') or request.args.get('start_date')
    end_date_str = request.form.get('end_date') or request.args.get('end_date')

    if not start_date_str or not end_date_str:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=29)
        start_date_str = start_date.strftime('%Y-%m-%d')
        end_date_str = end_date.strftime('%Y-%m-%d')
    else:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
            if start_date > end_date:
                flash('La fecha de inicio no puede ser posterior a la fecha de fin.', 'error')
                end_date = datetime.now()
                start_date = end_date - timedelta(days=29)
                start_date_str = start_date.strftime('%Y-%m-%d')
                end_date_str = end_date.strftime('%Y-%m-%d')
        except ValueError:
            flash('Formato de fecha inválido. Use AAAA-MM-DD.', 'error')
            end_date = datetime.now()
            start_date = end_date - timedelta(days=29)
            start_date_str = start_date.strftime('%Y-%m-%d')
            end_date_str = end_date.strftime('%Y-%m-%d')

    hospital_reports_data = []
    unit_percentage_chart_data = {'labels': [], 'data': []}
    met_goal_chart_data = {'labels': [], 'data': []}
    recurring_problems = {}

    if selected_hospital_id:
        query = """
            SELECT date, checklist_data, observations, met_goal, operations_performed
            FROM reports
            WHERE hospital_id = ? AND date BETWEEN ? AND ?
            ORDER BY date ASC
        """
        raw_reports = db.execute(query, (selected_hospital_id, start_date_str, end_date_str)).fetchall()

        for report in raw_reports:
            report_date = report['date']
            loaded_checklist_data = json.loads(report['checklist_data'])

            total_items_report = 0
            checked_items_count_report = 0
            
            unchecked_items_today = []

            for category, items in CHECKLIST_ITEMS.items():
                for item in items:
                    total_items_report += 1
                    if loaded_checklist_data.get(item):
                        checked_items_count_report += 1
                    else:
                        unchecked_items_today.append(f"{category}: {item}")
                
                otro_checkbox_name = f"{category}_otro_checkbox"
                otro_text_name = f"{category}_otro_text"
                
                if loaded_checklist_data.get(otro_text_name) and loaded_checklist_data[otro_text_name].strip() != '':
                    total_items_report += 1
                    if loaded_checklist_data.get(otro_checkbox_name):
                        checked_items_count_report += 1
                    else:
                        unchecked_items_today.append(f"{category}: Otro ({loaded_checklist_data[otro_text_name]})")

            unit_percentage = (checked_items_count_report / total_items_report) * 100 if total_items_report > 0 else 0

            hospital_reports_data.append({
                'date': report_date,
                'met_goal': report['met_goal'],
                'operations_performed': report['operations_performed'],
                'unit_percentage': round(unit_percentage, 1),
                'observations': report['observations'] or ''
            })

            unit_percentage_chart_data['labels'].append(report_date)
            unit_percentage_chart_data['data'].append(round(unit_percentage, 1))

            met_goal_chart_data['labels'].append(report_date)
            met_goal_chart_data['data'].append(1 if report['met_goal'] == 1 else 0)

            for item in unchecked_items_today:
                recurring_problems[item] = recurring_problems.get(item, 0) + 1
            
            observations_text = report['observations'].lower()
            keywords = ['falla de red', 'falta de personal', 'maquina dañada', 'agua', 'aire acondicionado', 'limpieza', 'vacaciones', 'ausentismo', 'pagos', 'facturas', 'kits', 'medicamentos', 'sistema', 'impresora', 'equipo dañado']
            for keyword in keywords:
                if keyword in observations_text:
                    recurring_problems[f"Observación: {keyword}"] = recurring_problems.get(f"Observación: {keyword}", 0) + 1

    sorted_recurring_problems = sorted(recurring_problems.items(), key=lambda item: item[1], reverse=True)

    return render_template(
        'hospital_trends.html',
        hospital_names=HOSPITAL_NAMES,
        selected_hospital_id=selected_hospital_id,
        selected_hospital_name=HOSPITAL_NAMES.get(selected_hospital_id, 'Seleccione un Hospital'),
        start_date=start_date_str,
        end_date=end_date_str,
        hospital_reports_data=hospital_reports_data,
        unit_percentage_chart_data=json.dumps(unit_percentage_chart_data),
        met_goal_chart_data=json.dumps(met_goal_chart_data),
        recurring_problems=sorted_recurring_problems
    )

# NEW: Add a route for viewing logs (admin only)
@app.route('/logs')
def view_logs():
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))

    db = get_db()
    logs = db.execute('''
        SELECT 
            l.id, 
            u.username, 
            l.action, 
            l.timestamp, 
            l.ip_address 
        FROM logs l
        LEFT JOIN users u ON l.user_id = u.id
        ORDER BY l.timestamp DESC
        LIMIT 100
    ''').fetchall() # Fetch last 100 logs

    return render_template('logs.html', logs=logs)

# NEW: Backup logic
def backup_database():
    """Performs a backup of the database."""
    # Ensure the backup directory exists
    backup_folder = app.config['BACKUP_FOLDER']
    if not os.path.exists(backup_folder):
        os.makedirs(backup_folder)

    # Generate a timestamped filename
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    backup_filename = f"hospital_checklist_{timestamp}.db"
    backup_path = os.path.join(backup_folder, backup_filename)

    # Use a separate connection for the backup to avoid locking issues
    source_db = app.config['DATABASE']
    with sqlite3.connect(source_db) as conn_source:
        with sqlite3.connect(backup_path) as conn_backup:
            conn_source.backup(conn_backup)
    
    print(f"Database backed up to {backup_path}")

# NEW: Scheduled task function
def schedule_daily_backup():
    """Runs a daily backup task in a separate thread."""
    while True:
        now = datetime.now()
        # Schedule the backup for the next day at a specific time (e.g., 2:00 AM)
        # You can adjust the time as needed
        next_backup = now.replace(hour=2, minute=0, second=0, microsecond=0)
        if now > next_backup:
            # If the scheduled time has passed for today, schedule it for tomorrow
            next_backup += timedelta(days=1)
        
        time_to_wait = (next_backup - now).total_seconds()
        print(f"Next backup scheduled for {next_backup}. Waiting for {time_to_wait/3600:.2f} hours...")
        time.sleep(time_to_wait)
        
        with app.app_context():
            backup_database()

@app.route('/backup_bd', methods=['GET'])
def manual_backup():
    """Route to trigger a manual backup (admin only)."""
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    
    try:
        backup_database()
        log_action(session['user_id'], 'manual database backup triggered', request.remote_addr)
        flash('Respaldo de la base de datos creado exitosamente.', 'success')
    except Exception as e:
        log_action(session['user_id'], f'manual database backup failed: {e}', request.remote_addr)
        flash(f'Error al crear el respaldo: {e}', 'error')
    
    return redirect(url_for('dashboard'))

if __name__ == '__main__':
    init_db()
    backup_thread = Thread(target=schedule_daily_backup, daemon=True)
    backup_thread.start()
    app.run(host='0.0.0.0', port=5000, debug=True)