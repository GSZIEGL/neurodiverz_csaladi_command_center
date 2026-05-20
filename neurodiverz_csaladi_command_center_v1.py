from __future__ import annotations

import io
from datetime import date, datetime, time, time
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st
from supabase import create_client, Client

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
    import matplotlib.pyplot as plt
except Exception:
    SimpleDocTemplate = None


def _clean_predictability_safe(value):
    text = str(value or "")
    if "| Idő:" in text:
        return text.split("| Idő:", 1)[0].strip()
    return text


def _parse_event_time_safe_from_text(value):
    text = str(value or "")
    if "| Idő:" not in text:
        return "", ""
    try:
        rng = text.split("| Idő:", 1)[1].split("|", 1)[0].strip()
        if "-" in rng:
            a, b = rng.split("-", 1)
            return a.strip(), b.strip()
    except Exception:
        pass
    return "", ""


st.set_page_config(page_title="Neurodiverz Családi Command Center v4.6.1", page_icon="🧩", layout="wide")

st.markdown("""
<style>
.hero{border-radius:24px;padding:24px;margin-bottom:18px;background:linear-gradient(135deg,#0f172a,#1e293b);border:1px solid rgba(255,255,255,.12)}
.hero-title{font-size:2rem;font-weight:900}.hero-sub{color:#cbd5e1;font-size:1rem;line-height:1.45}
.card{border-radius:18px;padding:18px;margin-bottom:14px;background:rgba(31,41,55,.75);border:1px solid rgba(255,255,255,.10)}
.pill{display:inline-block;padding:5px 10px;border-radius:999px;font-weight:800;margin-bottom:8px}.red{background:#7f1d1d;color:#fecaca}.yellow{background:#713f12;color:#fde68a}.green{background:#14532d;color:#bbf7d0}.blue{background:#1e3a8a;color:#bfdbfe}
</style>
""", unsafe_allow_html=True)

DAYS = ["Hétfő","Kedd","Szerda","Csütörtök","Péntek","Szombat","Vasárnap"]
WORKDAYS = ["Hétfő","Kedd","Szerda","Csütörtök","Péntek"]
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
MORNING_OPTIONS = {"Jó / kipihent":0,"Kissé nehéz indulás":1,"Fáradt":2,"Nyűgös / feszült":3,"Nagyon nehéz reggel":4}
MEAL_OPTIONS = {"Rendben evett":0,"Kicsit kevesebbet":1,"Válogatós / keveset":2,"Kimondottan problémás":3}
WEATHER_OPTIONS = ["Nincs külön hatás","Front / időjárás érzékenység","Nagy meleg","Hideg / eső","Erős szél","Nem tudjuk"]
CHALLENGE_OPTIONS = ["Nem volt","Ordítás / sírás","Verekedés / agresszió","Elvonulás / shutdown","Erős ellenállás","Iskolai/óvodai nehézség","Testvérkonfliktus","Alvás előtti kiborulás"]
CHALLENGE_TIME_OPTIONS = ["Nem volt","Reggel","Délelőtt","Dél körül","Délután","Este","Lefekvés előtt","Éjszaka"]
CHALLENGE_PHASE_OPTIONS = ["Nem volt","Program előtt","Program közben","Program után","Átálláskor / induláskor","Hazaérkezés után","Várakozás közben","Szabad játék közben","Étkezés körül","Alvás / lefekvés körül"]
CHALLENGE_LOCATION_OPTIONS = ["Nem volt","Otthon","Udvar / játszótér","Óvoda / iskola","Fejlesztés / terápia","Sport","Bolt / ügyintézés","Utazás közben","Családi programon","Ismeretlen / nem egyértelmű"]
CHALLENGE_TRIGGER_OPTIONS = ["Nem volt","Fáradtság","Éhség / szomjúság","Zaj / sok inger","Sok ember","Váratlan változás","Átállás / indulás","Várakozás","Túl hosszú program","Túl sok elvárás","Testvér / társas konfliktus","Veszteség / kudarc","Nem sikerült megnyugodni","Képernyő lezárása","Nem tudjuk"]
CHALLENGE_DURATION_OPTIONS = ["Nem volt","0–5 perc","5–15 perc","15–30 perc","30–60 perc","60+ perc","Hullámzó / visszatérő"]
SETTLE_OPTIONS = ["Nem kellett","Ölelés","Csendes szoba","Takaró alá bújás","Kedvenc zene","Mese / képernyő","Kütyüidő","Közös kuckózás","Mozgás","Tudatos légzés","Kedvenc tárgy"]

REWARD_OPTIONS = [
    "1 kocka csoki",
    "2 szem gumicukor",
    "Kakaó",
    "Kedvenc nasi",
    "Bubifújózás",
    "Játszótér",
    "Közös mese",
    "Társasjáték",
    "Közös kuckózás",
    "Séta",
    "Ő választ esti mesét",
    "Ő választ zenét",
    "Ő választ játékot"
]

HEALTH_OPTIONS = ["Nincs","Allergia","Megfázás / influenza","Hasfájás","Fejfájás","Gyógyszerváltás","ADHD tünetek erősebbek","Egyéb"]

@st.cache_resource
def get_sb() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_ANON_KEY"])

def restore_session(sb: Client):
    if st.session_state.get("access_token") and st.session_state.get("refresh_token"):
        try:
            sb.auth.set_session(st.session_state["access_token"], st.session_state["refresh_token"])
        except Exception:
            pass

def login_required(sb: Client):
    restore_session(sb)
    if st.session_state.get("user"):
        return st.session_state["user"]
    st.markdown('<div class="hero"><div class="hero-title">🧩 Neurodiverz Családi Command Center</div><div class="hero-sub">Felhőalapú, többfelhasználós családi stabilitástervező. Lépj be vagy regisztrálj.</div></div>', unsafe_allow_html=True)
    tab1, tab2 = st.tabs(["Belépés", "Regisztráció"])
    with tab1:
        email = st.text_input("Email", key="login_email")
        password = st.text_input("Jelszó", type="password", key="login_pw")
        if st.button("Belépés", use_container_width=True):
            try:
                res = sb.auth.sign_in_with_password({"email": email, "password": password})
                st.session_state["user"] = {"id": res.user.id, "email": res.user.email}
                st.session_state["access_token"] = res.session.access_token
                st.session_state["refresh_token"] = res.session.refresh_token
                st.rerun()
            except Exception as exc:
                st.error(f"Belépés sikertelen: {exc}")
    with tab2:
        email = st.text_input("Email", key="signup_email")
        password = st.text_input("Jelszó", type="password", key="signup_pw")
        if st.button("Regisztráció", use_container_width=True):
            try:
                sb.auth.sign_up({"email": email, "password": password})
                st.success("Regisztráció kész. Ha be van kapcsolva email megerősítés, nézd meg a postafiókod.")
            except Exception as exc:
                st.error(f"Regisztráció sikertelen: {exc}")
    st.stop()

def logout():
    for k in ["user","access_token","refresh_token"]:
        st.session_state.pop(k, None)
    st.rerun()

def q(table: str): return get_sb().table(table)

def df_from(res): return pd.DataFrame(res.data or [])

