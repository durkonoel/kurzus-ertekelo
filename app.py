import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
from datetime import datetime, date
import zoneinfo
import re

# ==============================================================================
# 1. BEÁLLÍTÁSOK
# ==============================================================================
# A csoportok megjelenített neve és a hozzájuk tartozó Google Táblázat pontos neve (vagy ID-ja):
CSOPORTOK = {
    "XYZ csoport": "XYZjelenlét",
    "EQ csoport": "EQjelenlét",
    "W csoport": "Wjelenlét",
    "R csoport": "Rjelenlét",
}

# ==============================================================================
# 2. SEGÉDFÜGGVÉNYEK ÉS HITELESÍTÉS
# ==============================================================================
@st.cache_resource
def get_gspread_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    if "google_credentials" in st.secrets:
        creds_dict = json.loads(st.secrets["google_credentials"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    else:
        creds = ServiceAccountCredentials.from_json_keyfile_name("secrets.json", scope)
    return gspread.authorize(creds)

def parse_sheet_date(val, current_year=2026):
    """Felismeri a táblázat 2. sorában lévő dátumokat (pl. 09.24. vagy 2026.09.24)."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    val_str = str(val).strip()
    if not val_str:
        return None
    
    formats = [
        "%Y-%m-%d", "%Y.%m.%d", "%Y.%m.%d.", "%Y/%m/%d",
        "%d.%m.%Y", "%d/%m/%Y", "%m/%d/%Y",
        "%Y. %m. %d.", "%Y. %m. %d", "%Y-%m-%d %H:%M:%S"
    ]
    for fmt in formats:
        try:
            return datetime.strptime(val_str, fmt).date()
        except ValueError:
            pass
    
    # Hónap.nap felismerése (pl. 09.24. vagy 9.24)
    m = re.match(r"^(\d{1,2})[./\-](\d{1,2})\.?$", val_str)
    if m:
        try:
            return date(current_year, int(m.group(1)), int(m.group(2)))
        except ValueError:
            pass
            
    m = re.match(r"^(\d{4})[./\-](\d{1,2})[./\-](\d{1,2})\.?$", val_str)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass
    return None

def get_today_date():
    """Visszaadja a mai napot a magyar időzóna (Europe/Budapest) szerint."""
    try:
        tz = zoneinfo.ZoneInfo("Europe/Budapest")
        return datetime.now(tz).date()
    except Exception:
        return date.today()

def parse_occasions_from_sheet(all_values):
    """
    Dinamikusan felismeri mind a 22 alkalmat a 2. sorban szereplő dátumok
    és a 3. sorban lévő fejlécek (J, A, B, V1, V2) alapján.
    """
    if len(all_values) < 3:
        return []
    row2 = all_values[1]
    row3 = all_values[2]
    
    occasions = []
    current_occ = None
    
    label_map = {
        "J": "Jelenlét (J)",
        "A": "Aktivitás (A)",
        "B": "Brit tudósok (B)",
        "V1": "1. vizsga (V1)",
        "V2": "2. vizsga (V2)"
    }
    
    for col_idx in range(1, len(row3)):
        c_1based = col_idx + 1
        metric = row3[col_idx] if col_idx < len(row3) else ""
        metric_str = str(metric).strip().upper() if metric is not None else ""
        
        date_raw = row2[col_idx] if col_idx < len(row2) else ""
        date_raw_str = str(date_raw).strip() if date_raw is not None else ""
        
        if metric_str not in ["J", "A", "B", "V1", "V2"]:
            continue
            
        # Új alkalom kezdődik, ha van dátum a 2. sorban, vagy ha 'J' oszlop következik
        if date_raw_str != "" or metric_str == "J":
            if current_occ is not None:
                occasions.append(current_occ)
            occ_num = len(occasions) + 1
            current_occ = {
                "id": occ_num,
                "name": f"{occ_num}. alkalom",
                "date_col": c_1based,
                "raw_date": date_raw_str,
                "cols": []
            }
        elif current_occ is None:
            occ_num = 1
            current_occ = {
                "id": occ_num,
                "name": f"{occ_num}. alkalom",
                "date_col": c_1based,
                "raw_date": date_raw_str,
                "cols": []
            }
            
        current_occ["cols"].append((metric_str, c_1based, label_map.get(metric_str, metric_str)))
        if "V1" in metric_str or "V2" in metric_str:
            if "(Vizsga)" not in current_occ["name"]:
                current_occ["name"] = f"{current_occ['id']}. alkalom (Vizsga)"
                
    if current_occ is not None and current_occ["cols"]:
        occasions.append(current_occ)
        
    return occasions

# ==============================================================================
# 3. FELÜLET MEGJELENÍTÉSE
# ==============================================================================
st.set_page_config(page_title="Matek Önértékelő", page_icon="📐", layout="centered")

st.title("📐 Matek Önértékelő")
st.write("Lépj be a teljes neveddel a mai óra pontjainak rögzítéséhez és eredményeid megtekintéséhez!")
st.divider()

# Csoport kiválasztása
if len(CSOPORTOK) > 1:
    kivalasztott_csoport_nev = st.selectbox(
        "Csoport kiválasztása:",
        options=list(CSOPORTOK.keys()),
        index=0
    )
else:
    kivalasztott_csoport_nev = list(CSOPORTOK.keys())[0]

tablazat_azonosito = CSOPORTOK[kivalasztott_csoport_nev]

# Kapcsolódás a kiválasztott csoporthoz tartozó Google Táblázathoz
try:
    client = get_gspread_client()
    try:
        spreadsheet = client.open_by_key(tablazat_azonosito)
    except Exception:
        spreadsheet = client.open(tablazat_azonosito)
    elerheto_lapok = [ws.title for ws in spreadsheet.worksheets()]
except Exception as e:
    st.error(f"Hiba történt a(z) '{kivalasztott_csoport_nev}' táblázathoz kapcsolódáskor: {e}")
    st.stop()

# Ha a csoport táblázatán belül több munkalap/fül is van
if len(elerheto_lapok) > 1:
    kivalasztott_lap = st.selectbox(
        "Munkalap kiválasztása:",
        options=elerheto_lapok,
        index=0
    )
else:
    kivalasztott_lap = elerheto_lapok[0]

sheet = spreadsheet.worksheet(kivalasztott_lap)
all_values = sheet.get_all_values()

if len(all_values) < 4:
    st.warning("A munkalap nem tartalmaz elegendő adatot.")
    st.stop()

# Alkalmak felismerése a 2. és 3. sorból
occasions = parse_occasions_from_sheet(all_values)

# Belépés névvel
diak_nev_input = st.text_input("Add meg a teljes neved (Belépési kód):", placeholder="pl. Bereczki Zoltán")

if diak_nev_input:
    keresett_nev = diak_nev_input.strip().lower()
    student_row_idx = None
    real_student_name = ""
    student_scores_row = []

    # Diák kikeresése az 1. oszlopból (4. sortól lefelé)
    for r_idx in range(3, len(all_values)):
        row = all_values[r_idx]
        if row and row[0]:
            if str(row[0]).strip().lower() == keresett_nev:
                student_row_idx = r_idx + 1  # 1-alapú index Google Sheets íráshoz
                real_student_name = str(row[0]).strip()
                student_scores_row = row
                break

    if not student_row_idx:
        st.error(f"Nem található '{diak_nev_input}' nevű diák a(z) '{kivalasztott_csoport_nev}' névsorában. Kérlek, ellenőrizd az írásmódot vagy a választott csoportot!")
        st.stop()

    st.success(f"Bejelentkezve: **{real_student_name}** ({kivalasztott_csoport_nev})")

    # Dátumok és státuszok kiértékelése
    ma = get_today_date()
    active_today_occ = None
    all_occ_status = []

    for occ in occasions:
        occ_date = parse_sheet_date(occ["raw_date"], ma.year)
        if occ_date:
            if occ_date == ma:
                status = "open"
                active_today_occ = occ
            elif occ_date < ma:
                status = "closed"
            else:
                status = "future"
        else:
            status = "not_set"
        
        all_occ_status.append({
            "occ": occ,
            "date": occ_date,
            "raw_date": occ["raw_date"],
            "status": status
        })

    # ==============================================================================
    # 4. MAI ÓRA ÉRTÉKELÉSI ŰRLAPJA (SZIGORÚ IDŐKORLÁT)
    # ==============================================================================
    if active_today_occ:
        st.subheader(f"🟢 Mai óra értékelése: {active_today_occ['name']} ({active_today_occ['raw_date']})")
        st.info("Minden kategóriában 0 vagy 1 pontot adhatsz magadnak. A mentés után a pontjaid azonnal bekerülnek a táblázatba.")

        with st.form("mai_pontozas_form"):
            uj_pontok = {}
            cols = st.columns(len(active_today_occ["cols"]))

            for i, (code, col_idx, label) in enumerate(active_today_occ["cols"]):
                jelenlegi_ertek = student_scores_row[col_idx - 1] if col_idx - 1 < len(student_scores_row) else ""
                default_idx = 1 if str(jelenlegi_ertek).strip() == "1" else 0

                with cols[i]:
                    uj_pontok[code] = st.radio(
                        label,
                        options=[0, 1],
                        index=default_idx,
                        horizontal=True,
                        key=f"radio_{code}_{col_idx}"
                    )

            mentes_gomb = st.form_submit_button("💾 Mai pontok mentése a Google Táblázatba", type="primary")

            if mentes_gomb:
                # Szerveroldali biztonsági ellenőrzés
                if get_today_date() != ma:
                    st.error("A szerver órája szerint ez az alkalom már lezárult!")
                    st.stop()

                with st.spinner("Mentés folyamatban..."):
                    for code, col_idx, label in active_today_occ["cols"]:
                        sheet.update_cell(student_row_idx, col_idx, uj_pontok[code])

                st.success("A mai pontjaidat sikeresen rögzítettük!")
                st.rerun()
    else:
        st.warning(f"ℹ️ **Ma ({ma.strftime('%Y.%m.%d.')}) nincs olyan óra kitűzve, amire pontot lehetne rögzíteni.**")
        st.caption("Az önértékelés kizárólag az adott óra napján érhető el a táblázatban megadott dátumok alapján.")

    # ==============================================================================
    # 5. ÖSSZESÍTŐ STATISZTIKA ÉS EDDIGI ÁLLÁS
    # ==============================================================================
    st.divider()
    with st.expander("📊 Összesített eredményeid és órák áttekintése", expanded=True):
        cat_totals = {"J": 0, "A": 0, "B": 0, "V1": 0, "V2": 0}
        cat_max_eddig = {"J": 0, "A": 0, "B": 0, "V1": 0, "V2": 0}
        total_earned = 0
        total_eddig_max = 0
        total_kurzus_max = sum(len(o["cols"]) for o in occasions)

        summary_rows = []
        for item in all_occ_status:
            occ = item["occ"]
            st_text = {
                "open": "🟢 Ma aktív (Szerkeszthető)",
                "closed": "🔒 Lezárult",
                "future": "⏳ Jövőbeli",
                "not_set": "⚪ Nincs dátum"
            }.get(item["status"], "-")

            row_data = {
                "Alkalom": occ["name"],
                "Dátum": item["raw_date"] if item["raw_date"] else "-",
                "Státusz": st_text,
                "J": "-", "A": "-", "B": "-", "V1": "-", "V2": "-",
                "Pontszám": "-"
            }

            occ_sum = 0
            has_points = False

            for code, col_idx, label in occ["cols"]:
                c_val = student_scores_row[col_idx - 1] if col_idx - 1 < len(student_scores_row) else ""
                val_str = str(c_val).strip().replace(",", ".")
                if val_str != "":
                    try:
                        f = float(val_str)
                        pts = int(f) if f.is_integer() else f
                        row_data[code] = str(pts)
                        cat_totals[code] += pts
                        total_earned += pts
                        occ_sum += pts
                        has_points = True
                    except ValueError:
                        row_data[code] = val_str

            # Eddig megszerezhetőnek számít az alkalom, ha lezárult, ma van, vagy már van rá rögzített pont
            is_eddig = (item["status"] in ["open", "closed"]) or has_points

            if is_eddig:
                total_eddig_max += len(occ["cols"])
                for code, col_idx, label in occ["cols"]:
                    cat_max_eddig[code] += 1

            if has_points:
                formatted_occ_sum = int(occ_sum) if isinstance(occ_sum, float) and occ_sum.is_integer() else occ_sum
                row_data["Pontszám"] = f"{formatted_occ_sum} pont"

            summary_rows.append(row_data)

        t_earned_disp = int(total_earned) if isinstance(total_earned, float) and total_earned.is_integer() else total_earned
        
        # Százalék az EDDIG megszerezhető maximumhoz képest
        if total_eddig_max > 0:
            szazalek = round((total_earned / total_eddig_max) * 100)
            status_text = f"{t_earned_disp} / {total_eddig_max} pont ({szazalek}%)"
        else:
            szazalek = 0
            status_text = f"{t_earned_disp} pont (még nincs lezárt óra)"

        # Kiemelt KPI mérőszámok
        m_col1, m_col2, m_col3, m_col4, m_col5 = st.columns(5)
        m_col1.metric("Jelenlegi állás", f"{t_earned_disp} / {total_eddig_max}", f"{szazalek}%")
        m_col2.metric("Jelenlét (J)", f"{cat_totals['J']} / {cat_max_eddig['J']}" if cat_max_eddig['J'] > 0 else "-")
        m_col3.metric("Aktivitás (A)", f"{cat_totals['A']} / {cat_max_eddig['A']}" if cat_max_eddig['A'] > 0 else "-")
        m_col4.metric("Brit tudósok (B)", f"{cat_totals['B']} / {cat_max_eddig['B']}" if cat_max_eddig['B'] > 0 else "-")
        vizsga_eddig_max = cat_max_eddig['V1'] + cat_max_eddig['V2']
        m_col5.metric("Vizsgák (V1+V2)", f"{cat_totals['V1'] + cat_totals['V2']} / {vizsga_eddig_max}" if vizsga_eddig_max > 0 else "-")

        st.caption(f"📌 A százalék az eddig lezajlott vagy mai órákon megszerezhető maximumhoz ({total_eddig_max} pont) viszonyítva értendő. A teljes kurzus 22 alkalma összesen {total_kurzus_max} pontos.")

        def fmt_cat_cell(code):
            return f"{cat_totals[code]} / {cat_max_eddig[code]}" if cat_max_eddig[code] > 0 else "-"

        # Alsó összegző sor
        total_row = {
            "Alkalom": "⭐ ÖSSZESEN",
            "Dátum": "-",
            "Státusz": status_text,
            "J": fmt_cat_cell("J"),
            "A": fmt_cat_cell("A"),
            "B": fmt_cat_cell("B"),
            "V1": fmt_cat_cell("V1"),
            "V2": fmt_cat_cell("V2"),
            "Pontszám": f"{t_earned_disp} pont"
        }
        summary_rows.append(total_row)

        df_summary = pd.DataFrame(summary_rows)
        st.dataframe(df_summary, use_container_width=True, hide_index=True)
