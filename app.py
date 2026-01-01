import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.express as px
import time
import requests
from io import StringIO

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="Global Screener V17.3", layout="wide")

st.title("🌍 Ultimate Global Screener (V17.3 - PEG Débloqué)")
st.markdown("""
**Analyse 360° : Valorisation + Croissance + Santé Financière**
* **Onglet 1** : Historique (Value).
* **Onglet 2** : Croissance (Growth).
* **Tableau** : PEG Ratio (Inclus les croissances négatives).
""")

# --- 2. FONCTIONS DE SCRAPING ---

def get_tickers_from_wikipedia(url, index_suffix=""):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        tables = pd.read_html(StringIO(r.text))
        
        found_tickers = []
        possible_cols = ['Symbol', 'Ticker', 'Code', 'Security Symbol', 'Stock symbol', 'Securities Code']
        
        for df in tables:
            col_match = None
            for col in df.columns:
                if str(col).strip() in possible_cols:
                    col_match = col
                    break
            
            if col_match:
                raw_list = df[col_match].tolist()
                for t in raw_list:
                    t = str(t).strip()
                    if t.lower() == "nan" or t == "": continue
                    
                    if index_suffix == ".TO":
                        if ".TO" in t: found_tickers.append(t)
                        else: found_tickers.append(t)
                    else:
                        if index_suffix and not t.endswith(index_suffix):
                            t = f"{t}{index_suffix}"
                        found_tickers.append(t)
                
                if len(found_tickers) > 10:
                    return found_tickers
        return found_tickers
    except Exception:
        return []

@st.cache_data(ttl=3600*24)
def get_top_tickers(index_name, limit):
    status = st.empty()
    status.text(f"⏳ Récupération liste : {index_name}...")
    tickers = []
    
    if index_name == "S&P 500 (USA)":
        tickers = get_tickers_from_wikipedia("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", "")
        tickers = [t.replace('.', '-') for t in tickers]
    elif index_name == "Nasdaq 100 (USA)":
        tickers = get_tickers_from_wikipedia("https://en.wikipedia.org/wiki/Nasdaq-100", "")
    elif index_name == "TSX 60 (Canada)":
        raw = get_tickers_from_wikipedia("https://en.wikipedia.org/wiki/S%26P/TSX_60", ".TO")
        tickers = []
        for t in raw:
            if "nan" in t.lower(): continue
            root = t.replace(".TO", "").replace(".", "-")
            tickers.append(f"{root}.TO")
    elif index_name == "CAC 40 (France)":
        tickers = get_tickers_from_wikipedia("https://en.wikipedia.org/wiki/CAC_40", ".PA")
    elif index_name == "DAX 40 (Allemagne)":
        tickers = get_tickers_from_wikipedia("https://en.wikipedia.org/wiki/DAX", ".DE")
    elif index_name == "FTSE 100 (UK)":
        tickers = get_tickers_from_wikipedia("https://en.wikipedia.org/wiki/FTSE_100_Index", ".L")
    elif index_name == "SMI 20 (Suisse)":
        tickers = get_tickers_from_wikipedia("https://en.wikipedia.org/wiki/Swiss_Market_Index", ".SW")
    elif index_name == "Nifty 50 (Inde)":
        tickers = get_tickers_from_wikipedia("https://en.wikipedia.org/wiki/Nifty_50", ".NS")

    if not tickers: return []

    status.text(f"⚡ Tri des {limit} plus grosses entreprises...")
    market_caps = {}
    safe_limit = min(limit, len(tickers))
    batch_size = 50
    
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i:i+batch_size]
        for t in batch:
            try:
                info = yf.Ticker(t).fast_info
                mcap = info['market_cap']
                if mcap: market_caps[t] = mcap
            except: continue
    
    sorted_tickers = sorted(market_caps, key=market_caps.get, reverse=True)[:safe_limit]
    status.empty()
    return sorted_tickers

# --- 3. ANALYSE PROFONDE ---

