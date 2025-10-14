import os
import logging
import json
import tempfile
from datetime import datetime

import pandas as pd
from flask import Flask, render_template, request, jsonify, send_file, send_from_directory
from weasyprint import HTML
from pymongo import MongoClient
from dotenv import load_dotenv
from whitenoise import WhiteNoise  # ✅ for serving static files on Railway

# -------------------------
# App Configuration
# -------------------------
load_dotenv()  # Load .env variables

MONGO_URI = os.environ.get("MONGO_URI")

app = Flask(__name__, static_folder='static', static_url_path='/static')

# ✅ Enable WhiteNoise for serving static files in production
app.wsgi_app = WhiteNoise(app.wsgi_app, root='static/', prefix='static/')

# ✅ Logging setup
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

# -------------------------
# Serve static files manually (extra fallback)
# -------------------------
@app.route('/static/<path:filename>')
def staticfiles(filename):
    return send_from_directory(app.static_folder, filename)  # ✅ ensures static always served


# -------------------------
# MongoDB Connection
# -------------------------
try:
    if not MONGO_URI:
        raise ValueError("MONGO_URI is missing in .env file")

    client = MongoClient(MONGO_URI)
    db = client["prescription_db"]
    collection = db["medicines"]

    all_data = list(collection.find({}, {"_id": 0}))
    if not all_data:
        raise ValueError("No medicine data found in MongoDB collection")

    df_cleaned = pd.DataFrame(all_data)
    df_cleaned['Generic_Clean'] = df_cleaned['Generic'].astype(str).str.strip().str.lower()
    df_cleaned['Strength'] = df_cleaned['Strength'].astype(str).str.strip()
    df_cleaned['Type'] = df_cleaned['Type'].astype(str).str.strip()

    logger.info(f"✅ Loaded {len(df_cleaned)} medicines from MongoDB")

except Exception as e:
    logger.error(f"❌ MongoDB connection failed: {e}")
    df_cleaned = pd.DataFrame()


# -------------------------
# Routes
# -------------------------
@app.route('/')
def index():
    """Main page: Load all unique generic options"""
    if df_cleaned.empty:
        return render_template('index.html', error="Error: Could not load data from MongoDB.")

    generic_options = sorted(df_cleaned['Generic_Clean'].dropna().unique().tolist())
    generic_options = [g.title() for g in generic_options]
    return render_template('index.html', generic_options=generic_options)


@app.route('/get_options', methods=['POST'])
def get_options():
    """Fetch Strength and Type options based on the selected Generic name."""
    try:
        data = request.get_json()
        generic = data.get('generic', '').strip().lower()

        if not generic:
            return jsonify({'strengths': [], 'types': []})

        filtered = df_cleaned[df_cleaned['Generic_Clean'] == generic]
        strengths = sorted(filtered['Strength'].dropna().unique().tolist())
        types = sorted(filtered['Type'].dropna().unique().tolist())

        return jsonify({'strengths': strengths, 'types': types})
    except Exception as e:
        logger.error(f"Error in get_options: {e}")
        return jsonify({'error': 'Failed to fetch options'}), 500


@app.route('/get_details', methods=['POST'])
def get_details():
    """Fetch available brand options for a given generic, strength, and type."""
    try:
        data = request.get_json()
        generic = data.get('generic', '').strip().lower()
        strength = data.get('strength', '').strip()
        drug_type = data.get('type', '').strip()

        df_filtered = df_cleaned[
            (df_cleaned['Generic_Clean'] == generic)
            & (df_cleaned['Strength'] == strength)
            & (df_cleaned['Type'] == drug_type)
        ].copy()

        if df_filtered.empty:
            return jsonify({'error': 'No brands found.'}), 404

        df_filtered['Price_Clean'] = pd.to_numeric(
            df_filtered.get('Price_Clean', df_filtered.get('Price', 0)),
            errors='coerce'
        ).fillna(0.0)

        options = []
        for _, row in df_filtered.iterrows():
            options.append({
                'generic': row.get('Generic_Clean', '').title(),
                'medicine_name': row.get('Medicine Name', ''),
                'brand': row.get('Brand', ''),
                'price': f"{row['Price_Clean']:.2f}",
                'price_raw': row['Price_Clean'],
                'strength': row.get('Strength', ''),
                'type': row.get('Type', ''),
                'quantity': 1,
                'time_schedule': "1+1+1",
                'meal_time': "After Meal"
            })

        return jsonify({'options': options})
    except Exception as e:
        logger.error(f"Error in get_details: {e}")
        return jsonify({'error': 'Failed to fetch medicine details'}), 500


@app.route('/generate_pdf', methods=['POST'])
def generate_pdf():
    """Generate prescription PDF and return it for download."""
    try:
        data = request.get_json(force=True)
        if isinstance(data, list):
            data = data[0] if data else {}

        # Patient and doctor info
        patient_name = data.get('patient_name', 'Unknown')
        age = data.get('age', '')
        sex = data.get('sex', '')
        patient_id = data.get('patient_id', '')
        doctor_name = data.get('doctor_name', 'Dr. Unknown')
        specialization = data.get('specialization', '')
        reg_no = data.get('reg_no', '')
        phone = data.get('phone', '')
        medicines = data.get('medicines', [])
        total_cost = data.get('total_cost', 0)
        next_appointment = data.get('next_appointment', 'As Advised')
        current_date = datetime.now().strftime('%d-%m-%Y')

        rendered_html = render_template(
            'prescription.html',
            patient_name=patient_name,
            age=age,
            sex=sex,
            patient_id=patient_id,
            doctor_name=doctor_name,
            specialization=specialization,
            reg_no=reg_no,
            phone=phone,
            medicines=medicines,
            total_cost=total_cost,
            next_appointment=next_appointment,
            current_date=current_date
        )

        base_url = os.path.join(app.root_path, 'static')

        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
            pdf_path = tmp_file.name

        HTML(string=rendered_html, base_url=base_url).write_pdf(pdf_path)

        return send_file(pdf_path, as_attachment=True, download_name="Prescription.pdf")

    except Exception as e:
        logger.exception(f"❌ PDF generation failed: {e}")
        return jsonify({"error": str(e)}), 500


# -------------------------
# Main Entry
# -------------------------
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True, use_reloader=False)
