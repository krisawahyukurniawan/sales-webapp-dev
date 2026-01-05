import streamlit as st
import pandas as pd
from sqlalchemy import text
from datetime import datetime

# Inisialisasi Koneksi ke 'connections.postgresql' di secrets.toml
conn = st.connection("postgresql", type="sql")

# ==============================================================================
# 1. AUTHENTICATION & USER MANAGEMENT
# Menggunakan tabel: users
# ==============================================================================

def validate_user(username, password):
    """Memvalidasi login user dari tabel 'users'."""
    
    # 1. Query Database
    # Pastikan query ini menggunakan 'name'
    query = "SELECT * FROM users WHERE sales_name = :u AND password = :p"
    df = conn.query(query, params={"u": username, "p": password}, ttl=0)
    
    if not df.empty:
        user_data = df.iloc[0]
        
        # 2. Ambil data dari DataFrame
        # PERBAIKAN UTAMA ADA DI SINI:
        # Ganti user_data['username'] menjadi user_data['name']
        
        # Kita juga menggunakan .get() agar lebih aman jika nama kolom sales group bervariasi
        sales_group = user_data.get('salesgroup') or user_data.get('salesGroup') or user_data.get('sales_group')
        
        return {
            "status": 200, 
            "data": {
                "salesName": user_data['sales_name'],  # <--- Ganti ini dari 'username' ke 'name'
                "salesGroup": sales_group
            }
        }
    return {"status": 401, "message": "Nama atau Password salah."}

def get_sales_names():
    """Mengambil list nama sales untuk dropdown login (opsional)."""
    # Mengambil dari tabel 'users' atau 'sales_names'
    df = conn.query("SELECT sales_name FROM users ORDER BY sales_name", ttl=600)
    return df['sales_name'].tolist()

# ==============================================================================
# 2. READ DATA (GET) - KANBAN & SEARCH
# Menggunakan tabel: sales_opportunities (Header/Summary) & opportunities (Detail)
# ==============================================================================

def get_kanban_data(sales_group, sales_name, is_super_user=False):
    """
    Mengambil data Kanban.
    PERBAIKAN: Mengganti 'so.sales_group' menjadi 'so.salesgroup_id'
    """
    query = """
        SELECT 
            so.opportunity_id, 
            so.opportunity_name, 
            so.sales_name, 
            so.salesgroup_id,  -- Pastikan ini salesgroup_id
            so.stage, 
            so.selling_price, 
            so.sales_notes,
            (
                SELECT op.company_name 
                FROM opportunities op 
                WHERE op.opportunity_id = so.opportunity_id 
                LIMIT 1
            ) as company_name
        FROM sales_opportunities so
        WHERE so.salesgroup_id = :sg  -- PERBAIKAN DI SINI (WHERE clause)
    """
    
    params = {"sg": sales_group}

    if not is_super_user:
        query += " AND so.sales_name = :sn"
        params["sn"] = sales_name
    
    # Debugging (Opsional): Print jika error lagi
    # print(query) 
    
    df = conn.query(query, params=params, ttl=60)
    
    if not df.empty and 'selling_price' in df.columns:
        df['selling_price'] = pd.to_numeric(df['selling_price'], errors='coerce').fillna(0)
        
    return df

def get_dashboard_data(sales_group, sales_name, is_super_user=False):
    """
    Mengambil data detail untuk Dashboard.
    PERBAIKAN: Mengganti 'sales_group' menjadi 'salesgroup_id'
    """
    # Cek nama tabel detail Anda, apakah 'opportunities' memiliki kolom 'salesgroup_id'
    query = "SELECT * FROM opportunities WHERE salesgroup_id = :sg" 
    params = {"sg": sales_group}
    
    if not is_super_user:
        query += " AND sales_name = :sn"
        params["sn"] = sales_name
    
    df = conn.query(query, params=params, ttl=300)
    return df

