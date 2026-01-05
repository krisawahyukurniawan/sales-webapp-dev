import streamlit as st
import pandas as pd
import time
import backend as db  # Pastikan file backend.py berada di folder yang sama

# ==============================================================================
# 1. KONFIGURASI HALAMAN & CSS
# ==============================================================================
st.set_page_config(
    page_title="Sales App - SISINDOKOM",
    page_icon="🔒",
    layout="wide"
)

# Inisialisasi session state
if 'group_info' not in st.session_state:
    st.session_state.group_info = None
if 'selected_kanban_opp_id' not in st.session_state:
    st.session_state.selected_kanban_opp_id = None

# ==============================================================================
# 2. DEFINISI SUPER USER & UTILITIES
# ==============================================================================

# Daftar Super User (Sales Manager) yang bisa melihat seluruh data Grup-nya
SUPER_USERS = [
    "Ridho Danu S.A", 
    "Budiono Untoro", 
    "Neli Nursyamsyiah", 
    "Tommy S. Purnomo", 
    "Lie Suherman",
    "Tommy S. Purnomo"
]

def check_is_super_user(username):
    """Cek apakah user memiliki hak akses Super User."""
    return username in SUPER_USERS

def format_idr(value):
    """Format angka ke format Rupiah (e.g., 1.000.000)."""
    try:
        if value is None: return "0"
        val_float = float(value)
        return f"{val_float:,.0f}".replace(",", ".")
    except (ValueError, TypeError):
        return "0"

# ==============================================================================
# 3. ANTARMUKA UTAMA (MAIN APP)
# ==============================================================================

