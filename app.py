import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.express as px
import time
import requests
from io import StringIO

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="Global Screener V6.1", layout="wide")

st.title("🌍 Ultimate Global Screener (Corrigé)")
st.markdown("""
**Scan de Valorisation Mondiale (P/E vs Moyenne Hist. 5 ans)**
* Correctifs appliqués : Scraping robuste (Canada/Japon/Suisse) & Conversion Pence/Livre (UK).
""")

# --- 2. FONCTION DE RÉCUPÉRATION ROBUSTE ---

def get_tickers_from_wikipedia(url, index_suffix=""):
    """
    Fonction intelligente qui cherche la colonne des tickers quel que soit son nom.
    """
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    try:
        r = requests.get(url, headers=headers)
        # On lit toutes les tables de la page
        tables = pd.read_html(StringIO(r.text))
        
        found_tickers = []
        
        # Mots-clés possibles pour la colonne ticker
        possible_cols = ['Symbol', 'Ticker', 'Code', 'Security Symbol', 'Stock symbol']
        
        for df in tables:
            # On cherche si une des colonnes correspond
            col_match = next((c for c in df.columns if c in possible_cols), None)
            
            if col_match:
                raw_list = df[col_match].tolist()
                # Nettoyage et ajout du suffixe
                for t in raw_list:
                    t = str(t).strip()
                    # Gestion spécifique S&P/TSX (parfois 'RY.TO', parfois 'RY')
                    if index_suffix == ".TO" and ".TO" in t:
                        found_tickers.append(t)
                    else:
                        # On évite le double suffixe
                        if index_suffix and not t.endswith(index_suffix):
                            t = f"{t}{index_suffix}"
                        elif index_suffix:
                             t = t # Le suffixe est déjà là
                        found_tickers.append(t)
                
                # Si on a trouvé une liste décente (>5 éléments), on arrête de chercher
                if len(found_tickers) > 5:
                    return found_tickers

        return found_tickers
    except Exception as e:
        st.error(f"Erreur scraping Wikipedia ({url}): {e}")
        return []

@st.cache_data(ttl=3600*24)
def get_top_tickers(index_name, limit):
    status = st.empty()
    status.text(f"⏳ Récupération de la liste {index_name}...")
    
    tickers = []
    
    # --- DÉFINITION DES URLS ET SUFFIXES ---
    if index_name == "S&P 500 (USA)":
        # Cas particulier S&P : table[0] et replace '.' par '-'
        tickers = get_tickers_from_wikipedia("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", "")
        tickers = [t.replace('.', '-') for t in tickers]
        
    elif index_name == "Nasdaq 100 (USA)":
        tickers = get_tickers_from_wikipedia("https://en.wikipedia.org/wiki/Nasdaq-100", "")
        
    elif index_name == "TSX 60 (Canada)":
        tickers = get_tickers_from_wikipedia("https://en.wikipedia.org/wiki/S%26P/TSX_60", ".TO")
        
    elif index_name == "CAC 40 (France)":
        tickers = get_tickers_from_wikipedia("https://en.wikipedia.org/wiki/CAC_40", ".PA")
        
    elif index_name == "DAX 40 (Allemagne)":
        tickers = get_tickers_from_wikipedia("https://en.wikipedia.org/wiki/DAX", ".DE")
        
    elif index_name == "FTSE 100 (Royaume-Uni)":
        tickers = get_tickers_from_wikipedia("https://en.wikipedia.org/wiki/FTSE_100_Index", ".L")
        
    elif index_name == "SMI 20 (Suisse)":
        tickers = get_tickers_from_wikipedia("https://en.wikipedia.org/wiki/Swiss_Market_Index", ".SW")
        
    elif index_name == "Nikkei 225 (Japon)":
        tickers = get_tickers_from_wikipedia("https://en.wikipedia.org/wiki/Nikkei_225", ".T")

    if not tickers:
        return []

    status.text(f"⚡ Tri des {limit} plus grosses entreprises ({index_name})...")
    
    # Tri par Market Cap (Batching)
    market_caps = {}
    safe_limit = min(limit, len(tickers))
    batch_size = 50
    
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i:i+batch_size]
        for t in batch:
            try:
                info = yf.Ticker(t).fast_info
                mcap = info['market_cap']
                if mcap:
                    market_caps[t] = mcap
            except:
                continue
    
    sorted_tickers = sorted(market_caps, key=market_caps.get, reverse=True)[:safe_limit]
    status.empty()
    return sorted_tickers

# --- 3. ANALYSE PROFONDE (AVEC CORRECTION DEVISE UK) ---

