import io
from datetime import datetime
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="Neurodiverz Családi Command Center", page_icon="🧩", layout="wide")

st.markdown("""
<style>
.hero{border-radius:24px;padding:24px;margin-bottom:18px;background:linear-gradient(135deg,#0f172a,#1e293b);border:1px solid rgba(255,255,255,.12)}
.hero-title{font-size:2rem;font-weight:900}
.hero-sub{color:#cbd5e1;font-size:1rem;line-height:1.45}
.card{border-radius:18px;padding:18px;margin-bottom:14px;background:rgba(31,41,55,.75);border:1px solid rgba(255,255,255,.10)}
.pill{display:inline-block;padding:5px 10px;border-radius:999px;font-weight:800;margin-bottom:8px}
.red{background:#7f1d1d;color:#fecaca}.yellow{background:#713f12;color:#fde68a}.green{background:#14532d;color:#bbf7d0}
</style>
""", unsafe_allow_html=True)

DAYS = ["Hétfő","Kedd","Szerda","Csütörtök","Péntek","Szombat","Vasárnap"]

PROGRAM_TYPES = {
    "Óvoda / iskola": {"base":3,"social":3,"sensory":3,"transition":2},
    "Fejlesztés / terápia": {"base":5,"social":2,"sensory":3,"transition":3},
    "Sport / mozgás": {"base":4,"social":3,"sensory":3,"transition":3},
    "Orvos / vizsgálat": {"base":7,"social":2,"sensory":4,"transition":4},
    "Bevásárlás / ügyintézés": {"base":6,"social":4,"sensory":5,"transition":4},
    "Családi program": {"base":5,"social":5,"sensory":4,"transition":3},
    "Születésnap / zsúr": {"base":8,"social":6,"sensory":6,"transition":4},
    "Utazás": {"base":5,"social":2,"sensory":3,"transition":6},
    "Otthoni nyugodt blokk": {"base":-4,"social":-2,"sensory":-3,"transition":-2},
    "Szabad játék / pihenés": {"base":-3,"social":-1,"sensory":-2,"transition":-1},
}
ENV_OPTIONS = ["Otthon","Ismerős hely","Új hely","Zsúfolt hely","Hangos hely","Sok ember","Kültér","Beltér"]
FEEDBACK_OPTIONS = {"Nyugodt":0,"Kissé fáradt":1,"Ingerlékeny":2,"Túlterhelt":3,"Meltdown közeli":4,"Meltdown volt":5}
RECOVERY_OPTIONS = {"Nem volt recovery":0,"Kevés recovery":1,"Közepes recovery":2,"Jó recovery":3,"Nagyon jó recovery":4}

if "events" not in st.session_state:
    st.session_state.events = []
if "feedback" not in st.session_state:
    st.session_state.feedback = []

def weight(level):
    return 0.6 + (level - 1) * 0.25

def clamp(x):
    return int(max(0, min(100, round(x))))

def score_color(score, inverse=False):
    if inverse:
        return "🔴" if score >= 75 else ("🟠" if score >= 50 else "🟢")
    return "🟢" if score >= 75 else ("🟠" if score >= 50 else "🔴")

def calculate_event_load(event, profile):
    p = PROGRAM_TYPES[event["program_típus"]]
    load = p["base"]
    load += p["sensory"] * weight(profile["sok_ember_zaj"])
    load += p["social"] * weight(profile["tarsas_helyzet"])
    load += p["transition"] * weight(profile["atallas"])
    load += max(0, event["időtartam_óra"] - 1) * 1.2
    if event["utazás_perc"] >= 45:
        load += 5 * weight(profile["utazas"])
    elif event["utazás_perc"] >= 20:
        load += 2.5 * weight(profile["utazas"])
    envs = event["környezeti_tényezők"]
    if "Sok ember" in envs or "Zsúfolt hely" in envs:
        load += 5 * weight(profile["sok_ember_zaj"])
    if "Hangos hely" in envs:
        load += 4 * weight(profile["sok_ember_zaj"])
    if "Új hely" in envs:
        load += 4 * weight(profile["rutinváltás"])
    if event["kiszámíthatóság"] == "Váratlan / bizonytalan":
        load += 6 * weight(profile["rutinváltás"])
    elif event["kiszámíthatóság"] == "Részben kiszámítható":
        load += 3 * weight(profile["rutinváltás"])
    if event["program_típus"] in ["Otthoni nyugodt blokk","Szabad játék / pihenés"]:
        load -= 4 * weight(profile["recovery_igeny"])
    return round(load, 1)