def load_children(sb): return df_from(sb.table("children").select("*").order("created_at").execute())
def load_events(sb, child_id, week): return df_from(sb.table("weekly_events").select("*").eq("child_id", child_id).eq("week_label", week).execute())
def load_all_events(sb, child_id): return df_from(sb.table("weekly_events").select("*").eq("child_id", child_id).execute())
def load_checkins(sb, child_id, week): return df_from(sb.table("daily_checkins").select("*").eq("child_id", child_id).eq("week_label", week).execute())
def load_all_checkins(sb, child_id): return df_from(sb.table("daily_checkins").select("*").eq("child_id", child_id).execute())

def safe_day_order_df(df: pd.DataFrame, day_col: str = "Nap") -> pd.DataFrame:
    if df is None or df.empty or day_col not in df.columns:
        return df
    out = df.copy()
    out["_nap_sorrend"] = out[day_col].map({d:i for i,d in enumerate(DAYS)}).fillna(99)
    return out.sort_values("_nap_sorrend").drop(columns=["_nap_sorrend"])

def collapse_checkins_by_day(checkins_df: pd.DataFrame) -> pd.DataFrame:
    # Egy napra csak egy napi rekordot hagyunk az elemzéshez.
    if checkins_df is None or checkins_df.empty or "day" not in checkins_df.columns:
        return pd.DataFrame() if checkins_df is None else checkins_df
    df = checkins_df.copy()
    if "created_at" in df.columns:
        df = df.sort_values("created_at")
    numeric_cols = ["reggeli_allapot_pont","esti_allapot_pont","napkozbeni_faradsag","alvas_minosege","etkezes_pont","kutyuidoperc","elvaras_ido","sajat_regeneracio_ido"]
    agg = {}
    for c in df.columns:
        if c == "day":
            continue
        agg[c] = "mean" if c in numeric_cols else "last"
    return df.groupby("day", as_index=False).agg(agg)

def delete_checkins_for_day(sb, child_id, week_label, day):
    return sb.table("daily_checkins").delete().eq("child_id", child_id).eq("week_label", week_label).eq("day", day).execute()

def save_single_checkin_for_day(sb, payload: Dict):
    # Új szabály: egy naphoz egy aktív check-in. Mentéskor töröljük az aznapi régieket, majd beszúrjuk az újat.
    delete_checkins_for_day(sb, payload["child_id"], payload["week_label"], payload["day"])
    return sb.table("daily_checkins").insert(payload).execute()

def cleanup_duplicate_checkins_current_week(sb, child_id, week_label) -> int:
    df = load_checkins(sb, child_id, week_label)
    if df is None or df.empty or "day" not in df.columns or "id" not in df.columns:
        return 0
    if "created_at" in df.columns:
        df = df.sort_values("created_at", ascending=False)
    deleted = 0
    for day, grp in df.groupby("day"):
        if len(grp) <= 1:
            continue
        # legfrissebb marad, többi törlődik
        for _, row in grp.iloc[1:].iterrows():
            sb.table("daily_checkins").delete().eq("id", row["id"]).execute()
            deleted += 1
    return deleted


def split_text(x): return [p.strip() for p in str(x or "").split(",") if p.strip()]
def weight(level): return 0.6 + (int(level)-1)*0.25
def clamp(x): return int(max(0, min(100, round(float(x)))))
def score_color(score, inverse=False):
    if inverse: return "🔴" if score >=75 else ("🟠" if score >=50 else "🟢")
    return "🟢" if score >=75 else ("🟠" if score >=50 else "🔴")

def calculate_event_load(event: Dict, profile: Dict) -> float:
    p = PROGRAM_TYPES[event["program_tipus"]]
    load = p["base"] + p["sensory"]*weight(profile.get("sok_ember_zaj",3)) + p["social"]*weight(profile.get("tarsas_helyzet",3)) + p["transition"]*weight(profile.get("atallas",3))
    load += max(0, float(event.get("idotartam_ora",1))-1)*1.2
    travel = int(event.get("utazas_perc",0))
    if travel >= 45: load += 5*weight(profile.get("utazas",3))
    elif travel >= 20: load += 2.5*weight(profile.get("utazas",3))
    envs = split_text(event.get("kornyezeti_tenyezok",""))
    if "Sok ember" in envs or "Zsúfolt hely" in envs: load += 5*weight(profile.get("sok_ember_zaj",3))
    if "Hangos hely" in envs: load += 4*weight(profile.get("sok_ember_zaj",3))
    if "Új hely" in envs: load += 4*weight(profile.get("rutinvalidas",3))
    if event.get("kiszamithatosag") == "Váratlan / bizonytalan": load += 6*weight(profile.get("rutinvalidas",3))
    elif event.get("kiszamithatosag") == "Részben kiszámítható": load += 3*weight(profile.get("rutinvalidas",3))
    if event["program_tipus"] in ["Otthoni nyugodt blokk","Szabad játék / pihenés"]: load -= 4*weight(profile.get("recovery_igeny",4))
    return round(load,1)

def norm_events(df):
    if df.empty: return df
    return df.rename(columns={"day":"Nap","program_tipus":"program_típus","idotartam_ora":"időtartam_óra","utazas_perc":"utazás_perc","atallas_szam":"átállás_szám","kiszamithatosag":"kiszámíthatóság","kornyezeti_tenyezok":"környezeti_tényezők","recovery_ora":"recovery_óra","szuloi_terheles":"szülői_terhelés","terhelesi_pont":"terhelési_pont"})

def norm_checkins(df):
    if df.empty: return df
    return df.rename(columns={"day":"Nap","reggeli_allapot":"Reggeli állapot","reggeli_allapot_pont":"Reggeli állapot pont","esti_allapot":"Esti állapot","esti_allapot_pont":"Esti állapot pont","napkozbeni_faradsag":"Napközbeni fáradtság","alvas_minosege":"Alvás minősége","etkezes":"Étkezés","etkezes_pont":"Étkezés pont","kutyuidoperc":"Kütyüidő perc","kulso_tenyezo":"Külső tényező","elvaras_ido":"Elvárásokkal töltött idő","sajat_regeneracio_ido":"Saját regenerációs idő","kihivas_helyzet":"Kihívást jelentő helyzet","megnyugvast_segitette":"Megnyugvást segítette","mi_segitett_szabad_szoveg":"Mi segített – saját","idoszakos_eu_allapot":"Időszakos eü. állapot"})

