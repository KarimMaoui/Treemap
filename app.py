import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.express as px
import time
import requests
from io import StringIO

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="S&P 500 Value Screener", layout="wide")

st.title("🏆 S&P 500 : Analyse de Valeur Historique (Sur-Mesure)")
st.markdown("""
Ce scanner isole les **plus grosses entreprises américaines** (selon votre choix) et compare leur prix actuel à leur **moyenne historique sur 5 ans**.
* **Bleu/Vert** = Sous-évalué (Opportunité ?)
* **Gris/Jaune** = Prix normal
* **Rouge/Violet** = Surévalué (Risque ?)
""")

# --- 2. RÉCUPÉRATION ET FILTRAGE DYNAMIQUE ---

@st.cache_data(ttl=3600*24)
def get_top_sp500_tickers(limit):
    """
    1. Récupère les 500 tickers du S&P.
    2. Trie par Market Cap.
    3. Garde uniquement les 'limit' premiers (ex: Top 50, Top 200...).
    """
    headers = {"User-Agent": "Mozilla/5.0"}
    status = st.empty()
    status.text("⏳ Récupération de la liste S&P 500...")
    
    try:
        # 1. Liste complète via Wikipedia
        url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
        r = requests.get(url, headers=headers)
        table = pd.read_html(StringIO(r.text))[0]
        tickers = table['Symbol'].tolist()
        tickers = [t.replace('.', '-') for t in tickers] # Correction BRK.B
        
        # 2. Tri par Market Cap (Utilisation de fast_info pour la vitesse)
        status.text(f"⚡ Tri des {limit} plus grosses capitalisations parmi {len(tickers)} actions...")
        
        market_caps = {}
        
        # On procède par petits paquets pour ne pas bloquer
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
        
        # Tri décroissant et coupe selon la limite choisie par l'utilisateur
        sorted_tickers = sorted(market_caps, key=market_caps.get, reverse=True)[:limit]
        
        status.empty()
        return sorted_tickers

    except Exception as e:
        st.error(f"Erreur récupération S&P : {e}")
        return ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL"] # Fallback

# --- 3. ANALYSE PROFONDE (HISTORIQUE P/E) ---

@st.cache_data(ttl=3600*12)
def get_historical_valuation(ticker):
    """Calcule la valorisation relative (Fwd P/E vs Moyenne Hist 5 ans)."""
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        
        # Filtres de base
        sector = info.get('sector', 'Unknown')
        fwd_pe = info.get('forwardPE', None)
        
        if fwd_pe is None: return None

        # Récupération des données comptables pour l'historique
        financials = stock.financials
        if financials.empty: return None
            
        # Recherche EPS
        eps_data = financials.T 
        eps_cols = [c for c in eps_data.columns if 'EPS' in str(c) or 'Earnings' in str(c)]
        if not eps_cols: return None
        
        eps_series = eps_data[eps_cols[0]].sort_index()
        
        # Historique Prix
        start_date = eps_series.index.min().strftime('%Y-%m-%d')
        history = stock.history(start=start_date)
        
        # Calcul P/E Historique
        pe_ratios = []
        for date, eps in eps_series.items():
            year = date.year
            mask = history.index.year == year
            if not mask.any(): continue
            avg_price = history.loc[mask, 'Close'].mean()
            if avg_price and eps > 0:
                pe_ratios.append(avg_price / eps)
        
        if not pe_ratios: return None
            
        avg_historical_pe = sum(pe_ratios) / len(pe_ratios)

        # Calcul Premium/Discount
        valuation_diff = (fwd_pe - avg_historical_pe) / avg_historical_pe
        
        return {
            "Ticker": ticker,
            "Name": info.get('shortName', ticker),
            "Sector": sector,
            "Market Cap": info.get('marketCap', 0),
            "Forward P/E": fwd_pe,
            "Avg Hist P/E": avg_historical_pe,
            "Premium/Discount": valuation_diff * 100
        }

    except Exception:
        return None