def main_app():
    # --- A. Setup User Context ---
    group_info = st.session_state.group_info
    
    # Safety Check
    if not group_info:
        st.error("Sesi login kadaluarsa. Silakan refresh halaman.")
        st.stop()

    sales_name = group_info.get('salesName', 'User')
    sales_group = group_info.get('salesGroup')

    # Cek Otoritas
    is_super = check_is_super_user(sales_name)

    # --- B. Sidebar ---
    with st.sidebar:
        st.subheader(f"Welcome, {sales_name}")
        st.caption(f"Group: {sales_group}")
        
        if is_super:
            st.success("🌟 Super User (Manager Mode)")
        else:
            st.info("👤 Sales Mode")
            
        st.markdown("---")
        if st.button("Logout", type="primary"):
            st.session_state.group_info = None
            st.session_state.selected_kanban_opp_id = None
            st.cache_data.clear()
            st.rerun()

    st.title(f"Sales App - {sales_group}")

    # --- C. Tabs Navigasi ---
    tab1, tab2, tab3, tab4 = st.tabs(["Kanban View", "Search & Dashboard", "Update Stage", "Update Price"])

    # ==========================================================================
    # TAB 1: KANBAN VIEW
    # ==========================================================================
    with tab1:
        # Load Data dengan Scope Otoritas
        # (Backend akan filter by Sales Name jika bukan Super User)
        df_kanban = db.get_kanban_data(sales_group, sales_name, is_super)

        if df_kanban.empty:
            msg = f"Tim {sales_group} belum memiliki opportunity." if is_super else "Anda belum memiliki opportunity."
            st.info(msg)
        else:
            # --- Dashboard Metrics ---
            # menghitung total pipeline value
            total_value = df_kanban['selling_price'].sum()
            # total opportunity berdasarkan unique opportunity_id
            total_opps = df_kanban['opportunity_id'].nunique()
            # menghitung total won value
            won_val = df_kanban[df_kanban['stage'] == 'Closed Won']['selling_price'].sum()

            m1, m2, m3 = st.columns(3)
            m1.metric("Pipeline Value", f"Rp {format_idr(total_value)}")
            m2.metric("Total Opportunities", f"{total_opps}")
            m3.metric("Won Value", f"Rp {format_idr(won_val)}")
            st.divider()

            # --- Detail View Logic ---
            if st.session_state.selected_kanban_opp_id:
                selected_id = st.session_state.selected_kanban_opp_id
                
                if st.button("⬅️ Kembali ke Kanban"):
                    st.session_state.selected_kanban_opp_id = None
                    st.rerun()
                
                # Ambil data header dari dataframe lokal
                header_data = df_kanban[df_kanban['opportunity_id'] == selected_id].iloc[0]
                
                st.subheader(f"{header_data['opportunity_name']}")
                st.caption(f"Client: {header_data.get('company_name', '-')}")
                st.markdown(f"**Total Price:** Rp {format_idr(header_data['selling_price'])}")

                # Ambil Detail Item dari Backend
                st.markdown("#### Solution Details")
                df_details = db.get_opportunity_details(selected_id)
                if not df_details.empty:
                    # Format harga di tabel detail
                    if 'selling_price' in df_details.columns:
                        df_details['selling_price'] = df_details['selling_price'].apply(format_idr)
                    st.dataframe(df_details, use_container_width=True)
                else:
                    st.info("Tidak ada rincian item.")

            # --- Kanban Board Logic ---
            else:
                # 1. Filter Dataframe per Stage
                open_opps = df_kanban[df_kanban['stage'] == 'Open']
                won_opps = df_kanban[df_kanban['stage'] == 'Closed Won']
                lost_opps = df_kanban[df_kanban['stage'] == 'Closed Lost']

                # 2. Hitung Total Value per Stage
                val_open = open_opps['selling_price'].sum()
                val_won = won_opps['selling_price'].sum()
                val_lost = lost_opps['selling_price'].sum()

                # 3. Render Kolom
                c1, c2, c3 = st.columns(3)

                def render_card(row, color):
                    with st.container(border=True):
                        st.markdown(f"**{row['opportunity_name']}**")
                        st.caption(f"🏢 {row.get('company_name', '-')}")
                        st.caption(f"👤 {row['sales_name']}")
                        st.markdown(f"💰 **Rp {format_idr(row['selling_price'])}**")
                        
                        if st.button("Lihat Detail", key=f"btn_{row['opportunity_id']}"):
                            st.session_state.selected_kanban_opp_id = row['opportunity_id']
                            st.rerun()

                with c1:
                    st.markdown(f"### 🟦 Open ({len(open_opps)})")
                    st.markdown(f"**Total: Rp {format_idr(val_open)}**")
                    st.markdown("---")
                    for _, row in open_opps.iterrows(): render_card(row, "blue")

                with c2:
                    st.markdown(f"### 🟩 Won ({len(won_opps)})")
                    st.markdown(f"**Total: Rp {format_idr(val_won)}**")
                    st.markdown("---")
                    for _, row in won_opps.iterrows(): render_card(row, "green")

                with c3:
                    st.markdown(f"### 🟥 Lost ({len(lost_opps)})")
                    st.markdown(f"**Total: Rp {format_idr(val_lost)}**")
                    st.markdown("---")
                    for _, row in lost_opps.iterrows(): render_card(row, "red")

    # ==========================================================================
    # TAB 2: DASHBOARD & SEARCH
    # ==========================================================================
    with tab2:
        st.header("Interactive Dashboard & Search")
        
        # Load Full Data (Detail Level) dari Backend
        with st.spinner("Loading dataset..."):
            df = db.get_dashboard_data(sales_group, sales_name, is_super)
        
        if df.empty:
            st.info("No opportunity data available.")
        else:
            # --- Pre-processing ---
            # 1. Numerik
            for col in ['cost', 'selling_price']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

            # 2. Tanggal (Prioritas start_date -> created_at)
            date_col = 'start_date' if 'start_date' in df.columns else 'created_at'
            if date_col in df.columns:
                df['filter_date_dt'] = pd.to_datetime(df[date_col], errors='coerce')
            
            # 3. Handle NULL (Convert to string "Unknown")
            fillna_cols = [
                'presales_name', 'responsible_name', 'sales_name', 
                'distributor_name', 'brand', 'pillar', 'solution', 
                'company_name', 'vertical_industry', 'stage', 
                'opportunity_name'
            ]
            for col in fillna_cols:
                if col in df.columns:
                    df[col] = df[col].fillna("Unknown").astype(str)

            # =================================================================
            # 🎛️ FILTER PANEL (12 ITEMS - 4x3 Grid)
            # =================================================================
            with st.container(border=True):
                st.subheader("🔍 Filter Panel")
                
                def get_opts(col_name):
                    return sorted(df[col_name].unique().tolist()) if col_name in df.columns else []

                # --- BARIS 1 ---
                c1, c2, c3, c4 = st.columns(4)
                with c1: sel_inputter = st.multiselect("Inputter (Presales)", get_opts('presales_name'))
                with c2: sel_pam = st.multiselect("Presales Account Manager", get_opts('responsible_name'))
                with c3: sel_sales = st.multiselect("Sales Name", get_opts('sales_name'))
                with c4: sel_distributor = st.multiselect("Distributor", get_opts('distributor_name'))

                # --- BARIS 2 ---
                c5, c6, c7, c8 = st.columns(4)
                with c5: sel_brand = st.multiselect("Brand", get_opts('brand'))
                with c6: sel_pillar = st.multiselect("Pillar", get_opts('pillar'))
                with c7: sel_solution = st.multiselect("Solution", get_opts('solution'))
                with c8: sel_client = st.multiselect("Client", get_opts('company_name'))

                # --- BARIS 3 ---
                c9, c10, c11, c12 = st.columns(4)
                with c9: sel_vertical = st.multiselect("Vertical", get_opts('vertical_industry'))
                with c10: sel_stage = st.multiselect("Stage", get_opts('stage'))
                with c11:
                    date_range = None
                    if 'filter_date_dt' in df.columns:
                        min_d = df['filter_date_dt'].min().date() if not df['filter_date_dt'].isnull().all() else None
                        max_d = df['filter_date_dt'].max().date() if not df['filter_date_dt'].isnull().all() else None
                        if min_d and max_d:
                            date_range = st.date_input("Start Date", value=(min_d, max_d))
                with c12: sel_opportunity = st.multiselect("Opportunity Name", get_opts('opportunity_name'))

            # =================================================================
            # 🔄 FILTER ENGINE
            # =================================================================
            df_filtered = df.copy()
            
            filters = {
                'presales_name': sel_inputter, 'responsible_name': sel_pam,
                'sales_name': sel_sales, 'distributor_name': sel_distributor,
                'brand': sel_brand, 'pillar': sel_pillar,
                'solution': sel_solution, 'company_name': sel_client,
                'vertical_industry': sel_vertical, 'stage': sel_stage,
                'opportunity_name': sel_opportunity
            }

            for col, selection in filters.items():
                if selection and col in df_filtered.columns:
                    df_filtered = df_filtered[df_filtered[col].isin(selection)]

            if isinstance(date_range, tuple) and len(date_range) == 2 and 'filter_date_dt' in df_filtered.columns:
                start_d, end_d = date_range
                mask = (df_filtered['filter_date_dt'].dt.date >= start_d) & (df_filtered['filter_date_dt'].dt.date <= end_d)
                df_filtered = df_filtered[mask]

            # =================================================================
            # 📊 SUMMARY METRICS (3 CARDS)
            # =================================================================
            st.markdown("### Summary Metrics")
            
            total_lines = len(df_filtered)
            uniq_opps = df_filtered['opportunity_id'].nunique() if 'opportunity_id' in df_filtered.columns else 0
            uniq_cust = df_filtered['company_name'].nunique() if 'company_name' in df_filtered.columns else 0
            val_sum = df_filtered['selling_price'].sum() if 'selling_price' in df_filtered.columns else 0

            m1, m2, m3 = st.columns(3)
            m1.metric("Unique Opportunities", f"{uniq_opps}")
            m2.metric("Total Customers", f"{uniq_cust}")
            m3.metric("Total Value", f"Rp {format_idr(val_sum)}")
            
            st.divider()

            # =================================================================
            # 📋 DATA TABLE (CUSTOM COLUMNS)
            # =================================================================
            st.subheader(f"Detailed Data ({total_lines} rows)")
            
            if not df_filtered.empty:
                desired_columns = [
                    'opportunity_id', 'presales_name', 'sales_name', 
                    'company_name', 'opportunity_name', 'stage', 
                    'selling_price', 'sales_notes', 'pillar', 
                    'solution', 'service', 'brand'
                ]
                # Filter kolom yang tersedia saja
                final_cols = [c for c in desired_columns if c in df_filtered.columns]
                
                df_display = df_filtered[final_cols].copy()
                if 'selling_price' in df_display.columns:
                    df_display['selling_price'] = df_display['selling_price'].apply(format_idr)

                st.dataframe(df_display, use_container_width=True)
            else:
                st.warning("Tidak ada data yang cocok dengan filter.")

    # ==========================================================================
    # TAB 3: UPDATE STAGE (ENHANCED WORKFLOW)
    # ==========================================================================
    with tab3:
        st.header("Update Stage Process")
        st.info("Pilih stage Tender/Procurement untuk update progres, atau Closed untuk finalisasi.")

        # Reuse Kanban data untuk list opportunity
        df_opps = db.get_kanban_data(sales_group, sales_name, is_super)
        
        if not df_opps.empty:
            # Dropdown Pilih Opportunity
            opp_dict = {f"{row['opportunity_name']}": row['opportunity_id'] for _, row in df_opps.iterrows()}
            sel_opp = st.selectbox("Pilih Opportunity untuk Di-update", options=opp_dict.keys(), index=None)
            
            if sel_opp:
                oid = opp_dict[sel_opp]
                # Ambil data terbaru dari DB (agar realtime)
                # Kita pakai helper get_kanban_data lagi tapi filter di python (atau buat fungsi get single di backend sales)
                curr_row = df_opps[df_opps['opportunity_id'] == oid].iloc[0]
                
                st.markdown("---")
                col_info1, col_info2 = st.columns(2)
                col_info1.write(f"**Current Stage:** `{curr_row['stage']}`")
                col_info1.write(f"**Last Note:** {curr_row.get('sales_notes', '-')}")
                
                # --- INPUT LOGIC ---
                st.subheader("Update Status")
                
                # 1. Definisi Stage Sales (Hardcoded sesuai Business Process baru)
                sales_stages = [
                    "Tender Auction", 
                    "Procurement / Pengadaan & Negotiation / Annualizing", 
                    "Closed Won", 
                    "Closed Lost"
                ]
                
                # Set default index
                try: 
                    def_idx = sales_stages.index(curr_row['stage'])
                except: 
                    def_idx = 0
                
                new_stg = st.selectbox("New Stage", sales_stages, index=def_idx)
                
                # 2. Conditional Logic (Notes vs Closing Reason)
                closing_reason_val = None
                sales_notes_val = ""
                
                if new_stg in ["Closed Won", "Closed Lost"]:
                    st.markdown("#### 🏁 Closing Details")
                    
                    if new_stg == "Closed Won":
                        st.success("Congratulations on winning this deal!")
                        # Opsi disamakan dengan Presales App
                        reason_opts = [
                            "Commercial / Price Strategy",
                            "Technical Solution Fit",
                            "Relationship / Trust",
                            "Delivery / Timeline",
                            "After-Sales Service",
                            "Other Winning Factors"
                        ]
                        label_reason = "Winning Factor (Why did we win?)"
                        placeholder_note = "Ceritakan kunci kemenangan kita..."
                    else:
                        st.error("Marking deal as Lost.")
                        # Opsi disamakan dengan Presales App
                        reason_opts = [
                            "Price / Budget Constraint",
                            "Competitor - Technical",
                            "Competitor - Price",
                            "Feature Gap / Spec Mismatch",
                            "Late Proposal Submission",
                            "Project Cancelled",
                            "Lost to Incumbent",
                            "No Decision"
                        ]
                        label_reason = "Loss Reason (Why did we lose?)"
                        placeholder_note = "Ceritakan kenapa kita kalah (nama kompetitor, gap harga, dll)..."
                    
                    c_reason, c_note = st.columns([1, 2])
                    with c_reason:
                        closing_reason_val = st.selectbox(label_reason, reason_opts)
                    with c_note:
                        sales_notes_val = st.text_area("Closing Remarks / Post-Mortem", placeholder=placeholder_note, height=100)
                        
                else:
                    # Logic untuk Stage Tender & Procurement
                    st.markdown("#### 📝 Progress Updates")
                    st.warning(f"You are updating to: **{new_stg}**")
                    sales_notes_val = st.text_area(
                        "Stage Notes (Wajib Diisi)", 
                        value=curr_row.get('sales_notes', ''),
                        placeholder="Update status terkini: Jadwal aanwijzing, status negosiasi harga, dll...",
                        height=150
                    )

                # 3. Submit Button
                st.markdown("---")
                if st.button("💾 Update Sales Stage", type="primary"):
                    if not sales_notes_val:
                        st.error("Notes/Remarks tidak boleh kosong.")
                    else:
                        with st.spinner("Updating Pipeline..."):
                            # Panggil fungsi backend BARU
                            res = db.update_stage_sales_enhanced(
                                oid, 
                                new_stg, 
                                sales_notes_val, 
                                closing_reason_val, 
                                sales_name
                            )
                            
                            if res['status'] == 200:
                                st.success("✅ Update Berhasil!")
                                st.session_state.selected_kanban_opp_id = None # Reset selection
                                time.sleep(1.5)
                                st.cache_data.clear() # Clear cache agar data refresh
                                st.rerun()
                            else:
                                st.error(res['message'])
    
    # ==========================================================================
    # TAB 4: UPDATE PRICE (LUMP SUM WITH ITEM DETAILS)
    # ==========================================================================
    with tab4:
        st.header("Update Lump Sum Price")
        st.info("Input harga penawaran total (Global Price) untuk opportunity ini.")

        # 1. Pilih Opportunity
        df_price = db.get_kanban_data(sales_group, sales_name, is_super)
        
        if df_price.empty:
            st.warning("Tidak ada data opportunity.")
        else:
            # Dropdown Selector
            opp_dict_p = {f"{row['opportunity_name']}": row['opportunity_id'] for _, row in df_price.iterrows()}
            sel_opp_p = st.selectbox("Pilih Opportunity", options=opp_dict_p.keys(), index=None)
            
            if sel_opp_p:
                oid_p = opp_dict_p[sel_opp_p]
                
                # 2. Ambil Detail Header (Realtime)
                header_data = db.get_sales_opportunity_header(oid_p)
                
                if header_data:
                    st.markdown("---")
                    
                    # A. INFO HEADER
                    with st.container(border=True):
                        st.subheader(f"📄 {header_data['opportunity_name']}")
                        
                        col_d1, col_d2 = st.columns(2)
                        col_d1.markdown(f"**Client:** {header_data.get('company_name')}")
                        col_d1.markdown(f"**Stage:** {header_data.get('stage')}")
                        col_d2.markdown(f"**Sales:** {header_data.get('sales_name')}")
                        
                        # Tampilkan harga saat ini
                        curr_sell = float(header_data.get('selling_price') or 0)
                        col_d2.markdown(f"**Current Price:** Rp {format_idr(curr_sell)}")

                    # B. SOLUTION ITEMS (TABEL DETAIL)
                    st.markdown("#### 📦 Solution Items (Reference)")
                    
                    # Ambil data item dari backend
                    df_items = db.get_opportunity_line_items(oid_p)
                    
                    if not df_items.empty:
                        # Hitung Total Cost (Modal) untuk referensi Margin
                        total_cost_ref = pd.to_numeric(df_items['cost'], errors='coerce').sum()
                        
                        # Format tampilan Cost di tabel
                        df_display = df_items.copy()
                        if 'cost' in df_display.columns:
                            df_display['cost'] = df_display['cost'].apply(lambda x: f"Rp {format_idr(x)}")
                        
                        # Tampilkan Tabel
                        st.dataframe(
                            df_display, 
                            use_container_width=True, 
                            hide_index=True,
                            column_config={
                                "product_id": "ID",
                                "brand": "Brand",
                                "solution": "Solution",
                                "service": "Service",
                                "cost": "Cost (Modal)"
                            }
                        )
                        
                        # Tampilkan Total Cost sebagai referensi
                        st.caption(f"ℹ️ **Total Cost (Modal Presales):** Rp {format_idr(total_cost_ref)}")
                        
                    else:
                        st.warning("Belum ada item solusi yang diinput Presales.")
                        total_cost_ref = 0

                    # C. FORM UPDATE HARGA
                    st.markdown("---")
                    st.subheader("Edit Global Price")
                    
                    with st.form("lump_sum_form"):
                        new_price_val = st.number_input(
                            "Total Selling Price (IDR)", 
                            value=curr_sell, 
                            step=1000000.0, 
                            format="%f",
                            help="Masukkan angka total penawaran ke customer (Lump Sum)."
                        )
                        st.caption(f"Reads: Rp {format_idr(new_price_val)}")
                        
                        # Hitung Estimasi Margin Langsung saat mengetik (Visual saja)
                        est_margin = new_price_val - total_cost_ref
                        est_margin_perc = (est_margin / new_price_val * 100) if new_price_val > 0 else 0
                        
                        if total_cost_ref > 0:
                            if est_margin < 0:
                                st.error(f"⚠️ Warning: Harga jual di bawah modal! (Margin: {est_margin_perc:.1f}%)")
                            else:
                                st.success(f"✅ Est. Gross Margin: {est_margin_perc:.1f}% (Rp {format_idr(est_margin)})")
                        
                        # Tombol Submit
                        submitted = st.form_submit_button("💾 Save New Price", type="primary")
                        
                        if submitted:
                            with st.spinner("Updating Header Price..."):
                                res = db.update_lump_sum_price_header(oid_p, new_price_val, sales_name)
                                
                                if res['status'] == 200:
                                    st.success(f"✅ {res['message']}")
                                    st.cache_data.clear()
                                    time.sleep(1.5)
                                    st.rerun()
                                else:
                                    st.error(f"Failed: {res['message']}")

# ==============================================================================
# 5. HALAMAN LOGIN & ROUTER
# ==============================================================================

def password_page():
    st.title("Sales App Login")
    st.caption("Please login using your Sales Name")
    
    # Ambil list user
    sales_list = db.get_sales_names()
    
    with st.form("login"):
        user_in = st.selectbox("Nama Sales", options=sales_list)
        pass_in = st.text_input("Password", type="password")
        
        if st.form_submit_button("Masuk"):
            res = db.validate_user(user_in, pass_in)
            if res['status'] == 200:
                st.session_state.group_info = res['data']
                st.rerun()
            else:
                st.error(res['message'])

if st.session_state.group_info:
    main_app()
else:
    password_page()