def build_day_summary(events_df, feedback_df):
    if events_df.empty:
        return pd.DataFrame()
    s = events_df.groupby("Nap", as_index=False).agg(
        Programok=("program_típus","count"),
        Terhelés=("terhelési_pont","sum"),
        Átállások=("átállás_szám","sum"),
        Recovery_órák=("recovery_óra","sum"),
        Szülői_terhelés=("szülői_terhelés","sum")
    )
    s["Kockázat"] = s["Terhelés"] + s["Átállások"]*2 + s["Szülői_terhelés"] - s["Recovery_órák"]*4
    s["Nap_sorrend"] = s["Nap"].map({d:i for i,d in enumerate(DAYS)})
    s = s.sort_values("Nap_sorrend").drop(columns=["Nap_sorrend"])
    if not feedback_df.empty:
        s = s.merge(feedback_df[["Nap","Esti állapot pont","Esti állapot"]], on="Nap", how="left")
    return s

def generate_insights(day_summary, profile, events_df):
    insights = []
    if day_summary.empty:
        return [{"Szint":"INFO","Téma":"Nincs még adat","Mit látunk?":"Adj hozzá heti programokat.","Mit érdemes tenni?":"Kezdd a fix programokkal: óvoda/iskola, fejlesztés, sport, családi programok."}]
    overload = day_summary[day_summary["Kockázat"] >= 45]
    if len(overload):
        insights.append({"Szint":"FIGYELMEZTETÉS","Téma":"Túlterhelt napok","Mit látunk?":f"Magasabb idegrendszeri terhelés látszik ezeken a napokon: {', '.join(overload['Nap'])}.","Mit érdemes tenni?":"Ezekre a napokra érdemes kevesebb plusz programot, több előrejelzést és több nyugodt blokkot tervezni."})
    low_rec = day_summary[day_summary["Recovery_órák"] < 1]
    if len(low_rec) >= 3:
        insights.append({"Szint":"FIGYELMEZTETÉS","Téma":"Kevés recovery","Mit látunk?":"Több napon kevés valódi lecsendesedési idő látszik.","Mit érdemes tenni?":"Érdemes legalább 2–3 délutánba rövid, védett nyugalmi blokkot tenni."})
    ordered = day_summary.set_index("Nap").reindex(DAYS).fillna(0).reset_index()
    streak = max_streak = 0
    for high in (ordered["Kockázat"] >= 40):
        streak = streak + 1 if high else 0
        max_streak = max(max_streak, streak)
    if max_streak >= 3:
        insights.append({"Szint":"KRITIKUS","Téma":"Egymást követő nehéz napok","Mit látunk?":"Legalább 3 egymást követő magasabb terhelésű nap látszik.","Mit érdemes tenni?":"Ha lehet, tegyél recovery blokkot a sorozat közepére vagy végére, és kerüld az új, bizonytalan helyzeteket."})
    if profile["sok_ember_zaj"] >= 4 and not events_df.empty:
        crowded = events_df[events_df["környezeti_tényezők"].apply(lambda xs: "Sok ember" in xs or "Zsúfolt hely" in xs if isinstance(xs, list) else False)]
        if len(crowded) >= 2:
            insights.append({"Szint":"FIGYELMEZTETÉS","Téma":"Sok ember / zsúfolt hely","Mit látunk?":"A gyermekprofil alapján a sok ember érzékeny pont, és több ilyen program is szerepel.","Mit érdemes tenni?":"Érdemes előre jelezni ezeket, rövidebb ott tartózkodást tervezni, vagy utána nyugodt blokkot hagyni."})
    if profile["atallas"] >= 4:
        high_t = day_summary[day_summary["Átállások"] >= 3]
        if len(high_t):
            insights.append({"Szint":"FIGYELMEZTETÉS","Téma":"Sok átállás","Mit látunk?":f"Sok váltás látszik ezeken a napokon: {', '.join(high_t['Nap'])}.","Mit érdemes tenni?":"Érdemes vizuális előrejelzést, indulási rutint és plusz időt hagyni az átmenetekre."})
    if not insights:
        insights.append({"Szint":"INFO","Téma":"Kezelhető hét","Mit látunk?":"A jelenlegi terv alapján nincs kiugró túlterhelési jel.","Mit érdemes tenni?":"Tartsd meg a nyugodt blokkokat, és a hét végén rögzíts visszajelzést."})
    return insights