def run_analysis(tickers_list):
    data = []
    progress_bar = st.progress(0)
    status_text = st.empty()
    total = len(tickers_list)
    
    for i, ticker in enumerate(tickers_list):
        status_text.text(f"Analyse approfondie : {ticker} ({i+1}/{total})")
        res = get_historical_valuation(ticker)
        if res:
            data.append(res)
        
        time.sleep(0.05) 
        progress_bar.progress((i + 1) / total)
    
    progress_bar.empty()
    status_text.empty()
    return pd.DataFrame(data)

# --- 4. INTERFACE ---

# Zone de paramétrage
col_config1, col_config2 = st.columns([1, 2])

with col_config1:
    # LE SLIDER MAGIQUE EST ICI
    nb_stocks = st.slider("Nombre d'actions à analyser (Top Market Cap)", min_value=10, max_value=500, value=150, step=10)
    st.caption(f"Le scan analysera les {nb_stocks} plus grosses entreprises du S&P 500.")

with col_config2:
    st.write(" ") # Espace pour aligner
    st.write(" ")
    start_button = st.button(f'🚀 Lancer l\'analyse sur le TOP {nb_stocks}', type="primary")

if start_button:
    
    # 1. On récupère le nombre exact demandé
    top_tickers = get_top_sp500_tickers(limit=nb_stocks)
    st.success(f"Cible verrouillée : Les {len(top_tickers)} plus grosses capitalisations.")
    
    # 2. On lance l'analyse
    df = run_analysis(top_tickers)
    
    if not df.empty:
        st.divider()
        
        col1, col2 = st.columns(2)
        col1.metric("Actions Analysées", len(df))
        med = df['Premium/Discount'].median()
        col2.metric("Niveau Médian du Marché", f"{med:+.1f}%", 
                    delta="Sous-évalué" if med < 0 else "Surévalué", delta_color="inverse")

        # --- TREEMAP CONFIGURATION ---
        
        custom_scale = [
            "#00008B", "#0000FF", "#00BFFF", "#2E8B57", "#32CD32", 
            "#FFFF00", "#FFD700", "#FF8C00", "#FF0000", "#800080"
        ]

        st.subheader(f"🗺️ Carte Thermique : Top {nb_stocks} S&P 500")
        
        fig = px.treemap(
            df,
            path=[px.Constant(f"S&P 500 (Top {nb_stocks})"), 'Sector', 'Ticker'],
            values='Market Cap',
            color='Premium/Discount',
            color_continuous_scale=custom_scale,
            range_color=[-80, 80],
            hover_data={
                'Premium/Discount': ':.1f%',
                'Forward P/E': ':.1f',
                'Avg Hist P/E': ':.1f',
                'Market Cap': False,
                'Sector': False,
                'Ticker': False
            }
        )
        
        fig.update_traces(
            textinfo="label+text",
            hovertemplate="<b>%{label}</b><br>Diff Moyenne: %{color:.1f}%<br>Fwd P/E: %{customdata[1]}<extra></extra>"
        )
        
        fig.update_layout(height=800, margin=dict(t=30, l=10, r=10, b=10))
        st.plotly_chart(fig, use_container_width=True)
        
        # Tableau
        st.subheader("Données Détaillées")
        
        def color_val(val):
            if val < -20: return 'color: blue; font-weight: bold'
            if val < 0: return 'color: green'
            if val > 40: return 'color: red; font-weight: bold'
            if val > 0: return 'color: orange'
            return 'color: black'

        st.dataframe(
            df.sort_values("Premium/Discount").style
            .format({
                "Market Cap": "${:,.0f}",
                "Forward P/E": "{:.1f}",
                "Avg Hist P/E": "{:.1f}",
                "Premium/Discount": "{:+.1f}%"
            })
            .map(color_val, subset=['Premium/Discount']),
            use_container_width=True
        )

    else:
        st.error("Aucune donnée disponible.")