def normalize_events_df(events_df: pd.DataFrame) -> pd.DataFrame:
    """Supabase eseményadatok magyar, biztonságos megjelenítése.
    Kezeli a régi, időpont nélküli sorokat is.
    """
    if events_df is None or events_df.empty:
        return pd.DataFrame()

    rename = {
        "program_tipus": "program_típus",
        "idotartam_ora": "időtartam_óra",
        "utazas_perc": "utazás_perc",
        "atallas_szam": "átállás_szám",
        "kiszamithatosag": "kiszámíthatóság",
        "kornyezeti_tenyezok": "környezeti_tényezők",
        "recovery_ora": "recovery_óra",
        "szuloi_terheles": "szülői_terhelés",
        "terhelesi_pont": "terhelési_pont",
        "day": "Nap",
    }

    out = events_df.rename(columns=rename).copy()

    def _clean_local(value):
        text = str(value or "")
        if "| Idő:" in text:
            return text.split("| Idő:", 1)[0].strip()
        return text

    def _parse_time_local(value):
        text = str(value or "")
        if "| Idő:" not in text:
            return "nincs megadva"
        try:
            rng = text.split("| Idő:", 1)[1].split("|", 1)[0].strip()
            return rng.replace("-", "–")
        except Exception:
            return "nincs megadva"

    # Időpont oszlop a naptárhoz / táblához
    if "kiszámíthatóság" in out.columns:
        out["Idő"] = out["kiszámíthatóság"].apply(_parse_time_local)
        out["kiszámíthatóság"] = out["kiszámíthatóság"].apply(_clean_local)
    else:
        out["Idő"] = "nincs megadva"

    # Nap szerinti rendezés, ha van Nap oszlop
    if "Nap" in out.columns:
        out["_nap_sorrend"] = out["Nap"].map({d: i for i, d in enumerate(DAYS)})
        out = out.sort_values(["_nap_sorrend"]).drop(columns=["_nap_sorrend"])

    # A legfontosabb oszlopokat előre tesszük, a többi maradhat mögötte
    preferred = [
        "Nap", "Idő", "program_típus", "időtartam_óra", "utazás_perc",
        "átállás_szám", "kiszámíthatóság", "környezeti_tényezők",
        "recovery_óra", "szülői_terhelés", "terhelési_pont"
    ]
    ordered_cols = [c for c in preferred if c in out.columns] + [c for c in out.columns if c not in preferred]
    return out[ordered_cols]




def calculate_reward_points(checkins_df: pd.DataFrame) -> int:
    if checkins_df is None or checkins_df.empty:
        return 0
    if "day" not in checkins_df.columns:
        return 0
    return len(checkins_df["day"].dropna().unique())


def reward_level(points: int) -> str:
    if points >= 7:
        return "Arany hét"
    if points >= 5:
        return "Szuper hét"
    if points >= 3:
        return "Jó úton"
    return "Kezdő gyűjtés"


def build_day_summary(events_df, checkins_df):
    checkins_df = collapse_checkins_by_day(checkins_df)
    if events_df.empty: return pd.DataFrame()
    e = norm_events(events_df)
    s = e.groupby("Nap", as_index=False).agg(Programok=("program_típus","count"), Terhelés=("terhelési_pont","sum"), Átállások=("átállás_szám","sum"), Recovery_órák=("recovery_óra","sum"), Szülői_terhelés=("szülői_terhelés","sum"))
    s["Kockázat"] = s["Terhelés"] + s["Átállások"]*2 + s["Szülői_terhelés"] - s["Recovery_órák"]*4
    s["_o"] = s["Nap"].map({d:i for i,d in enumerate(DAYS)})
    s = s.sort_values("_o").drop(columns="_o")
    if not checkins_df.empty:
        c = norm_checkins(checkins_df)
        cols = [x for x in ["Nap","Esti állapot pont","Esti állapot","Reggeli állapot pont","Étkezés pont","Kütyüidő perc","Napközbeni fáradtság","Elvárásokkal töltött idő","Saját regenerációs idő"] if x in c.columns]
        s = s.merge(c[cols], on="Nap", how="left")
        for col,m in [("Reggeli állapot pont",3),("Esti állapot pont",4),("Étkezés pont",3),("Napközbeni fáradtság",2.5),("Elvárásokkal töltött idő",1.2)]:
            if col in s: s["Kockázat"] += s[col].fillna(0)*m
        if "Kütyüidő perc" in s: s["Kockázat"] += (s["Kütyüidő perc"].fillna(0)/30)*2
        if "Saját regenerációs idő" in s: s["Kockázat"] -= s["Saját regenerációs idő"].fillna(0)*2
    return s

def generate_insights(day_summary, profile, events_df, checkins_df):
    out=[]
    if day_summary.empty: return [{"Szint":"INFO","Téma":"Nincs még adat","Mit látunk?":"Adj hozzá heti programokat.","Mit érdemes tenni?":"Kezdd a fix programokkal: óvoda/iskola, fejlesztés, sport, családi programok."}]
    overload = day_summary[day_summary["Kockázat"]>=50]
    if len(overload): out.append({"Szint":"FIGYELMEZTETÉS","Téma":"Túlterhelt napok","Mit látunk?":f"Magasabb idegrendszeri terhelés látszik: {', '.join(overload['Nap'])}.","Mit érdemes tenni?":"Kevesebb plusz program, több előrejelzés és több nyugodt blokk javasolt."})
    low_rec = day_summary[day_summary["Recovery_órák"]<1]
    if len(low_rec)>=3: out.append({"Szint":"FIGYELMEZTETÉS","Téma":"Kevés recovery","Mit látunk?":"Több napon kevés valódi lecsendesedési idő látszik.","Mit érdemes tenni?":"Tegyél be legalább 2–3 rövid, védett nyugalmi blokkot."})
    ordered = safe_day_order_df(day_summary.groupby("Nap", as_index=False).agg(lambda x: x.mean() if pd.api.types.is_numeric_dtype(x) else x.iloc[-1])).fillna(0)
    streak=max_streak=0
    for high in (ordered["Kockázat"]>=45):
        streak = streak+1 if high else 0; max_streak=max(max_streak,streak)
    if max_streak>=3: out.append({"Szint":"KRITIKUS","Téma":"Egymást követő nehéz napok","Mit látunk?":"Legalább 3 egymást követő magasabb terhelésű nap látszik.","Mit érdemes tenni?":"Tegyél recovery blokkot a sorozat közepére vagy végére."})
    if int(profile.get("screen_sensitivity",3))>=4 and not checkins_df.empty and "kutyuidoperc" in checkins_df:
        if len(checkins_df[checkins_df["kutyuidoperc"]>=45]): out.append({"Szint":"FIGYELMEZTETÉS","Téma":"Képernyőidő figyelendő","Mit látunk?":"A profil szerint a képernyő érzékeny pont, és volt magasabb kütyüidő.","Mit érdemes tenni?":"Teszteld, hogy a képernyőidő csökkentése javítja-e az esti állapotot vagy a másnapot."})
    if not out: out.append({"Szint":"INFO","Téma":"Kezelhető hét","Mit látunk?":"Nincs kiugró túlterhelési jel.","Mit érdemes tenni?":"Tartsd meg a nyugodt blokkokat, és rögzíts check-int."})
    return out

def engagement(checkins):
    n = checkins["day"].nunique() if not checkins.empty and "day" in checkins else 0
    if n>=7: return "🏆 Hibátlan hét: minden naphoz van check-in."
    if n>=5: return "🌟 Nagyon jó: már legalább 5 napot rögzítettetek."
    if n>=3: return "✅ Szép munka: már látszanak a mintázatok."
    if n>=1: return "👍 Jó kezdés: már egy check-in is hasznos."
    return "🧩 Kezdd egyetlen napi check-innel. Nem kell tökéletesen vezetni."