@st.cache_data(ttl=3600*12)
def get_historical_valuation(ticker):
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        currency = info.get('currency', 'USD')
        fwd_pe = info.get('forwardPE', info.get('trailingPE', None))
        
        # --- INDICATEURS ---
        growth = info.get('earningsGrowth', None)
        peg = info.get('pegRatio', None)
        debt_eq = info.get('debtToEquity', None)
        margins = info.get('profitMargins', None)
        
        if fwd_pe is None: return None
        
        # --- CORRECTION V17.3 : CALCUL PEG MÊME SI CROISSANCE NÉGATIVE ---
        # On vérifie juste que growth n'est pas zéro (division par zéro impossible)
        if peg is None and fwd_pe is not None and growth is not None and growth != 0:
            peg = fwd_pe / (growth * 100)

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
            if currency == 'GBp': avg_price = avg_price / 100.0
            if avg_price and eps > 0: pe_ratios.append(avg_price / eps)
        
        if not pe_ratios: return None
        avg_hist_pe = sum(pe_ratios) / len(pe_ratios)
        if avg_hist_pe == 0: return None
        
        valuation_diff = (fwd_pe - avg_hist_pe) / avg_hist_pe
        
        growth_percent = growth * 100 if growth is not None else None
        margins_percent = margins * 100 if margins is not None else None

        return {
            "Ticker": ticker,
            "Name": info.get('shortName', ticker),
            "Sector": info.get('sector', 'Unknown'),
            "Market Cap": info.get('marketCap', 0),
            "Forward P/E": fwd_pe,
            "Avg Hist P/E": avg_hist_pe,
            "Growth %": growth_percent,
            "PEG": peg,
            "Debt/Eq": debt_eq,
            "Margins %": margins_percent,
            "Premium/Discount": valuation_diff * 100
        }
    except: return None

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
    idx = st.selectbox("1. Indice", ["S&P 500 (USA)", "Nasdaq 100 (USA)", "CAC 40 (France)", "DAX 40 (Allemagne)", "FTSE 100 (UK)", "SMI 20 (Suisse)", "TSX 60 (Canada)", "Nifty 50 (Inde)"])
with c2:
    if "SMI" in idx: max_v = 20
    elif "CAC" in idx or "DAX" in idx: max_v = 40
    elif "TSX" in idx or "Nifty" in idx: max_v = 50
    elif "Nasdaq" in idx or "FTSE" in idx: max_v = 100
    else: max_v = 500
    nb = st.slider(f"2. Max Actions ({max_v})", 5, max_v, min(50, max_v), 5)
with c3:
    st.write(" ")
    st.write(" ")
    btn = st.button("🚀 Lancer l'Analyse", type="primary", use_container_width=True)

# --- 5. LOGIQUE ---

if btn:
    top = get_top_tickers(idx, nb)
    if top:
        st.success(f"Cible : {len(top)} entreprises.")
        df_result = run_analysis(top)
        
        if not df_result.empty:
            for suffix in ['.PA', '.DE', '.L', '.TO', '.SW', '.NS']:
                df_result['Ticker'] = df_result['Ticker'].astype(str).str.replace(suffix, '', regex=False)
            
            st.session_state['data'] = df_result
            st.session_state['index_name'] = idx
        else:
            st.warning("Données incomplètes.")
    else:
        st.error("Erreur liste.")

# --- 6. AFFICHAGE ---

