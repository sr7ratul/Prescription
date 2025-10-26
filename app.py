import os
import logging
import tempfile
from datetime import datetime
import pandas as pd
from pymongo import MongoClient
import base64
import io
from flask import Flask, render_template, request, jsonify, send_file, send_from_directory
from weasyprint import HTML
# from whitenoise import WhiteNoise  # ❌ Not needed in Render/Docker environment

# MongoDB connection setup
from dotenv import load_dotenv
load_dotenv()
MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB = os.getenv("MONGO_DB")

client = MongoClient(MONGO_URI)
db = client[MONGO_DB]
pdf_collection = db["prescriptions"]  # new collection

# -------------------------
# App Configuration
# -------------------------
app = Flask(__name__, static_folder='static', static_url_path='/static')
# app.wsgi_app = WhiteNoise(app.wsgi_app, root='static/', prefix='static/')  # Commented for Docker

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

# -------------------------
# Serve static files manually (extra fallback)
# -------------------------
@app.route('/static/<path:filename>')
def staticfiles(filename):
    return send_from_directory(app.static_folder, filename)

# -------------------------
# Load and clean CSV data
# -------------------------
try:
    csv_path = os.path.join(os.path.dirname(__file__), "medicines.csv")

    if not os.path.exists(csv_path):
        raise FileNotFoundError("❌ medicines.csv file not found in root folder")

    df = pd.read_csv(csv_path)

    # ✅ Clean Price (handles various messy formats)
    df['Price_Clean'] = (
        df['Price']
        .astype(str)
        .str.replace(r'.*?:\s*৳\s*', '', regex=True)
        .str.replace(r'[^\d\.]', '', regex=True)
        .replace('', '0')
    )

    # ✅ Fix multi-dot numbers like "10.256.00"
    df['Price_Clean'] = df['Price_Clean'].apply(
        lambda x: x if x.count('.') <= 1 else x[:x.find('.', x.find('.') + 1)]
    )

    df['Price_Clean'] = pd.to_numeric(df['Price_Clean'], errors='coerce').fillna(0.0)

    # ✅ Drop rows with missing Strength
    df_cleaned = df.dropna(subset=['Strength']).copy()

    # ✅ Normalize text columns
    df_cleaned['Generic_Clean'] = df_cleaned['Generic'].astype(str).str.strip().str.lower()
    df_cleaned['Strength'] = df_cleaned['Strength'].astype(str).str.strip()
    df_cleaned['Type'] = df_cleaned['Type'].astype(str).str.strip()

    logger.info(f"✅ Loaded {len(df_cleaned)} medicines from local CSV successfully.")

except Exception as e:
    logger.error(f"❌ Failed to load local CSV data: {e}")
    df_cleaned = pd.DataFrame()

# -------------------------
# Routes
# -------------------------
@app.route('/')
def index():
    if df_cleaned.empty:
        return render_template('index.html', error="Error: Could not load data from local CSV.")

    generic_options = sorted(df_cleaned['Generic_Clean'].dropna().unique().tolist())
    generic_options = [g.title() for g in generic_options]
    return render_template('index.html', generic_options=generic_options)


@app.route('/get_options', methods=['POST'])
def get_options():
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

        options = []
        for _, row in df_filtered.iterrows():
            options.append({
                'generic': row.get('Generic_Clean', '').title(),
                'medicine_name': row.get('Medicine Name', ''),
                'brand': row.get('Brand', ''),
                'price': f"৳ {row['Price_Clean']:.2f}",
                'price_raw': float(row['Price_Clean']),
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
    try:
        data = request.get_json(force=True)
        if isinstance(data, list):
            data = data[0] if data else {}

        patient_name = data.get('patient_name', 'Unknown')
        age = data.get('age', '')
        sex = data.get('sex', '')
        patient_id = data.get('patient_id', '')
        doctor_name = data.get('doctor_name', 'Dr. Unknown')
        specialization = data.get('specialization', '')
        reg_no = data.get('reg_no', '')
        phone = data.get('phone', '')
        medicines = data.get('medicines', [])
        next_appointment = data.get('next_appointment', 'As Advised')
        current_date = datetime.now().strftime('%d-%m-%Y')

        total_cost = 0
        for m in medicines:
            try:
                subtotal = float(m.get('price_raw', 0)) * int(m.get('quantity', 1))
                m['subtotal'] = subtotal
                total_cost += subtotal
            except:
                m['subtotal'] = 0

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

        css_path = os.path.join(app.root_path, 'static', 'css', 'prescription-style.css')
        from weasyprint import CSS

        # ✅ Generate PDF directly in memory (no temp file)
        pdf_bytes = HTML(string=rendered_html, base_url=request.host_url).write_pdf(
            stylesheets=[CSS(css_path)]
        )

        # ✅ Save to MongoDB (Base64 encoded)
        pdf_base64 = base64.b64encode(pdf_bytes).decode('utf-8')
        pdf_doc = {
            "patient_name": patient_name,
            "doctor_name": doctor_name,
            "created_at": datetime.now(),
            "pdf_data": pdf_base64
        }
        pdf_collection.insert_one(pdf_doc)

        # ✅ Return the generated PDF as download
        return send_file(
            io.BytesIO(pdf_bytes),
            as_attachment=True,
            download_name=f"{patient_name}_Prescription.pdf",
            mimetype="application/pdf"
        )

    except Exception as e:
        logger.exception(f"❌ PDF generation failed: {e}")
        return jsonify({"error": str(e)}), 500

# -------------------------
# Main Entry
# -------------------------
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