def get_opportunity_details(opportunity_id):
    """
    Mengambil detail item (produk/solusi) untuk satu opportunity.
    Menggunakan tabel: opportunities (Detail Line Items).
    """
    query = """
        SELECT 
            pillar, 
            solution, 
            service,
            brand, 
            selling_price 
        FROM opportunities 
        WHERE opportunity_id = :oid
    """
    df = conn.query(query, params={"oid": opportunity_id}, ttl=60)
    return df

def search_opportunities(keyword, search_by, sales_group, sales_name, is_super_user=False):
    """
    Search dengan batasan otoritas.
    PERBAIKAN: Mengganti 'sales_group' menjadi 'salesgroup_id'
    """
    col_map = {
        "Opportunity Name": "opportunity_name",
        "Company": "company_name",
        "Sales Name": "sales_name",
        "Stage": "stage"
    }
    db_col = col_map.get(search_by, "opportunity_name")
    
    # PERBAIKAN DI SINI
    query = f"SELECT * FROM sales_opportunities WHERE {db_col} ILIKE :kw AND salesgroup_id = :sg"
    params = {"kw": f"%{keyword}%", "sg": sales_group}
    
    if not is_super_user:
        query += " AND sales_name = :sn"
        params["sn"] = sales_name
        
    df = conn.query(query, params=params, ttl=0)
    return df

# ==============================================================================
# 3. MASTER DATA DROPDOWNS
# Mengambil data dari tabel master (brands, companies, master_pillars, dll)
# ==============================================================================

def get_master_data(table_name, column_name):
    """Helper generic untuk ambil list dari tabel master."""
    # Validasi nama tabel agar aman dari SQL Injection
    valid_tables = ["brands", "companies", "master_pillars", "distributors", "stage_pipeline"]
    if table_name not in valid_tables:
        return []
        
    query = f"SELECT {column_name} FROM {table_name} ORDER BY {column_name}"
    df = conn.query(query, ttl=3600) # Cache lama (1 jam) karena jarang berubah
    return df[column_name].tolist()

# ==============================================================================
# 4. WRITE DATA (POST/UPDATE) - TRANSACTIONAL
# Menggunakan tabel: sales_opportunities, activity_logs_sales
# ==============================================================================

def run_transaction(query_text, params):
    """Helper untuk eksekusi Write dengan Commit/Rollback."""
    with conn.engine.connect() as connection:
        trans = connection.begin()
        try:
            connection.execute(text(query_text), params)
            trans.commit()
            return True, "Success"
        except Exception as e:
            trans.rollback()
            return False, str(e)

def update_stage_and_note(opp_id, new_stage, new_note, user_name):
    """
    Update Stage dan Note di tabel sales_opportunities.
    Sekaligus mencatat log di activity_logs_sales.
    """
    
    # 1. Ambil data lama (untuk Log)
    check_q = "SELECT stage, sales_notes, opportunity_name FROM sales_opportunities WHERE opportunity_id = :oid"
    old_df = conn.query(check_q, params={"oid": opp_id}, ttl=0)
    
    if old_df.empty:
        return {"status": 404, "message": "Opportunity ID tidak ditemukan."}
    
    old_data = old_df.iloc[0]
    old_stage = old_data['stage']
    old_note = old_data['sales_notes']
    opp_name = old_data['opportunity_name']
    
    # 2. Query Update
    # Kita asumsikan kolomnya 'sales_notes' sesuai gambar (bukan sales_note)
    update_q = """
        UPDATE sales_opportunities 
        SET stage = :stage, sales_notes = :note, updated_at = NOW()
        WHERE opportunity_id = :oid
    """
    
    success, msg = run_transaction(update_q, {"stage": new_stage, "note": new_note, "oid": opp_id})
    
    if success:
        # 3. Logging ke activity_logs_sales
        # Kita catat 2 log jika Stage berubah dan Note berubah
        
        if old_stage != new_stage:
            log_sales_activity(opp_name, user_name, "UPDATE STAGE", "stage", old_stage, new_stage)
            
        if old_note != new_note:
            log_sales_activity(opp_name, user_name, "UPDATE NOTE", "sales_notes", old_note, new_note)
            
        conn.reset() # Reset cache agar data refresh
        return {"status": 200, "message": "Update berhasil."}
    else:
        return {"status": 500, "message": f"Error Database: {msg}"}

