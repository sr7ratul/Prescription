// static/js/app.js
let prescriptionItems = [];

function clearSelect(sel){ 
  sel.innerHTML='<option value="">-- Select --</option>'; 
}
function addOption(sel,v,t){ 
  const o=document.createElement('option'); 
  o.value=v; 
  o.textContent=t; 
  sel.appendChild(o); 
}

function fetchDependentOptions(e){
  const generic=document.getElementById('generic_name').value;
  const strength=document.getElementById('strength');
  const type=document.getElementById('type');
  const changed=e.target.id;
  document.getElementById('medicine_options_table_container').innerHTML='';
  if(changed==='generic_name'){ clearSelect(strength); clearSelect(type); }
  if(changed==='strength') clearSelect(type);
  if(!generic) return;
  fetch('/get_options',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({generic})})
  .then(r=>r.json()).then(d=>{
    if(changed==='generic_name') d.strengths.forEach(s=>addOption(strength,s,s));
    if(d.types) d.types.forEach(t=>addOption(type,t,t));
  });
}

function fetchMedicineOptions(){
  const generic=document.getElementById('generic_name').value;
  const strength=document.getElementById('strength').value;
  const type=document.getElementById('type').value;
  if(!generic||!strength||!type) return;
  fetch('/get_details',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({generic,strength,type})})
  .then(r=>r.json()).then(d=>renderMedicineTable(d.options));
}

