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
# A Google Drive-on lévő Google Táblázat PONTOS neve
TABLAZAT_NEVE = "2026-27-01XYZ"

# A 9 alkalom oszlopstruktúrája a táblázatod 3. sora alapján:
# - Standard alkalmak (1, 2, 4, 5, 7, 8): J (Jelenlét), A (Aktivitás), B (Brit tudósok)
# - Vizsga alkalmak (3, 6, 9): J (Jelenlét), A (Aktivitás), V1 (1. vizsga), V2 (2. vizsga)
OCCASIONS = [
    {"id": 1, "name": "1. alkalom", "cols": [("J", 2, "Jelenlét (J)"), ("A", 3, "Aktivitás (A)"), ("B", 4, "Brit tudósok (B)")]},
    {"id": 2, "name": "2. alkalom", "cols": [("J", 5, "Jelenlét (J)"), ("A", 6, "Aktivitás (A)"), ("B", 7, "Brit tudósok (B)")]},
    {"id": 3, "name": "3. alkalom (Vizsga)", "cols": [("J", 8, "Jelenlét (J)"), ("A", 9, "Aktivitás (A)"), ("V1", 10, "1. vizsga (V1)"), ("V2", 11, "2. vizsga (V2)")]},
    {"id": 4, "name": "4. alkalom", "cols": [("J", 12, "Jelenlét (J)"), ("A", 13, "Aktivitás (A)"), ("B", 14, "Brit tudósok (B)")]},
    {"id": 5, "name": "5. alkalom", "cols": [("J", 15, "Jelenlét (J)"), ("A", 16, "Aktivitás (A)"), ("B", 17, "Brit tudósok (B)")]},
    {"id": 6, "name": "6. alkalom (Vizsga)", "cols": [("J", 18, "Jelenlét (J)"), ("A", 19, "Aktivitás (A)"), ("V1", 20, "1. vizsga (V1)"), ("V2", 21, "2. vizsga (V2)")]},
    {"id": 7, "name": "7. alkalom", "cols": [("J", 22, "Jelenlét (J)"), ("A", 23, "Aktivitás (A)"), ("B", 24, "Brit tudósok (B)")]},
    {"id": 8, "name": "8. alkalom", "cols": [("J", 25, "Jelenlét (J)"), ("A", 26, "Aktivitás (A)"), ("B", 27, "Brit tudósok (B)")]},
    {"id": 9, "name": "9. alkalom (Vizsga)", "cols": [("J", 28, "Jelenlét (J)"), ("A", 29, "Aktivitás (A)"), ("V1", 30, "1. vizsga (V1)"), ("V2", 31, "2. vizsga (V2)")]},
]