@st.cache_data(ttl=3600*12)
def get_historical_valuation(ticker):
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        
        # Récupération Devise
        currency = info.get('currency', 'USD')
        
        # Données de base
        fwd_pe = info.get('forwardPE', info.get('trailingPE', None))
        if fwd_pe is None: return None

        financials = stock.financials
        if financials.empty: return None
            
        eps_data = financials.T 
        eps_cols = [c for c in eps_data.columns if 'EPS' in str(c) or 'Earnings' in str(c)]
        if not eps_cols: return None
        
        eps_series = eps_data[eps_cols[0]].sort_index()
        if eps_series.empty: return None

        start_date = eps_series.index.min().strftime('%Y-%m-%d')
        history = stock.history(start=start_date)
        
        pe_ratios = []
        for date, eps in eps_series.items():
            year = date.year
            mask = history.index.year == year
            if not mask.any(): continue
            
            avg_price = history.loc[mask, 'Close'].mean()
            
            # --- CORRECTION CRITIQUE POUR LONDRES (GBp vs GBP) ---
            # Si la devise est en Pence (GBp), le prix est ex: 1000.
            # Mais l'EPS est en Livres (GBP), ex: 1.0.
            # Sans correction : P/E = 1000 / 1 = 1000 (Faux)
            # Avec correction : P/E = (1000 / 100) / 1 = 10 (Juste)
            if currency == 'GBp':
                avg_price = avg_price / 100.0
            
            if avg_price and eps > 0:
                pe_ratios.append(avg_price / eps)
        
        if not pe_ratios: return None
        avg_hist_pe = sum(pe_ratios) / len(pe_ratios)
        if avg_hist_pe == 0: return None
        
        valuation_diff = (fwd_pe - avg_hist_pe) / avg_hist_pe
        
        return {
            "Ticker": ticker,
            "Name": info.get('shortName', ticker),
            "Sector": info.get('sector', 'Unknown'),
            "Market Cap": info.get('marketCap', 0),
            "Forward P/E": fwd_pe,
            "Avg Hist P/E": avg_hist_pe,
            "Premium/Discount": valuation_diff * 100
        }
    except:
        return None

def run_analysis(tickers):
    data = []
    bar = st.progress(0)
    status = st.empty()
    total = len(tickers)
    for i, t in enumerate(tickers):
        status.text(f"Analyse : {t} ({i+1}/{total})")
        res = get_historical_valuation(t)
        if res: data.append(res)
        time.sleep(0.05)
        bar.progress((i+1)/total)
    bar.empty()
    status.empty()
    return pd.DataFrame(data)

# --- 4. INTERFACE ---

c1, c2, c3 = st.columns([1, 1, 1])

with c1:
    indices = [
        "S&P 500 (USA)", "Nasdaq 100 (USA)", 
        "CAC 40 (France)", "DAX 40 (Allemagne)", 
        "FTSE 100 (Royaume-Uni)", "SMI 20 (Suisse)",
        "TSX 60 (Canada)", "Nikkei 225 (Japon)"
    ]
    idx = st.selectbox("1. Choisir l'Indice", indices)

with c2:
    if "SMI" in idx: max_v = 20
    elif "CAC" in idx or "DAX" in idx: max_v = 40
    elif "TSX" in idx: max_v = 60
    elif "Nasdaq" in idx or "FTSE" in idx: max_v = 100
    elif "Nikkei" in idx: max_v = 225
    else: max_v = 500
    
    nb = st.slider(f"2. Nombre d'actions (Max {max_v})", 5, max_v, min(50, max_v), 5)

with c3:
    st.write(" ")
    st.write(" ")
    btn = st.button("🚀 Lancer l'Analyse", type="primary", use_container_width=True)

if btn:
    top = get_top_tickers(idx, nb)
    if top:
        st.success(f"Cible : {len(top)} entreprises.")
        df = run_analysis(top)
        
        if not df.empty:
            # NETTOYAGE VISUEL
            for suffix in ['.PA', '.DE', '.L', '.TO', '.SW', '.T']:
                df['Ticker'] = df['Ticker'].astype(str).str.replace(suffix, '', regex=False)
            
            st.divider()
            col_a, col_b = st.columns(2)
            col_a.metric("Actions", len(df))
            med = df['Premium/Discount'].median()
            col_b.metric("Valorisation Médiane", f"{med:+.1f}%", delta_color="inverse")
            
            # TREEMAP
            scale = ["#00008B", "#0000FF", "#00BFFF", "#2E8B57", "#32CD32", "#FFFF00", "#FFD700", "#FF8C00", "#FF0000", "#800080"]
            fig = px.treemap(
                df, path=[px.Constant(idx), 'Sector', 'Ticker'], values='Market Cap', color='Premium/Discount',
                color_continuous_scale=scale, range_color=[-80, 80],
                hover_data={'Premium/Discount':':.1f%', 'Forward P/E':':.1f', 'Avg Hist P/E':':.1f', 'Market Cap':False, 'Sector':False, 'Ticker':False}
            )
            fig.update_traces(textinfo="label+text", hovertemplate="<b>%{label}</b><br>Diff Moy: %{color:.1f}%<br>P/E: %{customdata[1]}<extra></extra>")
            fig.update_layout(height=750, margin=dict(t=30, l=10, r=10, b=10))
            st.plotly_chart(fig, use_container_width=True)
            
            # TABLEAU
            st.subheader("Données Détaillées")
            cur = "$"
            if "France" in idx or "Allemagne" in idx: cur = "€"
            elif "Royaume" in idx: cur = "£" # Note: On affiche £ car on a converti les prix en livres
            elif "Suisse" in idx: cur = "CHF "
            elif "Japon" in idx: cur = "¥"
            elif "Canada" in idx: cur = "C$ "

            def color(v):
                if v < -20: return 'color: blue; font-weight: bold'
                if v < 0: return 'color: green'
                if v > 40: return 'color: red; font-weight: bold'
                if v > 0: return 'color: orange'
                return 'color: black'

            st.dataframe(
                df.sort_values("Premium/Discount").style.format({
                    "Market Cap": cur + "{:,.0f}", "Forward P/E": "{:.1f}", "Avg Hist P/E": "{:.1f}", "Premium/Discount": "{:+.1f}%"
                }).map(color, subset=['Premium/Discount']),
                use_container_width=True
            )
        else: st.warning("Pas de données complètes trouvées.")
    else: st.error("Impossible de récupérer la liste des tickers (Structure Wikipedia non reconnue).")