def build_deeper_conclusions(summary, profile, events, checkins):
    conclusions=[]
    if summary.empty: return conclusions
    hardest=summary.sort_values("Kockázat",ascending=False).iloc[0]
    conclusions.append({"Cím":"A hét legnehezebb pontja","Következtetés":f"A legnagyobb terhelés most ezen a napon látszik: {hardest['Nap']}.","Javaslat":"Ha csak egy dolgon változtattok, először ezt a napot érdemes könnyíteni vagy több recoveryt tenni utána."})
    if "Kütyüidő perc" in summary.columns and summary["Kütyüidő perc"].notna().sum()>=2 and int(profile.get("screen_sensitivity",3))>=3:
        high=summary[summary["Kütyüidő perc"].fillna(0)>=45]
        if len(high): conclusions.append({"Cím":"Képernyőidő mintázat","Következtetés":"Volt olyan nap, amikor magasabb képernyőidő jelent meg, és a profil alapján ez érzékeny terület lehet.","Javaslat":"Érdemes 1–2 hétig figyelni, hogy a plusz képernyőidő után romlik-e az esti állapot vagy a másnap."})
    if "Étkezés pont" in summary.columns and summary["Étkezés pont"].fillna(0).max()>=2:
        conclusions.append({"Cím":"Étkezési jelzés","Következtetés":"Az étkezésben látszik eltérés valamelyik napon. Ez sok neurodivergens gyereknél korai fáradási jel lehet.","Javaslat":"Érdemes figyelni, hogy az étkezési változás együtt jár-e fáradtsággal, ingerlékenységgel vagy több képernyőigénnyel."})
    if summary["Recovery_órák"].sum()<4:
        conclusions.append({"Cím":"Kevés visszatöltő idő","Következtetés":"A héten kevés tervezett nyugodt blokk látszik.","Javaslat":"Tegyél be legalább két rövidebb, védett lecsendesedési időt. A cél nem a programok törlése, hanem a hét fenntarthatóbbá tétele."})
    if not checkins.empty and "megnyugvast_segitette" in checkins.columns:
        helped=[]
        for v in checkins["megnyugvast_segitette"].dropna().astype(str): helped += [x.strip() for x in v.split(",") if x.strip()]
        if helped:
            top=pd.Series(helped).value_counts().index[0]
            conclusions.append({"Cím":"Ami működni látszik","Következtetés":f"A visszajelzések alapján ez többször megjelent segítő stratégiaként: {top}.","Javaslat":"Ezt érdemes tudatosan előre betervezni a nehezebb napok elé vagy után."})
    return conclusions[:6]

def pdf_safe(x):
    return str(x or "").replace("ő","ö").replace("Ő","Ö").replace("ű","ü").replace("Ű","Ü")


def classify_week_type(day_summary: pd.DataFrame) -> Dict[str, str]:
    """Heti összkép egyszerű, szülőbarát besorolással."""
    if day_summary.empty:
        return {"Típus": "Nincs elég adat", "Magyarázat": "Még nincs elég heti adat a besoroláshoz."}

    avg_risk = day_summary["Kockázat"].mean()
    max_risk = day_summary["Kockázat"].max()
    std_risk = day_summary["Kockázat"].std() if len(day_summary) > 1 else 0
    recovery_sum = day_summary.get("Recovery_órák", pd.Series(dtype=float)).sum()

    ordered = safe_day_order_df(day_summary.groupby("Nap", as_index=False).agg(lambda x: x.mean() if pd.api.types.is_numeric_dtype(x) else x.iloc[-1])).fillna(0)
    ordered["Kockázat"] = ordered["Kockázat"].fillna(0)
    second_half = ordered[ordered["Nap"].isin(["Csütörtök", "Péntek", "Szombat", "Vasárnap"])]["Kockázat"].mean()
    first_half = ordered[ordered["Nap"].isin(["Hétfő", "Kedd", "Szerda"])]["Kockázat"].mean()

    if max_risk >= 75 or avg_risk >= 55:
        return {
            "Típus": "Túlterhelt hét",
            "Magyarázat": "A hét egészében vagy legalább egy napon magas idegrendszeri terhelés látszik."
        }
    if second_half > first_half + 15:
        return {
            "Típus": "Fáradó hét",
            "Magyarázat": "A hét második felére emelkedik a terhelés, ami fokozatos kifáradásra utalhat."
        }
    if std_risk >= 20:
        return {
            "Típus": "Hullámzó hét",
            "Magyarázat": "A napok terhelése nagyon eltérő. Ilyenkor nehéz lehet kiszámítható ritmust tartani."
        }
    if recovery_sum < 4:
        return {
            "Típus": "Recovery-hiányos hét",
            "Magyarázat": "Kevés tervezett visszatöltő idő látszik a héten."
        }
    return {
        "Típus": "Alapvetően stabil hét",
        "Magyarázat": "A jelenlegi adatok alapján nincs erős túlterhelési minta."
    }


def _safe_mean(series):
    try:
        vals = pd.to_numeric(series, errors="coerce").dropna()
        return vals.mean() if len(vals) else np.nan
    except Exception:
        return np.nan



def parse_challenge_details(value: object) -> Dict[str, str]:
    """A régi és új 'kihivas_helyzet' mezőből is olvasható részletek."""
    text = "" if value is None else str(value)
    result = {
        "alap": text.strip(),
        "időszak": "",
        "kapcsolódás": "",
        "helyzet": "",
        "kiváltó": "",
        "időtartam": "",
    }
    if "|" not in text:
        return result
    parts = [p.strip() for p in text.split("|")]
    result["alap"] = parts[0] if parts else ""
    for p in parts[1:]:
        if ":" in p:
            k, v = p.split(":", 1)
            k = k.strip().lower()
            v = v.strip()
            if "időszak" in k:
                result["időszak"] = v
            elif "kapcsolódás" in k:
                result["kapcsolódás"] = v
            elif "helyzet" in k:
                result["helyzet"] = v
            elif "kiváltó" in k:
                result["kiváltó"] = v
            elif "időtartam" in k:
                result["időtartam"] = v
    return result