def export_excel(profile, events_df, day_summary, insights_df, feedback_df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        pd.DataFrame([profile]).to_excel(writer, index=False, sheet_name="Gyermekprofil")
        events_df.to_excel(writer, index=False, sheet_name="Programok")
        day_summary.to_excel(writer, index=False, sheet_name="Napi összegzés")
        insights_df.to_excel(writer, index=False, sheet_name="Insightok")
        feedback_df.to_excel(writer, index=False, sheet_name="Visszajelzések")
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.utils import get_column_letter
        for ws in writer.book.worksheets:
            for cell in ws[1]:
                cell.fill = PatternFill("solid", fgColor="1E3A8A")
                cell.font = Font(color="FFFFFF", bold=True)
                cell.alignment = Alignment(wrap_text=True)
            for col_idx, col in enumerate(ws.columns, 1):
                ws.column_dimensions[get_column_letter(col_idx)].width = 24
                for cell in col:
                    cell.alignment = Alignment(wrap_text=True, vertical="top")
    return output.getvalue()

st.markdown("""
<div class="hero">
  <div class="hero-title">🧩 Neurodiverz Családi Command Center</div>
  <div class="hero-sub">
    Standardizált, kérdőíves családi terhelés- és stabilitástervező autizmus / Asperger érintett családoknak.
    Nem naptár: azt próbálja megmutatni, hogy a hét mennyire lehet fenntartható idegrendszeri szempontból.
  </div>
</div>
""", unsafe_allow_html=True)

tab_profile, tab_plan, tab_feedback, tab_dashboard, tab_export = st.tabs([
    "1. Gyermekprofil", "2. Heti programtervező", "3. Napi visszajelzés", "4. Stabilitási elemzés", "5. Export"
])

with tab_profile:
    st.subheader("Gyermekprofil")
    st.caption("1 = alig jellemző, 5 = nagyon jellemző. Ezek súlyozzák a heti programokat.")
    c1,c2,c3 = st.columns(3)
    with c1:
        child_name = st.text_input("Gyermek neve / beceneve", "Gyermek")
        age_group = st.selectbox("Életkor", ["3–5 év","6–8 év","9–12 év","13+ év"])
        sok_ember_zaj = st.slider("Sok ember / zaj mennyire terhelő?", 1, 5, 4)
    with c2:
        atallas = st.slider("Átállások mennyire nehezek?", 1, 5, 3)
        rutinváltás = st.slider("Váratlan helyzet / rutinváltás mennyire nehéz?", 1, 5, 4)
        utazas = st.slider("Utazás mennyire terhelő?", 1, 5, 3)
    with c3:
        tarsas_helyzet = st.slider("Társas helyzet mennyire merítő?", 1, 5, 3)
        recovery_igeny = st.slider("Mennyi lecsendesedési időre van szüksége?", 1, 5, 4)
        alvas = st.slider("Rossz alvás mennyire borítja a napot?", 1, 5, 4)
    helps = st.multiselect("Mi szokott segíteni?", ["Vizuális napirend","Előre szólás","Fülvédő","Kedvenc tárgy","Csendes sarok","Mozgás","Egyedüllét","Rövid séta","Kevesebb beszéd"], default=["Előre szólás","Csendes sarok"])
    profile = {"gyermek_neve":child_name,"életkor":age_group,"sok_ember_zaj":sok_ember_zaj,"atallas":atallas,"rutinváltás":rutinváltás,"utazas":utazas,"tarsas_helyzet":tarsas_helyzet,"recovery_igeny":recovery_igeny,"alvas":alvas,"segítő_stratégiák":", ".join(helps)}
    st.info("A rendszer nem általános szabályt használ, hanem a gyermek saját érzékenységeit súlyozza.")

with tab_plan:
    st.subheader("Heti programtervező")
    with st.form("program_form"):
        c1,c2,c3 = st.columns(3)
        with c1:
            day = st.selectbox("Nap", DAYS)
            program_type = st.selectbox("Program típusa", list(PROGRAM_TYPES.keys()))
            duration = st.slider("Időtartam (óra)", 0.5, 8.0, 1.0, step=0.5)
        with c2:
            travel = st.slider("Utazás összesen (perc)", 0, 120, 0, step=5)
            transitions = st.slider("Átállások száma", 0, 6, 1)
            predictability = st.selectbox("Kiszámíthatóság", ["Kiszámítható","Részben kiszámítható","Váratlan / bizonytalan"])
        with c3:
            envs = st.multiselect("Környezeti tényezők", ENV_OPTIONS, default=["Ismerős hely"])
            recovery_hours = st.slider("Utána tervezett nyugodt blokk (óra)", 0.0, 5.0, 0.5, step=0.5)
            parent_load = st.slider("Szülői szervezési terhelés", 1, 5, 2)
        submitted = st.form_submit_button("Program hozzáadása", use_container_width=True)
    if submitted:
        event = {"Nap":day,"program_típus":program_type,"időtartam_óra":duration,"utazás_perc":travel,"átállás_szám":transitions,"kiszámíthatóság":predictability,"környezeti_tényezők":envs,"recovery_óra":recovery_hours,"szülői_terhelés":parent_load}
        event["terhelési_pont"] = calculate_event_load(event, profile)
        st.session_state.events.append(event)
        st.success("Program hozzáadva.")
    events_df = pd.DataFrame(st.session_state.events)
    if events_df.empty:
        st.info("Még nincs rögzített program.")
    else:
        st.dataframe(events_df, use_container_width=True, hide_index=True)
        if st.button("Utolsó program törlése"):
            st.session_state.events = st.session_state.events[:-1]
            st.rerun()

with tab_feedback:
    st.subheader("Napi visszajelzés")
    with st.form("feedback_form"):
        c1,c2,c3 = st.columns(3)
        with c1:
            fb_day = st.selectbox("Nap", DAYS, key="fb_day")
            evening_state = st.selectbox("Esti állapot", list(FEEDBACK_OPTIONS.keys()))
        with c2:
            sleep_quality = st.slider("Alvás minősége előző éjjel", 1, 5, 3)
            recovery_quality = st.selectbox("Recovery minősége", list(RECOVERY_OPTIONS.keys()))
        with c3:
            helped = st.multiselect("Mi segített aznap?", ["Előre szólás","Csend","Mozgás","Kevesebb program","Egyedüllét","Rutin","Fülvédő","Nem tudjuk"])
            trigger = st.multiselect("Mi nehezítette?", ["Sok ember","Zaj","Átállás","Váratlan helyzet","Utazás","Éhség","Fáradtság","Túl hosszú program","Nem tudjuk"])
        fb_submit = st.form_submit_button("Visszajelzés mentése", use_container_width=True)
    if fb_submit:
        st.session_state.feedback.append({"Nap":fb_day,"Esti állapot":evening_state,"Esti állapot pont":FEEDBACK_OPTIONS[evening_state],"Alvás minősége":sleep_quality,"Recovery minősége":recovery_quality,"Recovery pont":RECOVERY_OPTIONS[recovery_quality],"Mi segített":", ".join(helped),"Mi nehezítette":", ".join(trigger)})
        st.success("Visszajelzés mentve.")
    feedback_df = pd.DataFrame(st.session_state.feedback)
    if feedback_df.empty:
        st.info("Még nincs visszajelzés.")
    else:
        st.dataframe(feedback_df, use_container_width=True, hide_index=True)
        if st.button("Utolsó visszajelzés törlése"):
            st.session_state.feedback = st.session_state.feedback[:-1]
            st.rerun()

with tab_dashboard:
    events_df = pd.DataFrame(st.session_state.events)
    feedback_df = pd.DataFrame(st.session_state.feedback)
    day_summary = build_day_summary(events_df, feedback_df)
    insights_df = pd.DataFrame(generate_insights(day_summary, profile, events_df))
    st.subheader("Heti stabilitási elemzés")
    if day_summary.empty:
        st.info("Adj hozzá programokat a heti elemzéshez.")
    else:
        weekly_risk_raw = day_summary["Kockázat"].sum()
        overload_risk = clamp(weekly_risk_raw / 280 * 100)
        stability = clamp(100 - overload_risk + day_summary["Recovery_órák"].sum()*2)
        max_day = day_summary.sort_values("Kockázat", ascending=False).iloc[0]
        c1,c2,c3,c4 = st.columns(4)
        c1.metric("Heti stabilitás", f"{stability}/100", score_color(stability))
        c2.metric("Túlterhelési kockázat", f"{overload_risk}/100", score_color(overload_risk, inverse=True))
        c3.metric("Legnehezebb nap", str(max_day["Nap"]), f"{max_day['Kockázat']:.0f} pont")
        c4.metric("Recovery összesen", f"{day_summary['Recovery_órák'].sum():.1f} óra")
        fig = px.bar(day_summary, x="Nap", y="Kockázat", color="Kockázat", title="Napi idegrendszeri terhelés / kockázat")
        fig.update_layout(template="plotly_dark", xaxis_title="", yaxis_title="Kockázati pont")
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(day_summary, use_container_width=True, hide_index=True)
        st.markdown("### Szülőbarát insightok")
        for _, item in insights_df.iterrows():
            klass = "red" if item["Szint"]=="KRITIKUS" else ("yellow" if item["Szint"]=="FIGYELMEZTETÉS" else "green")
            st.markdown(f"""<div class="card"><span class="pill {klass}">{item['Szint']}</span><h3>{item['Téma']}</h3><b>Mit látunk?</b><br>{item['Mit látunk?']}<br><br><b>Mit érdemes tenni?</b><br>{item['Mit érdemes tenni?']}</div>""", unsafe_allow_html=True)
        if not feedback_df.empty:
            st.markdown("### Mit tanulhatunk a visszajelzésekből?")
            merged = day_summary.merge(feedback_df[["Nap","Esti állapot","Esti állapot pont","Mi nehezítette"]], on="Nap", how="left")
            st.dataframe(merged, use_container_width=True, hide_index=True)
            if merged["Esti állapot pont"].notna().sum() >= 2:
                corr = merged[["Kockázat","Esti állapot pont"]].corr().iloc[0,1]
                if pd.notna(corr) and corr > 0.4:
                    st.warning("A visszajelzések alapján úgy tűnik, hogy a magasabb napi terhelés rosszabb esti állapottal jár együtt.")
                else:
                    st.info("Egyelőre nincs erős kapcsolat a napi terhelés és az esti állapot között. Több hét adat segíthet.")

with tab_export:
    st.subheader("Export")
    events_df = pd.DataFrame(st.session_state.events)
    feedback_df = pd.DataFrame(st.session_state.feedback)
    day_summary = build_day_summary(events_df, feedback_df)
    insights_df = pd.DataFrame(generate_insights(day_summary, profile, events_df))
    if day_summary.empty:
        st.info("Nincs exportálható heti elemzés.")
    else:
        st.dataframe(day_summary, use_container_width=True, hide_index=True)
        st.dataframe(insights_df, use_container_width=True, hide_index=True)
        st.download_button("⬇️ Excel riport letöltése", data=export_excel(profile, events_df, day_summary, insights_df, feedback_df), file_name=f"neurodiverz_csaladi_command_center_{datetime.now().strftime('%Y%m%d')}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
    st.info("Ez az eszköz nem diagnosztikai vagy egészségügyi rendszer. Célja a családi terhelés, rutin, átállások és recovery tudatosabb tervezése.")