def update_lump_sum_price(opp_id, new_price, user_name):
    """Update harga total di sales_opportunities."""
    
    # 1. Ambil data lama
    old_df = conn.query("SELECT selling_price, opportunity_name FROM sales_opportunities WHERE opportunity_id = :oid", params={"oid": opp_id}, ttl=0)
    if old_df.empty: return {"status": 404, "message": "Data not found"}
    
    old_price = old_df.iloc[0]['selling_price']
    opp_name = old_df.iloc[0]['opportunity_name']
    
    # 2. Update
    update_q = "UPDATE sales_opportunities SET selling_price = :p, updated_at = NOW() WHERE opportunity_id = :oid"
    success, msg = run_transaction(update_q, {"p": new_price, "oid": opp_id})
    
    if success:
        log_sales_activity(opp_name, user_name, "UPDATE PRICE", "selling_price", old_price, new_price)
        conn.reset()
        return {"status": 200, "message": "Harga berhasil diupdate."}
    return {"status": 500, "message": msg}

def log_sales_activity(opp_id, opp_name, user, action, field, old_val, new_val):
    """
    Mencatat log dengan Opportunity ID sebagai referensi utama.
    """
    try:
        query = """
            INSERT INTO activity_logs_sales 
            (timestamp, opportunity_id, opportunity_name, user_name, action, field_changed, old_value, new_value)
            VALUES (NOW(), :oid, :on, :un, :act, :fld, :old, :new)
        """
        params = {
            "oid": opp_id,      # <--- ID Opportunity masuk di sini
            "on": opp_name, 
            "un": user, 
            "act": action, 
            "fld": field, 
            "old": str(old_val), 
            "new": str(new_val)
        }
        # Jalankan silent transaction
        run_transaction(query, params)
    except Exception as e:
        print(f"Log Error: {e}")
    
def fix_empty_stages():
    """Mengisi stage kosong dengan 'Open'."""
    query = """
        UPDATE sales_opportunities
        SET stage = 'Open'
        WHERE stage IS NULL OR stage = ''
    """
    success, msg = run_transaction(query, {})
    return success, msg

def update_stage_sales_enhanced(opp_id, new_stage, notes, closing_reason, user_name):
    """
    Update Stage khusus Sales App dengan dukungan Closing Reason.
    Target Table: sales_opportunities
    """
    try:
        # 1. Ambil data lama untuk Log
        check_q = "SELECT stage, sales_notes, opportunity_name FROM sales_opportunities WHERE opportunity_id = :oid"
        old_df = conn.query(check_q, params={"oid": opp_id}, ttl=0)
        
        if old_df.empty: return {"status": 404, "message": "Opportunity ID tidak ditemukan."}
        
        old_data = old_df.iloc[0]
        opp_name = old_data['opportunity_name']
        old_stage = old_data['stage']

        # 2. Query Update Dinamis
        # Jika Closing, simpan reason & closing_notes.
        # Jika Progress (Tender/Procurement), simpan ke sales_notes biasa.
        
        if new_stage in ["Closed Won", "Closed Lost"]:
            update_q = """
                UPDATE sales_opportunities 
                SET stage = :stg, 
                    sales_notes = :note, 
                    closing_reason = :reason,
                    closing_notes = :note, 
                    updated_at = NOW()
                WHERE opportunity_id = :oid
            """
            params = {"stg": new_stage, "note": notes, "reason": closing_reason, "oid": opp_id}
        else:
            update_q = """
                UPDATE sales_opportunities 
                SET stage = :stg, 
                    sales_notes = :note, 
                    updated_at = NOW()
                WHERE opportunity_id = :oid
            """
            params = {"stg": new_stage, "note": notes, "oid": opp_id}

        # Eksekusi Transaction
        success, msg = run_transaction(update_q, params)
        
        success, msg = run_transaction(update_q, params)
        
        if success:
            # 3. Log Activity
            log_msg = f"{old_stage} -> {new_stage}"
            if closing_reason:
                log_msg += f" (Reason: {closing_reason})"
            
            # PANGGIL LOG DENGAN ID
            log_sales_activity(
                opp_id,          # <--- Kirim ID
                opp_name,        # Kirim Nama
                user_name, 
                "UPDATE STAGE", 
                "stage", 
                old_stage, 
                log_msg
            )
            
            conn.reset()
            return {"status": 200, "message": "Stage updated successfully."}
        else:
            return {"status": 500, "message": f"DB Error: {msg}"}

    except Exception as e:
        return {"status": 500, "message": str(e)}
    