def build_prognosis_engine(day_summary: pd.DataFrame, profile: Dict, events_df: pd.DataFrame, checkins_df: pd.DataFrame) -> pd.DataFrame:
    """Egyszerű, szabályalapú előrejelző réteg a következő napokra / hétre."""
    rows = []
    if day_summary.empty:
        return pd.DataFrame([{
            "Terület": "Nincs elég adat",
            "Előrejelzés": "Adj hozzá programokat és néhány check-int, és a rendszer óvatos prognózist ad.",
            "Mire figyelj?": "A prognózis nem diagnózis, csak tervezési segítség.",
            "Megelőző lépés": "Kezdd napi 1 rövid check-innel."
        }])

    ordered = safe_day_order_df(day_summary.groupby("Nap", as_index=False).agg(lambda x: x.mean() if pd.api.types.is_numeric_dtype(x) else x.iloc[-1])).fillna(0)
    ordered["Kockázat"] = pd.to_numeric(ordered["Kockázat"], errors="coerce").fillna(0)
    ordered["Recovery_órák"] = pd.to_numeric(ordered.get("Recovery_órák", 0), errors="coerce").fillna(0)

    # Következő magas kockázatú napok
    risk_days = ordered[ordered["Kockázat"] >= 45]
    if not risk_days.empty:
        rows.append({
            "Terület": "Következő nehezebb napok",
            "Előrejelzés": f"Ezek a napok előre terheltebbnek tűnnek: {', '.join(risk_days['Nap'].astype(str).tolist())}.",
            "Mire figyelj?": "Ezeken a napokon könnyebben jöhet túlterhelés, főleg ha kevés a lecsendesedési idő.",
            "Megelőző lépés": "Előre jelezd a nap menetét, és tervezz rövid, elvárásmentes blokkot a legterheltebb program után."
        })

    # Halmozódás / sorozat
    streak = 0
    max_streak = 0
    for val in ordered["Kockázat"] >= 40:
        streak = streak + 1 if val else 0
        max_streak = max(max_streak, streak)
    if max_streak >= 2:
        rows.append({
            "Terület": "Terhelés halmozódása",
            "Előrejelzés": "Több egymást követő figyelendő nap látszik.",
            "Mire figyelj?": "Ilyenkor nem mindig az első nehéz nap borít, hanem a második-harmadik.",
            "Megelőző lépés": "A sorozat közepére tegyél egy alacsony ingerű délutánt vagy rövidebb programot."
        })

    # Hét végi kifáradás
    first = ordered[ordered["Nap"].isin(["Hétfő","Kedd","Szerda"])]["Kockázat"].mean()
    second = ordered[ordered["Nap"].isin(["Csütörtök","Péntek","Szombat","Vasárnap"])]["Kockázat"].mean()
    if pd.notna(first) and pd.notna(second) and second > first + 10:
        rows.append({
            "Terület": "Hétvégi / hétvége előtti fáradás",
            "Előrejelzés": "A hét második fele nehezebbnek tűnik.",
            "Mire figyelj?": "A csütörtök-péntek körüli fáradás sokszor késleltetve jelenik meg.",
            "Megelőző lépés": "Csütörtök után érdemes kevesebb új helyzetet és több kiszámítható rutint hagyni."
        })

    # Challenge részletek alapján trigger prognózis
    if not checkins_df.empty and "kihivas_helyzet" in checkins_df.columns:
        parsed = checkins_df["kihivas_helyzet"].dropna().apply(parse_challenge_details)
        triggers = [x.get("kiváltó","") for x in parsed if x.get("kiváltó","") and x.get("kiváltó","") != "Nem volt"]
        phases = [x.get("kapcsolódás","") for x in parsed if x.get("kapcsolódás","") and x.get("kapcsolódás","") != "Nem volt"]
        times = [x.get("időszak","") for x in parsed if x.get("időszak","") and x.get("időszak","") != "Nem volt"]
        if triggers:
            top_trigger = pd.Series(triggers).value_counts().index[0]
            rows.append({
                "Terület": "Visszatérő kiváltó ok",
                "Előrejelzés": f"A rögzített adatok alapján ez figyelendő trigger lehet: {top_trigger}.",
                "Mire figyelj?": "Nem biztos, hogy ez az ok, de érdemes a következő hetekben külön megfigyelni.",
                "Megelőző lépés": "Ha ez a trigger várható, előtte legyen rövid előrejelzés, utána pedig visszatöltő blokk."
            })
        if phases:
            top_phase = pd.Series(phases).value_counts().index[0]
            rows.append({
                "Terület": "Mikor jelenik meg a nehézség?",
                "Előrejelzés": f"A nehéz helyzetek gyakran ehhez kapcsolódhatnak: {top_phase}.",
                "Mire figyelj?": "A program előtti, közbeni és utáni nehézség más-más megelőzést igényel.",
                "Megelőző lépés": "A kapcsolódó időszakba tegyél több kiszámíthatóságot és kevesebb elvárást."
            })
        if times:
            top_time = pd.Series(times).value_counts().index[0]
            rows.append({
                "Terület": "Napszakos érzékenység",
                "Előrejelzés": f"A rögzített nehézségek gyakrabban ebben az időszakban jelentek meg: {top_time}.",
                "Mire figyelj?": "Lehet, hogy a napszak önmagában is kapacitáscsökkenést jelez.",
                "Megelőző lépés": "Ebben az időszakban érdemes kevesebb plusz döntést és átállást kérni."
            })

    # Screen prognózis
    if not checkins_df.empty and "kutyuidoperc" in checkins_df.columns and int(profile.get("screen_sensitivity", 3)) >= 4:
        avg_screen = pd.to_numeric(checkins_df["kutyuidoperc"], errors="coerce").dropna().mean()
        if pd.notna(avg_screen) and avg_screen >= 45:
            rows.append({
                "Terület": "Képernyőérzékenység",
                "Előrejelzés": "A profil és az adatok alapján a képernyőidő külön figyelendő.",
                "Mire figyelj?": "A hatás nem mindig azonnali; lehet esti vagy másnapi feszültség.",
                "Megelőző lépés": "Ne teljes tiltással kezdj, hanem tesztelj 1 héten át rövidebb vagy korábbi képernyőidőt."
            })

    if not rows:
        rows.append({
            "Terület": "Óvatos prognózis",
            "Előrejelzés": "A jelenlegi adatok alapján nincs erős előrejelző jel.",
            "Mire figyelj?": "Ez nem azt jelenti, hogy biztosan könnyű hét lesz, csak nincs még elég markáns minta.",
            "Megelőző lépés": "Folytasd a rövid check-ineket; 2–3 hét után pontosabb lesz a rendszer."
        })

    return pd.DataFrame(rows[:8])


def build_challenge_pattern_table(checkins_df: pd.DataFrame) -> pd.DataFrame:
    """Kihívást jelentő helyzetek áttekintése strukturáltan."""
    if checkins_df.empty or "kihivas_helyzet" not in checkins_df.columns:
        return pd.DataFrame()
    rows = []
    for _, r in checkins_df.iterrows():
        details = parse_challenge_details(r.get("kihivas_helyzet", ""))
        if details.get("alap", "") and details.get("alap", "") != "Nem volt":
            rows.append({
                "Nap": r.get("day", ""),
                "Helyzet": details.get("alap", ""),
                "Időszak": details.get("időszak", ""),
                "Kapcsolódás": details.get("kapcsolódás", ""),
                "Helyszín": details.get("helyzet", ""),
                "Kiváltó": details.get("kiváltó", ""),
                "Időtartam": details.get("időtartam", ""),
            })
    return pd.DataFrame(rows)


