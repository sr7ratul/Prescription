import os
import logging
import json
import tempfile
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_file
from weasyprint import HTML
from pymongo import MongoClient
import pandas as pd
from dotenv import load_dotenv # .env ফাইল লোড করার জন্য

# .env ফাইল থেকে এনভায়রনমেন্ট ভ্যারিয়েবল লোড করা হচ্ছে
load_dotenv()

# --- Configuration ---
MONGO_URI = os.environ.get("MONGO_URI")

app = Flask(__name__)
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# --- MongoDB Connection ---
try:
    if not MONGO_URI:
        raise ValueError("MONGO_URI environment variable is not set. Check your .env file.")
        
    client = MongoClient(MONGO_URI)
    db = client["prescription_db"]
    collection = db["medicines"]
    all_data = list(collection.find({}, {"_id": 0}))
    df_cleaned = pd.DataFrame(all_data)
    logger.info(f"✅ Loaded {len(df_cleaned)} medicines from MongoDB")

    # Data normalization for consistent lookups
    df_cleaned['Generic_Clean'] = df_cleaned['Generic'].astype(str).str.strip().str.lower()
    df_cleaned['Strength'] = df_cleaned['Strength'].astype(str).str.strip()
    df_cleaned['Type'] = df_cleaned['Type'].astype(str).str.strip()

except Exception as e:
    logger.error(f"❌ MongoDB connection failed: {e}")
    df_cleaned = pd.DataFrame() # Data not loaded

# -------------------------
# ROUTES
# -------------------------

@app.route('/')
def index():
    """Main page: Load all unique generic options"""
    if df_cleaned.empty:
        return render_template('index.html', error="Error: Data not loaded from MongoDB.")

    # Prepare and sort generic list for the dropdown
    generic_options = sorted(df_cleaned['Generic_Clean'].dropna().unique().tolist())
    # Convert lowercase names back to Title Case for better display
    generic_options = [g.title() for g in generic_options]

    return render_template('index.html', generic_options=generic_options)

@app.route('/get_options', methods=['POST'])
def get_options():
    """Fetch Strength and Type options based on the selected Generic name."""
    data = request.get_json()
    generic = data.get('generic', '').strip().lower()

    if not generic:
        return jsonify({'strengths': [], 'types': []})

    filtered = df_cleaned[df_cleaned['Generic_Clean'] == generic]

    strengths = sorted(filtered['Strength'].dropna().unique().tolist())
    types = sorted(filtered['Type'].dropna().unique().tolist())

    return jsonify({'strengths': strengths, 'types': types})

@app.route('/get_details', methods=['POST'])
def get_details():
    """Fetch available brand options for a given generic, strength, and type."""
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

    # Ensure price is numeric for calculations
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

@app.route('/generate_pdf', methods=['POST'])
def generate_pdf():
    """Generate prescription PDF safely (prevents double download / 0-byte)"""
    try:
        data = request.get_json(force=True)
        if isinstance(data, list):
            data = data[0] if data else {}

        patient_name = data.get('patient_name', 'Unknown')
        age = data.get('age', '')
        sex = data.get('sex', '')
        patient_id = data.get('patient_id', 'NUB-0')
        next_appointment = data.get('next_appointment', 'N/A')
        medicines = data.get('medicines', [])

        # Calculate total estimated cost
        total_cost = 0
        for med in medicines:
            try:
                price_str = med.get('price', med.get('price_raw', 0))
                price = float(price_str)
                quantity = int(med.get('quantity', 1))
                total_cost += price * quantity
            except Exception as e:
                logger.warning(f"⚠️ Price/quantity error for {med}: {e}")

        # Render HTML template
        rendered_html = render_template(
            'prescription.html',
            doctor_name="Dr. SAKIB AL HASAN",
            specialization="MBBS, FCPS (Medicine)",
            reg_no="BMDC-12345",
            phone="01762057707",
            patient_name=patient_name,
            age=age,
            sex=sex,
            patient_id=patient_id,
            next_appointment=next_appointment,
            medicines=medicines,
            total_cost=total_cost,
            current_date=datetime.now().strftime("%d %B %Y")
        )

        BASE_URL = request.url_root
        HTML(string=rendered_html, base_url=BASE_URL).write_pdf(tmp_file.name)

        # ✅ Use `with` to ensure PDF is fully written
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
            HTML(string=rendered_html, base_url=BASE_URL).write_pdf(tmp_file.name)
            tmp_file_path = tmp_file.name

        # Send the file once and delete after sending
        response = send_file(tmp_file_path, as_attachment=True, download_name="Prescription.pdf")
        @response.call_on_close
        def cleanup():
            try:
                os.remove(tmp_file_path)
            except:
                pass

        return response

    except Exception as e:
        logger.exception(f"❌ PDF generation failed: {e}")
        return jsonify({'error': str(e)}), 500

# -------------------------
# MAIN ENTRY
# -------------------------
if __name__ == '__main__':
    app.run(debug=True, use_reloader=False)
