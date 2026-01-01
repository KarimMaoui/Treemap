import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.express as px
import time
import requests
from io import StringIO

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="Ultimate Market Screener", layout="wide")

st.title("🌍 Ultimate Global Screener")
st.markdown("""
**Scan de Valorisation Mondiale (P/E vs Moyenne Hist. 5 ans)**
* 🇺🇸 **US** (S&P 500, Nasdaq)
* 🇪🇺 **Europe** (CAC 40, DAX, FTSE 100, SMI)
* 🇨🇦 **Canada** (TSX 60)
* 🇯🇵 **Japon** (Nikkei 225)
""")

# --- 2. RÉCUPÉRATION ET FILTRAGE DYNAMIQUE ---

@st.cache_data(ttl=3600*24)
def get_top_tickers(index_name, limit):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
    status = st.empty()
    status.text(f"⏳ Récupération de la liste {index_name}...")
    
    tickers = []
    
    try:
        # --- AMÉRIQUE DU NORD ---
        if index_name == "S&P 500 (USA)":
            url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
            r = requests.get(url, headers=headers)
            table = pd.read_html(StringIO(r.text))[0]
            tickers = [t.replace('.', '-') for t in table['Symbol'].tolist()]

        elif index_name == "Nasdaq 100 (USA)":
            url = "https://en.wikipedia.org/wiki/Nasdaq-100"
            r = requests.get(url, headers=headers)
            tables = pd.read_html(StringIO(r.text))
            for t in tables:
                if 'Ticker' in t.columns:
                    tickers = t['Ticker'].tolist()
                    break

        elif index_name == "TSX 60 (Canada)":
            url = "https://en.wikipedia.org/wiki/S%26P/TSX_60"
            r = requests.get(url, headers=headers)
            table = pd.read_html(StringIO(r.text))[0]
            # Wiki donne souvent 'RY', Yahoo veut 'RY.TO'
            raw_tickers = table['Symbol'].tolist()
            tickers = [f"{t}.TO" if not str(t).endswith('.TO') else t for t in raw_tickers]

        # --- EUROPE ---
        elif index_name == "CAC 40 (France)":
            url = "https://en.wikipedia.org/wiki/CAC_40"
            r = requests.get(url, headers=headers)
            tables = pd.read_html(StringIO(r.text))
            for t in tables:
                if 'Ticker' in t.columns:
                    raw = t['Ticker'].tolist()
                    tickers = [f"{x}.PA" if not str(x).endswith('.PA') else x for x in raw]
                    break
        
        elif index_name == "DAX 40 (Allemagne)":
            url = "https://en.wikipedia.org/wiki/DAX"
            r = requests.get(url, headers=headers)
            tables = pd.read_html(StringIO(r.text))
            for t in tables:
                if 'Ticker' in t.columns:
                    raw = t['Ticker'].tolist()
                    tickers = [f"{x}.DE" if not str(x).endswith('.DE') else x for x in raw]
                    break
                    
        elif index_name == "FTSE 100 (Royaume-Uni)":
            url = "https://en.wikipedia.org/wiki/FTSE_100_Index"
            r = requests.get(url, headers=headers)
            table = pd.read_html(StringIO(r.text))[4] # Souvent la table 4 ou chercher 'Ticker'
            # Fallback recherche table
            if 'Ticker' not in table.columns:
                 tables = pd.read_html(StringIO(r.text))
                 for t in tables:
                     if 'Ticker' in t.columns:
                         table = t
                         break
            raw = table['Ticker'].tolist()
            # Yahoo suffixe .L pour Londres
            tickers = [f"{x}.L" if not str(x).endswith('.L') else x for x in raw]

        elif index_name == "SMI 20 (Suisse)":
            url = "https://en.wikipedia.org/wiki/Swiss_Market_Index"
            r = requests.get(url, headers=headers)
            tables = pd.read_html(StringIO(r.text))
            for t in tables:
                if 'Ticker' in t.columns:
                    raw = t['Ticker'].tolist()
                    # Yahoo suffixe .SW pour Swiss Exchange
                    tickers = [f"{x}.SW" for x in raw] 
                    break

        # --- ASIE ---
        elif index_name == "Nikkei 225 (Japon)":
            url = "https://en.wikipedia.org/wiki/Nikkei_225"
            r = requests.get(url, headers=headers)
            tables = pd.read_html(StringIO(r.text))
            # Table souvent complexe, on cherche celle avec "Symbol" ou "Code"
            raw = []
            for t in tables:
                if 'Symbol' in t.columns:
                    raw = t['Symbol'].tolist()
                    break
            # Yahoo veut '7203.T' pour Tokyo
            tickers = [f"{x}.T" for x in raw]

        # --- TRI & BATCHING ---
        if not tickers: return []
        status.text(f"⚡ Tri des {limit} plus grosses entreprises ({index_name})...")
        
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

    except Exception as e:
        st.error(f"Erreur : {e}")
        return []

# --- 3. ANALYSE PROFONDE ---

@st.cache_data(ttl=3600*12)
def get_historical_valuation(ticker):
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        
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
    # Réglage auto du slider selon la taille de l'indice
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
            # NETTOYAGE VISUEL (On retire tous les suffixes possibles)
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
            # Gestion Devise
            cur = "$"
            if "France" in idx or "Allemagne" in idx: cur = "€"
            elif "Royaume" in idx: cur = "£"
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
    else: st.error("Erreur de liste.")