def build_neurodiverz_insight_engine(
    day_summary: pd.DataFrame,
    profile: Dict,
    events_df: pd.DataFrame,
    checkins_df: pd.DataFrame
) -> Dict[str, pd.DataFrame]:
    """Mélyebb, több rétegű insight motor AI nélkül."""
    weekly_rows = []
    day_rows = []
    pattern_rows = []
    positive_rows = []
    micro_rows = []

    if day_summary.empty:
        empty = pd.DataFrame(columns=["Típus", "Megállapítás", "Miért fontos?", "Javaslat"])
        return {
            "heti_osszkep": empty,
            "napi_fokusz": empty,
            "mintazatok": empty,
            "pozitiv_jelek": empty,
            "mikro_javaslatok": empty,
        }

    week_type = classify_week_type(day_summary)
    weekly_rows.append({
        "Típus": week_type["Típus"],
        "Megállapítás": week_type["Magyarázat"],
        "Miért fontos?": "A heti ritmus sokszor fontosabb, mint egyetlen program önmagában.",
        "Javaslat": "A cél nem minden terhelés megszüntetése, hanem a nehéz napok köré elég visszatöltő időt tenni."
    })

    ordered = safe_day_order_df(day_summary.groupby("Nap", as_index=False).agg(lambda x: x.mean() if pd.api.types.is_numeric_dtype(x) else x.iloc[-1])).fillna(0)
    ordered["Kockázat"] = pd.to_numeric(ordered["Kockázat"], errors="coerce").fillna(0)
    ordered["Recovery_órák"] = pd.to_numeric(ordered.get("Recovery_órák", 0), errors="coerce").fillna(0)

    # Több nap fókusz: top 3 nem csak legmagasabb
    top_days = ordered[ordered["Kockázat"] > 0].sort_values("Kockázat", ascending=False).head(3)
    for _, row in top_days.iterrows():
        level = "Magas" if row["Kockázat"] >= 55 else ("Közepes" if row["Kockázat"] >= 35 else "Figyelendő")
        day_rows.append({
            "Nap": row["Nap"],
            "Fókusz": f"{level} terhelés",
            "Mit látunk?": f"{row['Nap']} kockázati pontja: {row['Kockázat']:.0f}.",
            "Javaslat": "Ezen a napon érdemes előre jelezni a programokat, és legalább egy rövid lecsendesedési blokkot biztosítani."
        })

    # Hét második felének kifáradása
    first = ordered[ordered["Nap"].isin(["Hétfő", "Kedd", "Szerda"])]["Kockázat"].mean()
    second = ordered[ordered["Nap"].isin(["Csütörtök", "Péntek", "Szombat", "Vasárnap"])]["Kockázat"].mean()
    if pd.notna(first) and pd.notna(second) and second > first + 12:
        pattern_rows.append({
            "Minta": "Hét második felére emelkedő terhelés",
            "Mit látunk?": "A hét második fele nehezebbnek tűnik, mint az első.",
            "Miért fontos?": "Sok neurodivergens gyereknél a hét végére csökken a tartalék, még akkor is, ha minden nap külön-külön kezelhetőnek tűnik.",
            "Javaslat": "Csütörtök-péntek környékére érdemes könnyebb délutánt vagy több saját regenerációs időt hagyni."
        })

    # Recovery minta
    low_rec_days = ordered[(ordered["Recovery_órák"] < 1) & (ordered["Kockázat"] > 25)]
    if len(low_rec_days) >= 2:
        pattern_rows.append({
            "Minta": "Nehéz napok kevés recoveryvel",
            "Mit látunk?": f"Több terheltebb napon kevés visszatöltő idő látszik: {', '.join(low_rec_days['Nap'].astype(str).tolist())}.",
            "Miért fontos?": "A gond sokszor nem a program, hanem az, hogy utána nincs idegrendszeri lecsengés.",
            "Javaslat": "A nehezebb programok után 20–40 perc elvárásmentes blokk sokat segíthet."
        })

    # Checkin alapú minták
    if not checkins_df.empty:
        c = checkins_df.copy()
        # expected raw supabase columns
        if "kutyuidoperc" in c.columns and "esti_allapot_pont" in c.columns:
            high_screen = c[pd.to_numeric(c["kutyuidoperc"], errors="coerce").fillna(0) >= 45]
            if len(high_screen) >= 1 and int(profile.get("screen_sensitivity", 3)) >= 3:
                pattern_rows.append({
                    "Minta": "Képernyőidő figyelendő",
                    "Mit látunk?": "Volt magasabb képernyőidővel járó nap.",
                    "Miért fontos?": "Egyes gyerekeknél a plusz képernyőidő nem aznap, hanem este vagy másnap jelentkezik terhelésként.",
                    "Javaslat": "Érdemes 1–2 hétig tesztelni: kevesebb képernyő a nehezebb napokon, és figyelni az esti állapotot."
                })

        if "etkezes_pont" in c.columns:
            meal_mean = _safe_mean(c["etkezes_pont"])
            if pd.notna(meal_mean) and meal_mean >= 1.4:
                pattern_rows.append({
                    "Minta": "Étkezés mint korai jel",
                    "Mit látunk?": "Több napon nem teljesen stabil az étkezés.",
                    "Miért fontos?": "Az étkezés romlása sok családnál hamarabb jelez túlterhelést, mint a látványos kiborulás.",
                    "Javaslat": "Nézzétek meg, hogy az étkezési eltérés együtt jár-e rosszabb alvással, fáradtsággal vagy képernyőigénnyel."
                })

        if "reggeli_allapot_pont" in c.columns and "esti_allapot_pont" in c.columns:
            morning_avg = _safe_mean(c["reggeli_allapot_pont"])
            evening_avg = _safe_mean(c["esti_allapot_pont"])
            if pd.notna(morning_avg) and pd.notna(evening_avg) and evening_avg > morning_avg + 1:
                pattern_rows.append({
                    "Minta": "Nap közbeni lemerülés",
                    "Mit látunk?": "Az esti állapot érezhetően rosszabb, mint a reggeli indulás.",
                    "Miért fontos?": "Ez arra utalhat, hogy a nap közbeni elvárások, ingerek vagy átállások fokozatosan merítik a gyermeket.",
                    "Javaslat": "Érdemes napközben is keresni mini visszatöltő pontokat, nem csak estére hagyni a lecsendesedést."
                })

        if "megnyugvast_segitette" in c.columns:
            helped = []
            for value in c["megnyugvast_segitette"].dropna().astype(str):
                helped += [x.strip() for x in value.split(",") if x.strip()]
            if helped:
                top_help = pd.Series(helped).value_counts().index[0]
                positive_rows.append({
                    "Pozitív minta": "Van működő megnyugvási stratégia",
                    "Mit látunk?": f"Ez többször is segítő tényezőként jelent meg: {top_help}.",
                    "Miért jó jel?": "Nem csak a nehézséget látjuk, hanem azt is, mi segít visszaterelni a rendszert.",
                    "Javaslat": "Ezt érdemes előre betervezni a nehezebb napok elé vagy után, nem csak utólag használni."
                })

        if "sajat_regeneracio_ido" in c.columns:
            rec_avg = _safe_mean(c["sajat_regeneracio_ido"])
            if pd.notna(rec_avg) and rec_avg >= 1.5:
                positive_rows.append({
                    "Pozitív minta": "Megjelent saját regenerációs idő",
                    "Mit látunk?": "Több napon volt saját tempójú pihenés vagy szabad játék.",
                    "Miért jó jel?": "A visszatöltő idő védőfaktor lehet a hét során.",
                    "Javaslat": "Ezt érdemes tudatosan megtartani, még akkor is, ha látszólag 'nem történik semmi'."
                })

    # Program alapú minták
    if not events_df.empty:
        e = events_df.copy()
        if "atallas_szam" in e.columns:
            high_transition_events = e[pd.to_numeric(e["atallas_szam"], errors="coerce").fillna(0) >= 3]
            if len(high_transition_events) >= 2 and int(profile.get("atallas", 3)) >= 3:
                pattern_rows.append({
                    "Minta": "Átállási terhelés",
                    "Mit látunk?": "Több program körül sok átállás jelenik meg.",
                    "Miért fontos?": "Az átállás sokszor láthatatlan terhelés: indulás, öltözés, érkezés, váltás, hazaérés.",
                    "Javaslat": "A sok átállásos napokon segíthet a vizuális sorrend, fix indulási rutin és plusz idő."
                })

        if "kornyezeti_tenyezok" in e.columns:
            crowded = e[e["kornyezeti_tenyezok"].fillna("").str.contains("Sok ember|Zsúfolt hely|Hangos hely", regex=True)]
            if len(crowded) >= 2 and int(profile.get("sok_ember_zaj", 3)) >= 3:
                pattern_rows.append({
                    "Minta": "Ingergazdag környezetek halmozódása",
                    "Mit látunk?": "Több zajos, zsúfolt vagy sok emberrel járó helyzet szerepel a héten.",
                    "Miért fontos?": "Ezek önmagukban is merítőek lehetnek, de egymás után különösen leterhelők.",
                    "Javaslat": "Ha nem lehet elkerülni, előtte/utána legyen kiszámítható, alacsony ingerű blokk."
                })

    # Mikro-javaslatok, mindig legyen néhány konkrét
    if not day_rows:
        micro_rows.append({
            "Javaslat": "Tartsátok meg a jelenlegi ritmust",
            "Mikor?": "A hét egészében",
            "Hogyan?": "A meglévő nyugodt blokkok és előrejelzések megtartása most fontosabb lehet, mint új szabályok bevezetése."
        })
    else:
        for row in day_rows[:3]:
            micro_rows.append({
                "Javaslat": f"{row['Nap']} könnyítése",
                "Mikor?": row["Nap"],
                "Hogyan?": "Egy plusz program elhagyása, rövidebb ott tartózkodás, vagy program után 20–30 perc elvárásmentes idő."
            })

    if len(positive_rows) == 0:
        positive_rows.append({
            "Pozitív minta": "Már maga a rögzítés is segítség",
            "Mit látunk?": "A hét adatai alapján elkezdhető a mintázatok keresése.",
            "Miért jó jel?": "Nem kell tökéletesen vezetni: néhány adatpont is segíthet a családnak kívülről ránézni a hétre.",
            "Javaslat": "A következő héten elég napi 1 gyors check-inre törekedni."
        })

    return {
        "heti_osszkep": pd.DataFrame(weekly_rows),
        "napi_fokusz": pd.DataFrame(day_rows),
        "mintazatok": pd.DataFrame(pattern_rows),
        "pozitiv_jelek": pd.DataFrame(positive_rows),
        "mikro_javaslatok": pd.DataFrame(micro_rows),
    }