# ==============================================================================
# SECTION 5: LUMP SUM PRICE UPDATE (SALES OPPORTUNITIES HEADER)
# ==============================================================================

def get_sales_opportunity_header(opp_id):
    """
    Mengambil data header dari sales_opportunities untuk ditampilkan sebelum edit.
    FIX: Mengambil company_name dari tabel opportunities menggunakan Subquery.
    """
    query = """
        SELECT 
            so.opportunity_id,
            so.opportunity_name,
            -- Subquery untuk mengambil Company Name dari tabel detail
            (
                SELECT op.company_name 
                FROM opportunities op 
                WHERE op.opportunity_id = so.opportunity_id 
                LIMIT 1
            ) as company_name,
            so.sales_name,
            so.stage,
            so.selling_price,
            so.sales_notes
        FROM sales_opportunities so
        WHERE so.opportunity_id = :oid
    """
    df = conn.query(query, params={"oid": opp_id}, ttl=0)
    if not df.empty:
        return df.iloc[0].to_dict()
    return None

def update_lump_sum_price_header(opp_id, new_price, user_name):
    """
    Update harga total (Lump Sum) HANYA di tabel sales_opportunities.
    Tabel detail 'opportunities' TIDAK disentuh.
    """
    try:
        with conn.engine.connect() as connection:
            trans = connection.begin()
            try:
                # 1. Ambil harga lama untuk log
                old_val = connection.execute(
                    text("SELECT selling_price FROM sales_opportunities WHERE opportunity_id = :oid"),
                    {"oid": opp_id}
                ).scalar() or 0

                # 2. Update Harga Header
                upd_q = text("""
                    UPDATE sales_opportunities 
                    SET selling_price = :price, updated_at = NOW() 
                    WHERE opportunity_id = :oid
                """)
                connection.execute(upd_q, {"price": new_price, "oid": opp_id})

                # 3. Log Activity
                if float(old_val) != float(new_price):
                    # Ambil nama opportunity untuk keperluan tampilan log teks
                    opp_name_q = connection.execute(
                        text("SELECT opportunity_name FROM sales_opportunities WHERE opportunity_id=:oid"), 
                        {"oid": opp_id}
                    ).scalar()

                    # PANGGIL LOG DENGAN ID
                    log_sales_activity(
                        opp_id,          # <--- Kirim ID
                        opp_name_q,      # Kirim Nama
                        user_name, 
                        "UPDATE PRICE", 
                        "Lump Sum Selling Price", 
                        str(old_val), 
                        str(new_price)
                    )

                trans.commit()
                return {"status": 200, "message": f"Harga berhasil diupdate menjadi Rp {new_price:,.0f}"}
            
            except Exception as e:
                trans.rollback()
                return {"status": 500, "message": str(e)}

    except Exception as e:
        return {"status": 500, "message": str(e)}
    
def get_opportunity_line_items(opp_id):
    """
    Mengambil detail item untuk referensi Sales saat update harga.
    """
    query = """
        SELECT 
            product_id,
            pillar,
            solution,
            brand,
            service, -- Tambahkan ini agar info lebih lengkap
            cost
        FROM opportunities 
        WHERE opportunity_id = :oid
        ORDER BY created_at
    """
    df = conn.query(query, params={"oid": opp_id}, ttl=0)
    return df