function renderMedicineTable(options){
  let html=`<h3>Available Options (${options.length})</h3>
  <table><thead><tr><th>Brand</th><th>Price</th><th>Add</th></tr></thead><tbody>`;
  options.forEach(o=>{
    const esc=JSON.stringify(o).replace(/'/g,"&apos;");
    // ✅ এখানে "৳" দ্বিগুণ না হয় সে জন্য শুধু o.price দেখানো হয়েছে
    html+=`<tr><td>${o.brand}</td><td>${o.price}</td>
    <td><button class='add-btn-small' data-item='${esc}' onclick='addToPrescription(this)'>Add</button></td></tr>`;
  });
  document.getElementById('medicine_options_table_container').innerHTML=html+"</tbody></table>";
}

function addToPrescription(btn){
  const item=JSON.parse(btn.dataset.item.replace(/&apos;/g,"'"));
  item.quantity=1;
  item.time_schedule="1+1+1";
  item.meal_time="After Meal";
  prescriptionItems.push(item);
  renderPrescriptionTable();
}

function removeFromPrescription(i){ 
  prescriptionItems.splice(i,1); 
  renderPrescriptionTable(); 
}

function updateQuantity(i,val){
  prescriptionItems[i].quantity=parseInt(val)||1;
  renderPrescriptionTable();
}
function updateField(i,val,field){ 
  prescriptionItems[i][field]=val; 
}

function renderPrescriptionTable(){
  const tb=document.querySelector('#prescription_table tbody');
  tb.innerHTML=''; 
  let total=0;
  prescriptionItems.forEach((it,i)=>{
    // ✅ price_raw থাকলে সেটা ব্যবহার করব, না থাকলে price থেকে সংখ্যা বের করব
    const priceVal = parseFloat(it.price_raw || it.price.toString().replace(/[^\d.]/g,'')) || 0;
    const subtotal = priceVal * (parseInt(it.quantity)||1);
    total += subtotal;

    tb.innerHTML+=`
    <tr>
      <td>${it.generic}</td>
      <td>${it.brand}</td>
      <td>${it.strength}/${it.type}</td>
      <td><input type='number' min='1' value='${it.quantity}' onchange='updateQuantity(${i},this.value)' style='width:60px'></td>
      <td>
        <select onchange='updateField(${i},this.value,"time_schedule")'>
          <option value='1+1+1' ${it.time_schedule==='1+1+1'?'selected':''}>1+1+1</option>
          <option value='1+0+1' ${it.time_schedule==='1+0+1'?'selected':''}>1+0+1</option>
          <option value='0+0+1' ${it.time_schedule==='0+0+1'?'selected':''}>0+0+1</option>
        </select>
      </td>
      <td>
        <select onchange='updateField(${i},this.value,"meal_time")'>
          <option value='After Meal' ${it.meal_time==='After Meal'?'selected':''}>After Meal</option>
          <option value='Before Meal' ${it.meal_time==='Before Meal'?'selected':''}>Before Meal</option>
        </select>
      </td>
      <td class='price'>৳ ${subtotal.toFixed(2)}</td>
      <td><button class='remove-btn' onclick='removeFromPrescription(${i})'>X</button></td>
    </tr>`;
  });
  document.getElementById('total_cost').textContent='৳ '+total.toFixed(2);
  document.getElementById('prescription_table').style.display=prescriptionItems.length?'table':'none';
  document.getElementById('prescription_footer').style.display=prescriptionItems.length?'block':'none';
  document.getElementById('no_items_message').style.display=prescriptionItems.length?'none':'block';
}

function generateFinalOutput() {
  if (prescriptionItems.length === 0) return alert("Add medicines first!");

  const btn = document.querySelector('#generate_btn');
  if (btn) {
    btn.disabled = true;
    btn.textContent = "Generating PDF...";
  }

  const totalElement = document.getElementById('total_cost');
  let total_cost = 0;
  if (totalElement) {
    const match = totalElement.textContent.match(/[\d,\.]+/);
    total_cost = match ? parseFloat(match[0].replace(/,/g, '')) : 0;
  }

  console.log("💰 Total cost being sent:", total_cost);

  const data = {
    patient_name: document.getElementById('patient_name').value || 'Unknown',
    age: document.getElementById('age').value || '',
    sex: document.getElementById('sex').value || '',
    patient_id: document.getElementById('patient_id').value || 'NUB-0',
    next_appointment: document.getElementById('next_appointment').value || 'As Advised',
    medicines: prescriptionItems,
    total_cost: total_cost,
    doctor_name: "Dr. Sakib",
    specialization: "General Physician",
    reg_no: "REG-1234",
    phone: "+8801XXXXXXXXX"
  };

  console.log("🧾 Sending data to server:", data);

  fetch('/generate_pdf', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data)
  })
  .then(r => r.blob())
  .then(b => {
    const u = URL.createObjectURL(b);
    const a = document.createElement('a');
    a.href = u;
    a.download = 'Prescription.pdf';
    a.click();
    URL.revokeObjectURL(u);
  })
  .catch(err => {
    console.error("PDF generation failed:", err);
    alert("Failed to generate PDF. See console for details.");
  })
  .finally(() => {
    if (btn) {
      btn.disabled = false;
      btn.textContent = "💾 Generate Prescription PDF";
    }
  });
}

// =================== AUTO FILL FROM URL ===================
function getParam(k) {
  try {
    const p = new URLSearchParams(window.location.search);
    return p.has(k) ? p.get(k) : null;
  } catch {
    return null;
  }
}

function clean(v) {
  return v ? String(v).replace(/[<>]/g, "").trim() : "";
}

document.addEventListener("DOMContentLoaded", () => {
  const nameInput = document.getElementById("patient_name");
  const ageInput = document.getElementById("age");
  const sexInput = document.getElementById("sex");

  // read URL params
  const qName = clean(getParam("name"));
  const qAge  = clean(getParam("age"));
  const qSex  = clean(getParam("sex"));

  if (qName && nameInput && !nameInput.value)
    nameInput.value = qName;

  if (qAge && ageInput && !ageInput.value)
    ageInput.value = qAge.replace(/[^\d]/g, "");

  if (qSex && sexInput && !sexInput.value) {
    const s = qSex.toLowerCase();
    if (s.startsWith("m")) sexInput.value = "Male";
    else if (s.startsWith("f")) sexInput.value = "Female";
    else sexInput.value = qSex;
  }
});
// =================== END AUTO FILL ===================