def build_safe_pdf_report(profile, events_df, day_summary, insights_df, checkins_df, week_label):
    """Szebb, vizuális PDF export a Stabilitási elemzés oldal logikájához igazítva."""
    if SimpleDocTemplate is None:
        return None

    if insights_df is None:
        insights_df = pd.DataFrame()
    if day_summary is None:
        day_summary = pd.DataFrame()
    if events_df is None:
        events_df = pd.DataFrame()
    if checkins_df is None:
        checkins_df = pd.DataFrame()

    output = io.BytesIO()
    doc = SimpleDocTemplate(
        output,
        pagesize=A4,
        rightMargin=1.1*cm,
        leftMargin=1.1*cm,
        topMargin=0.9*cm,
        bottomMargin=0.9*cm,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "TitleClean",
        parent=styles["Title"],
        fontSize=18,
        leading=22,
        textColor=colors.HexColor("#0F172A"),
        spaceAfter=6,
    )
    subtitle_style = ParagraphStyle(
        "SubtitleClean",
        parent=styles["Normal"],
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#475569"),
        spaceAfter=8,
    )
    h2_style = ParagraphStyle(
        "H2Clean",
        parent=styles["Heading2"],
        fontSize=11,
        leading=14,
        textColor=colors.HexColor("#1E3A8A"),
        spaceBefore=8,
        spaceAfter=5,
    )
    body_style = ParagraphStyle(
        "BodyClean",
        parent=styles["Normal"],
        fontSize=8.2,
        leading=10.3,
        textColor=colors.HexColor("#0F172A"),
    )
    small_style = ParagraphStyle(
        "SmallClean",
        parent=styles["Normal"],
        fontSize=7.2,
        leading=9,
        textColor=colors.HexColor("#334155"),
    )
    white_style = ParagraphStyle(
        "WhiteClean",
        parent=styles["Normal"],
        fontSize=8,
        leading=10,
        textColor=colors.white,
    )

    def safe_text(x):
        text = str(x or "")
        # ReportLab alapfont miatt a hosszú ékezetek egyszerűsítése
        return text.replace("ő", "ö").replace("Ő", "Ö").replace("ű", "ü").replace("Ű", "Ü")

    def P(x, style=body_style):
        return Paragraph(safe_text(x), style)

    story = []
    child_name = profile.get("nickname") or profile.get("gyermek_neve") or "Gyermek"

    # Fejléc
    header = Table(
        [[
            P(f"Neurodiverz családi heti riport", white_style),
            P(f"{safe_text(child_name)} · {safe_text(week_label)}", white_style),
        ]],
        colWidths=[10.5*cm, 6.2*cm],
    )
    header.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), colors.HexColor("#1E3A8A")),
        ("BOX", (0,0), (-1,-1), 0, colors.HexColor("#1E3A8A")),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("LEFTPADDING", (0,0), (-1,-1), 9),
        ("RIGHTPADDING", (0,0), (-1,-1), 9),
        ("TOPPADDING", (0,0), (-1,-1), 8),
        ("BOTTOMPADDING", (0,0), (-1,-1), 8),
    ]))
    story.append(header)
    story.append(Spacer(1, 0.25*cm))
    story.append(P("A riport célja: átláthatóvá tenni a hét terhelését, visszatöltő idejét, mintázatait és a következő hétre vihető apró lépéseket.", subtitle_style))

    if day_summary.empty:
        story.append(P("Nincs elég adat a heti riporthoz.", body_style))
        doc.build(story)
        return output.getvalue()

    # Score-ok
    weekly_risk_raw = day_summary["Kockázat"].sum() if "Kockázat" in day_summary.columns else 0
    overload_risk = clamp(weekly_risk_raw / 330 * 100)
    recovery_sum = day_summary["Recovery_órák"].sum() if "Recovery_órák" in day_summary.columns else 0
    stability = clamp(100 - overload_risk + recovery_sum * 2)
    max_day = day_summary.sort_values("Kockázat", ascending=False).iloc[0] if "Kockázat" in day_summary.columns else day_summary.iloc[0]
    checkin_days = checkins_df["day"].nunique() if not checkins_df.empty and "day" in checkins_df.columns else 0

    def score_bg(value, inverse=False):
        if inverse:
            if value >= 75:
                return colors.HexColor("#FEE2E2")
            if value >= 50:
                return colors.HexColor("#FEF3C7")
            return colors.HexColor("#DCFCE7")
        else:
            if value >= 75:
                return colors.HexColor("#DCFCE7")
            if value >= 50:
                return colors.HexColor("#FEF3C7")
            return colors.HexColor("#FEE2E2")

    score_data = [
        [P("Heti stabilitás", small_style), P("Túlterhelési kockázat", small_style), P("Legnehezebb nap", small_style), P("Check-in napok", small_style)],
        [P(f"{stability}/100", title_style), P(f"{overload_risk}/100", title_style), P(str(max_day.get("Nap", max_day.get("day", ""))), title_style), P(f"{checkin_days}/7", title_style)],
    ]
    score_table = Table(score_data, colWidths=[4.15*cm, 4.15*cm, 4.15*cm, 4.15*cm])
    score_table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (0,1), score_bg(stability)),
        ("BACKGROUND", (1,0), (1,1), score_bg(overload_risk, inverse=True)),
        ("BACKGROUND", (2,0), (2,1), colors.HexColor("#EFF6FF")),
        ("BACKGROUND", (3,0), (3,1), colors.HexColor("#F5F3FF")),
        ("GRID", (0,0), (-1,-1), 0.45, colors.HexColor("#CBD5E1")),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("ALIGN", (0,0), (-1,-1), "CENTER"),
        ("TOPPADDING", (0,0), (-1,-1), 6),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
    ]))
    story.append(score_table)
    story.append(Spacer(1, 0.3*cm))

    # Heti terhelésdiagram
    try:
        story.append(P("Heti terhelésdiagram", h2_style))
        story.append(_make_weekly_bar_drawing(day_summary, width=500, height=175))
        story.append(Spacer(1, 0.25*cm))
    except Exception as exc:
        story.append(P(f"A heti diagram nem volt elkészíthető: {exc}", small_style))

    def add_cards(title, df, max_rows=6, accent="#1E3A8A"):
        story.append(P(title, h2_style))
        if df is None or df.empty:
            story.append(P("Nincs elég adat ehhez a blokkhoz.", small_style))
            story.append(Spacer(1, 0.1*cm))
            return
        for _, row in df.head(max_rows).iterrows():
            vals = []
            for col in df.columns:
                val = row.get(col, "")
                if pd.notna(val) and str(val).strip() and str(val) != "nan":
                    vals.append(f"<b>{safe_text(col)}:</b> {safe_text(val)}")
            if not vals:
                continue
            card = Table([[P("<br/>".join(vals), small_style)]], colWidths=[16.7*cm])
            card.setStyle(TableStyle([
                ("BACKGROUND", (0,0), (-1,-1), colors.HexColor("#F8FAFC")),
                ("BOX", (0,0), (-1,-1), 0.6, colors.HexColor("#CBD5E1")),
                ("LINEBEFORE", (0,0), (0,-1), 4, colors.HexColor(accent)),
                ("VALIGN", (0,0), (-1,-1), "TOP"),
                ("LEFTPADDING", (0,0), (-1,-1), 8),
                ("RIGHTPADDING", (0,0), (-1,-1), 8),
                ("TOPPADDING", (0,0), (-1,-1), 6),
                ("BOTTOMPADDING", (0,0), (-1,-1), 6),
            ]))
            story.append(card)
            story.append(Spacer(1, 0.12*cm))

    # Alap insightok
    add_cards("Szülőbarát insightok", insights_df, max_rows=6, accent="#2563EB")

    # Mélyebb következtetések
    try:
        deeper_df = pd.DataFrame(build_deeper_conclusions(day_summary, profile, events_df, checkins_df))
        add_cards("Részletesebb heti következtetések", deeper_df, max_rows=6, accent="#7C3AED")
    except Exception as exc:
        story.append(P(f"Részletesebb következtetések nem készültek el: {exc}", small_style))

    # Insight engine
    try:
        pack = build_neurodiverz_insight_engine(day_summary, profile, events_df, checkins_df)
        add_cards("Heti összkép", pack.get("heti_osszkep", pd.DataFrame()), max_rows=4, accent="#0F766E")
        add_cards("Több nap fókuszban", pack.get("napi_fokusz", pd.DataFrame()), max_rows=5, accent="#F97316")
        add_cards("Mintázatok és összefüggések", pack.get("mintazatok", pd.DataFrame()), max_rows=6, accent="#DC2626")
        add_cards("Pozitív jelek / ami működni látszik", pack.get("pozitiv_jelek", pd.DataFrame()), max_rows=5, accent="#16A34A")
        add_cards("Konkrét mikro-javaslatok", pack.get("mikro_javaslatok", pd.DataFrame()), max_rows=6, accent="#0891B2")
    except Exception as exc:
        story.append(P(f"Insight engine blokk nem készült el: {exc}", small_style))

    # Prognózis
    try:
        prognosis_df = build_prognosis_engine(day_summary, profile, events_df, checkins_df)
        add_cards("Prognózis / mire figyeljetek előre?", prognosis_df, max_rows=6, accent="#B45309")
    except Exception as exc:
        story.append(P(f"Prognózis nem készült el: {exc}", small_style))

    # Kihívást jelentő helyzetek
    try:
        challenge_df = build_challenge_pattern_table(checkins_df)
        add_cards("Kihívást jelentő helyzetek mintázata", challenge_df, max_rows=6, accent="#BE123C")
    except Exception as exc:
        story.append(P(f"Kihívást jelentő helyzetek blokk nem készült el: {exc}", small_style))

    # Jutalmazás
    try:
        points = calculate_reward_points(checkins_df)
        reward_df = pd.DataFrame([{
            "Matricák": f"{points}/7",
            "Szint": reward_level(points),
            "Üzenet": "A jutalom nem a tökéletes viselkedésért jár, hanem azért, mert együtt figyeltétek a hetet."
        }])
        add_cards("Jutalmazás / matricagyűjtés", reward_df, max_rows=1, accent="#EAB308")
    except Exception:
        pass

    story.append(Spacer(1, 0.15*cm))
    note = Table([[P("Fontos: ez az eszköz nem diagnosztikai vagy egészségügyi rendszer. Célja a családi terhelés, rutin, átállások, alvás/étkezés/képernyő és recovery tudatosabb tervezése.", small_style)]], colWidths=[16.7*cm])
    note.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), colors.HexColor("#FFF7ED")),
        ("BOX", (0,0), (-1,-1), 0.4, colors.HexColor("#FDBA74")),
        ("LEFTPADDING", (0,0), (-1,-1), 7),
        ("RIGHTPADDING", (0,0), (-1,-1), 7),
        ("TOPPADDING", (0,0), (-1,-1), 6),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
    ]))
    story.append(note)

    doc.build(story)
    return output.getvalue()