if 'data' in st.session_state:
    df = st.session_state['data']
    current_idx = st.session_state['index_name']
    
    st.divider()
    
    tab1, tab2 = st.tabs(["🗺️ Treemap (Value)", "🚀 Growth vs P/E (GARP)"])
    
    scale = ["#00008B", "#0000FF", "#00BFFF", "#2E8B57", "#32CD32", "#FFFF00", "#FFD700", "#FF8C00", "#FF0000", "#800080"]
    
    with tab1:
        st.subheader(f"Carte Thermique : {current_idx}")
        fig_tree = px.treemap(
            df, path=[px.Constant(current_idx), 'Sector', 'Ticker'], values='Market Cap', color='Premium/Discount',
            color_continuous_scale=scale, range_color=[-80, 80],
            hover_data={'Premium/Discount':':.1f%', 'Forward P/E':':.1f', 'Avg Hist P/E':':.1f', 'PEG':':.2f', 'Market Cap':False, 'Sector':False, 'Ticker':False}
        )
        fig_tree.update_traces(textinfo="label+text", hovertemplate="<b>%{label}</b><br>Diff: %{color:.1f}%<br>Fwd P/E: %{customdata[1]}<extra></extra>")
        fig_tree.update_layout(height=700, margin=dict(t=20, l=10, r=10, b=10))
        st.plotly_chart(fig_tree, use_container_width=True)

    with tab2:
        col_sel1, col_sel2 = st.columns([1, 3])
        all_sectors = sorted(df['Sector'].unique().tolist())
        selected_sector = col_sel1.selectbox("🔎 Filtrer par Secteur", ["Tous"] + all_sectors)
        
        if selected_sector != "Tous":
            df_show = df[df['Sector'] == selected_sector]
        else:
            df_show = df

        df_chart = df_show.dropna(subset=['Growth %', 'Forward P/E'])
        df_chart = df_chart[(df_chart['Growth %'] > -50) & (df_chart['Growth %'] < 100)]
        df_chart = df_chart[df_chart['Forward P/E'] < 100]

        if not df_chart.empty:
            fig_scatter = px.scatter(
                df_chart, x="Growth %", y="Forward P/E", size="Market Cap", 
                color="Premium/Discount", color_continuous_scale=scale, range_color=[-80, 80],
                text="Ticker", hover_name="Name", trendline="ols", trendline_color_override="red",
                title=f"P/E vs Croissance : {selected_sector}"
            )
            fig_scatter.update_traces(textposition='top center')
            fig_scatter.update_layout(height=650, xaxis_title="Croissance Estimée (%)", yaxis_title="Forward P/E")
            st.plotly_chart(fig_scatter, use_container_width=True)
        else:
            st.warning("Pas assez de données de croissance.")

    st.divider()
    st.subheader("Données Détaillées & Indicateurs de Risque")
    st.caption("• **PEG** < 1 : Bon marché | **Négatif** : Croissance en baisse (Danger) | • **Debt/Eq** > 200 : Endetté")
    
    cur = "$"
    if "France" in current_idx or "Allemagne" in current_idx: cur = "€"
    elif "UK" in current_idx: cur = "£"
    elif "Suisse" in current_idx: cur = "CHF "
    elif "Canada" in current_idx: cur = "C$ "
    elif "Inde" in current_idx: cur = "₹ "

    # Fonction couleurs
    def color_premium(v):
        if pd.isna(v): return ''
        if v < -20: return 'color: blue; font-weight: bold'
        if v < 0: return 'color: green'
        if v > 40: return 'color: red; font-weight: bold'
        if v > 0: return 'color: orange'
        return 'color: black'
    
    def color_peg(v):
        if pd.isna(v): return ''
        if v < 0: return 'color: darkred; font-weight: bold' # Croissance Négative
        if v < 1: return 'color: green; font-weight: bold'
        if v > 2.5: return 'color: red'
        return ''

    def color_debt(v):
        if pd.isna(v): return ''
        if v > 200: return 'color: red; font-weight: bold'
        if v < 50: return 'color: green'
        return ''

    st.dataframe(
        df.sort_values("Premium/Discount").style
        .format({
            "Market Cap": lambda x: (cur + "{:,.0f}").format(x) if pd.notnull(x) else "-", 
            "Forward P/E": lambda x: "{:.1f}".format(x) if pd.notnull(x) else "-", 
            "Avg Hist P/E": lambda x: "{:.1f}".format(x) if pd.notnull(x) else "-", 
            "Growth %": lambda x: "{:+.1f}%".format(x) if pd.notnull(x) else "-",
            "PEG": lambda x: "{:.2f}".format(x) if pd.notnull(x) else "-",
            "Debt/Eq": lambda x: "{:.0f}%".format(x) if pd.notnull(x) else "-",
            "Margins %": lambda x: "{:.1f}%".format(x) if pd.notnull(x) else "-",
            "Premium/Discount": lambda x: "{:+.1f}%".format(x) if pd.notnull(x) else "-"
        })
        .map(color_premium, subset=['Premium/Discount'])
        .map(color_peg, subset=['PEG'])
        .map(color_debt, subset=['Debt/Eq']),
        use_container_width=True
    )