# ==============================================================================
# 2. SEGÉDFÜGGVÉNYEK ÉS HITELÉSÍTÉS
# ==============================================================================
@st.cache_resource 
def get_gspread_client():
    """Csatlakozik a Google Drive API-hoz a felhős vagy helyi kulcs segítségével."""
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    if "google_credentials" in st.secrets:
        creds_dict = json.loads(st.secrets["google_credentials"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    else:
        creds = ServiceAccountCredentials.from_json_keyfile_name("secrets.json", scope)
    return gspread.authorize(creds)

def parse_sheet_date(val, current_year=2026):
    """Felismeri a 2. sorba beírt dátumformátumokat (pl. 2026.09.22, 2026-09-22, 09.22)."""
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
    
    # Hónap.nap felismerése (pl. 09.22 vagy 9.22.)
    m = re.match(r"^(\d{1,2})[./\-](\d{1,2})\.?$", val_str)
    if m:
        try:
            return date(current_year, int(m.group(1)), int(m.group(2)))
        except ValueError:
            pass
            
    # Év.hónap.nap felismerése kötőjellel vagy ponttal
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

def get_occasion_date_from_row2(row2, occ, current_year=2026):
    """Megkeresi az adott alkalomhoz tartozó dátumot a táblázat 2. sorában."""
    for code, col_idx, label in occ["cols"]:
        idx = col_idx - 1
        if idx < len(row2) and row2[idx] is not None:
            parsed = parse_sheet_date(row2[idx], current_year)
            if parsed:
                return parsed, str(row2[idx]).strip()
    return None, ""

# ==============================================================================
# 3. FELÜLET MEGJELENÍTÉSE
# ==============================================================================
st.set_page_config(page_title="Matek önértékelés", page_icon="🎓", layout="centered")

st.title("🎓 Matek önértékelés")
st.write("Válaszd ki a csoportodat, majd lépj be a teljes neveddel a mai pontok rögzítéséhez!")
st.divider()

# Kapcsolódás a táblázathoz
try:
    client = get_gspread_client()
    spreadsheet = client.open(TABLAZAT_NEVE)
    elerheto_csoportok = [ws.title for ws in spreadsheet.worksheets()]
except Exception as e:
    st.error(f"Hiba történt a Google Táblázathoz kapcsolódáskor: {e}")
    st.stop()

# 1. LÉPÉS: Csoport választása
kivalasztott_csoport = st.selectbox(
    "1. Csoport kiválasztása:",
    options=elerheto_csoportok,
    index=0 if elerheto_csoportok else None
)

if not kivalasztott_csoport:
    st.stop()

sheet = spreadsheet.worksheet(kivalasztott_csoport)
all_values = sheet.get_all_values()

if len(all_values) < 4:
    st.warning("A kiválasztott munkalap nem tartalmaz elegendő adatot (fejléc vagy név hiányzik).")
    st.stop()

# 2. LÉPÉS: Belépés névvel
diak_nev_input = st.text_input("2. Jelszó:", placeholder="pl. Cérna Géza")

if diak_nev_input:
    keresett_nev = diak_nev_input.strip().lower()
    student_row_idx = None
    real_student_name = ""
    student_scores_row = []

    # Diák kikeresése az 1. oszlopból (a 4. sortól lefelé)
    for r_idx in range(3, len(all_values)):
        row = all_values[r_idx]
        if row and row[0]:
            if str(row[0]).strip().lower() == keresett_nev:
                student_row_idx = r_idx + 1  # 1-alapú index a Google Sheets íráshoz
                real_student_name = str(row[0]).strip()
                student_scores_row = row
                break

    if not student_row_idx:
        st.error(f"Nem található '{diak_nev_input}' nevű diák a(z) {kivalasztott_csoport} csoportban. Kérlek, ellenőrizd az ékezeteket és a csoportot!")
        st.stop()

    st.success(f"Bejelentkezve: **{real_student_name}** | Csoport: **{kivalasztott_csoport}**")

    # Dátumok és státuszok kiértékelése
    row2 = all_values[1]
    ma = get_today_date()
    
    active_today_occ = None
    all_occ_status = []

    for occ in OCCASIONS:
        occ_date, raw_date_str = get_occasion_date_from_row2(row2, occ, ma.year)
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
            "raw_date": raw_date_str,
            "status": status
        })

    # ==============================================================================
    # 3. MAI ÓRA ÉRTÉKELÉSI ŰRLAPJA (CSAK HA MA VAN AZ ÓRA!)
    # ==============================================================================
    if active_today_occ:
        st.subheader(f"🟢 Óra értékelése: {active_today_occ['name']}")
        st.info("Minden kategóriában 0 vagy 1 pontot adhatsz magadnak. A pontok a mentés után azonnal frissülnek.")

        with st.form("mai_pontozas_form"):
            uj_pontok = {}
            cols = st.columns(len(active_today_occ["cols"]))

            for i, (code, col_idx, label) in enumerate(active_today_occ["cols"]):
                # Ha a diák korábban már mentett értéket ma, azt állítjuk be alapértelmezettnek
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

            mentes_gomb = st.form_submit_button("💾 Pontok mentése", type="primary")

            if mentes_gomb:
                # Szerveroldali biztonsági dátumellenőrzés
                mentes_napja = get_today_date()
                if mentes_napja != ma:
                    st.error("Ez az alkalom már lezárult!")
                    st.stop()

                with st.spinner("Mentés folyamatban..."):
                    for code, col_idx, label in active_today_occ["cols"]:
                        sheet.update_cell(student_row_idx, col_idx, uj_pontok[code])

                st.success("A pontjaidat sikeresen rögzítetted!")
                st.rerun()
    else:
        st.warning(f"ℹ️ **Ma ({ma.strftime('%Y.%m.%d.')}) nincs olyan óra kitűzve, amire pontot lehetne rögzíteni.**")
        st.caption("Az önértékelés mindig kizárólag az adott óra napján érhető el a táblázat 2. sorában megadott dátumok alapján.")

  # ==============================================================================
    # 4. EDDIGI EREDMÉNYEK ÁTTEKINTÉSE (PONTÖSSZEGZÉS AZ EDDIG MEGSZEREZHETŐ MAXIMUMHOZ)
    # ==============================================================================
    st.divider()
    with st.expander("📊 Összesített eredményeid és órák áttekintése", expanded=True):
        cat_totals = {"J": 0, "A": 0, "B": 0, "V1": 0, "V2": 0}
        cat_max_eddig = {"J": 0, "A": 0, "B": 0, "V1": 0, "V2": 0}
        total_earned = 0
        total_eddig_max = 0
        total_kurzus_max = 30

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

            # Az alkalom akkor számít "eddig megszerezhetőnek", ha:
            # - Már lezárult ("closed") vagy ma aktív ("open"), VAGY
            # - Már rögzítve lett rá pont (has_points)
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
        
        # Százalék számítása az EDDIG megszerezhető pontokhoz viszonyítva
        if total_eddig_max > 0:
            szazalek = round((total_earned / total_eddig_max) * 100)
            status_text = f"{t_earned_disp} / {total_eddig_max} pont ({szazalek}%)"
        else:
            szazalek = 0
            status_text = f"{t_earned_disp} pont (még nincs lezárt óra)"

        # Kiemelt kártyák (KPI) a táblázat felett
        m_col1, m_col2, m_col3, m_col4, m_col5 = st.columns(5)
        m_col1.metric("Jelenlegi állás", f"{t_earned_disp} / {total_eddig_max}", f"{szazalek}%")
        m_col2.metric("Jelenlét (J)", f"{cat_totals['J']} / {cat_max_eddig['J']}" if cat_max_eddig['J'] > 0 else "-")
        m_col3.metric("Aktivitás (A)", f"{cat_totals['A']} / {cat_max_eddig['A']}" if cat_max_eddig['A'] > 0 else "-")
        m_col4.metric("Brit tudósok (B)", f"{cat_totals['B']} / {cat_max_eddig['B']}" if cat_max_eddig['B'] > 0 else "-")
        vizsga_eddig_max = cat_max_eddig['V1'] + cat_max_eddig['V2']
        m_col5.metric("Vizsgák (V1+V2)", f"{cat_totals['V1'] + cat_totals['V2']} / {vizsga_eddig_max}" if vizsga_eddig_max > 0 else "-")

        st.caption(f"📌 A százalék az eddig lezajlott vagy mai órákon megszerezhető maximumhoz ({total_eddig_max} pont) viszonyítva értendő. A teljes kurzus összesen {total_kurzus_max} pontos.")

        def fmt_cat_cell(code):
            return f"{cat_totals[code]} / {cat_max_eddig[code]}" if cat_max_eddig[code] > 0 else "-"

        # Összesítő sor a táblázat alján
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