with tab_export:
    st.subheader("Exportok")

    st.info("Itt letölthető a heti riport PDF formában.")

    # Fontos: az export saját maga tölti be az adatokat, nem támaszkodik más fülek változóira.
    export_events_df = load_events(sb, selected_child_id, week_label)
    export_checkins_df = load_checkins(sb, selected_child_id, week_label)

    try:
        export_day_summary = build_day_summary(export_events_df, export_checkins_df)
    except Exception:
        export_day_summary = pd.DataFrame()

    try:
        export_insights_df = pd.DataFrame(
            generate_insights(
                export_day_summary,
                profile,
                export_events_df,
                export_checkins_df
            )
        )
    except Exception:
        export_insights_df = pd.DataFrame()

    st.markdown("### Export előnézet")
    if export_day_summary.empty:
        st.info("Nincs még elég adat a heti riporthoz.")
    else:
        st.dataframe(export_day_summary, use_container_width=True, hide_index=True)

    if st.button("PDF riport elkészítése", use_container_width=True):

        try:
            pdf_bytes = build_safe_pdf_report(
                profile=profile,
                events_df=export_events_df,
                day_summary=export_day_summary,
                insights_df=export_insights_df,
                checkins_df=export_checkins_df,
                week_label=week_label
            )

            if pdf_bytes is not None:

                st.download_button(
                    "⬇️ PDF riport letöltése",
                    data=pdf_bytes,
                    file_name=f"neurodiverz_heti_riport_{week_label}.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )

            else:
                st.error("A PDF export nem sikerült.")

        except Exception as exc:
            st.error(f"PDF export hiba: {exc}")

