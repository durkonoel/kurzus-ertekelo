import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- BEÁLLÍTÁSOK ---
TABLAZAT_NEVE = "Diakok_Eredmenyei"
MAX_ONERTEKELES_PONT = 10

# --- GOOGLE SHEETS KAPCSOLAT ---
@st.cache_resource 
def get_gspread_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name("secrets.json", scope)
    client = gspread.authorize(creds)
    return client

def adatok_betoltese(client):
    sheet = client.open(TABLAZAT_NEVE).sheet1
    adatok = sheet.get_all_records()
    return pd.DataFrame(adatok), sheet

# --- FELÜLET ÉPÍTÉSE ---
st.set_page_config(page_title="Kurzus Értékelő", page_icon="🎓")

st.title("🎓 Kurzus Értékelő Rendszer")
st.write("Kérlek, lépj be az egyedi azonosítóddal a pontjaid megtekintéséhez és az önértékelés leadásához.")
st.divider()

try:
    client = get_gspread_client()
    df, sheet = adatok_betoltese(client)
except Exception as e:
    st.error(f"Hiba a Google kapcsolódásnál: {e}")
    st.stop()

diak_id = st.text_input("Diákazonosító (pl. DIAK01):", max_chars=10)

if diak_id:
    diak_adat = df[df['Azonosito'].astype(str).str.upper() == diak_id.upper()]

    if not diak_adat.empty:
        diak_neve = diak_adat['Nev'].values[0]
        st.success(f"Üdvözlünk, **{diak_neve}**!")
        
        st.subheader("📚 Tanári értékelések")
        col1, col2 = st.columns(2)
        col1.metric(label="Dolgozat", value=f"{diak_adat['Dolgozat'].values[0]} pont")
        col2.metric(label="Beadandó", value=f"{diak_adat['Beadando'].values[0]} pont")
        
        st.divider()
        st.subheader("💡 Önértékelés")
        
        jelenlegi_onert = diak_adat['Onertekeles'].values[0]
        
        with st.form("onertekeles_urlap"):
            uj_onert = st.number_input(
                f"Hány pontot adnál magadnak? (0-{MAX_ONERTEKELES_PONT})", 
                min_value=0, max_value=MAX_ONERTEKELES_PONT, 
                value=int(jelenlegi_onert) if pd.notna(jelenlegi_onert) and str(jelenlegi_onert).isdigit() else 0,
                step=1
            )
            submit_button = st.form_submit_button("Önértékelés mentése a felhőbe")
            
            if submit_button:
                sor_index = df.index[df['Azonosito'].astype(str).str.upper() == diak_id.upper()].tolist()[0]
                google_sor = sor_index + 2
                google_oszlop = 5 
                
                sheet.update_cell(google_sor, google_oszlop, uj_onert)
                st.success("Az önértékelésed sikeresen rögzítve lett a Google Táblázatban!")
                st.rerun() 
    else:
        st.error("Nem található ilyen azonosító a rendszerben.")