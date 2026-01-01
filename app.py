import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.express as px
import time
import requests
from io import StringIO

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="US Market Screener", layout="wide")

st.title("🇺🇸 US Market Screener : Analyse de Valeur Historique")
st.markdown("""
Comparez la valorisation actuelle des géants américains à leur **moyenne historique sur 5 ans**.
* **Bleu/Vert** = Sous-évalué (Opportunité ?)
* **Gris/Jaune** = Prix normal
* **Rouge/Violet** = Surévalué (Risque ?)
""")

# --- 2. RÉCUPÉRATION ET FILTRAGE DYNAMIQUE ---

@st.cache_data(ttl=3600*24)
def get_top_tickers(index_name, limit):
    """
    Récupère les tickers de l'indice choisi, les trie par Market Cap, 
    et ne garde que le Top 'limit'.
    """
    headers = {"User-Agent": "Mozilla/5.0"}
    status = st.empty()
    status.text(f"⏳ Récupération de la liste {index_name}...")
    
    tickers = []
    
    try:
        # A. Choix de la source selon l'indice
        if index_name == "S&P 500":
            url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
            r = requests.get(url, headers=headers)
            table = pd.read_html(StringIO(r.text))[0]
            tickers = table['Symbol'].tolist()
            # Correction spécifique S&P (BRK.B -> BRK-B)
            tickers = [t.replace('.', '-') for t in tickers]
            
        elif index_name == "Nasdaq 100":
            url = "https://en.wikipedia.org/wiki/Nasdaq-100"
            r = requests.get(url, headers=headers)
            # Sur la page Nasdaq, c'est souvent la table des composants
            tables = pd.read_html(StringIO(r.text))
            for t in tables:
                if 'Ticker' in t.columns:
                    tickers = t['Ticker'].tolist()
                    break
                if 'Symbol' in t.columns:
                    tickers = t['Symbol'].tolist()
                    break

        # B. Tri par Market Cap (via fast_info)
        status.text(f"⚡ Tri des {limit} plus grosses entreprises du {index_name}...")
        
        market_caps = {}
        
        # Batching pour éviter le spam
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
        
        # Tri décroissant et coupe
        sorted_tickers = sorted(market_caps, key=market_caps.get, reverse=True)[:limit]
        
        status.empty()
        return sorted_tickers

    except Exception as e:
        st.error(f"Erreur récupération {index_name} : {e}")
        return ["AAPL", "MSFT", "NVDA"] # Fallback

# --- 3. ANALYSE PROFONDE (HISTORIQUE P/E) ---

@st.cache_data(ttl=3600*12)
def get_historical_valuation(ticker):
    """Calcule la valorisation relative (Fwd P/E vs Moyenne Hist 5 ans)."""
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        
        # Filtres
        sector = info.get('sector', 'Unknown')
        fwd_pe = info.get('forwardPE', None)
        
        if fwd_pe is None: return None

        # Historique Financier
        financials = stock.financials
        if financials.empty: return None
            
        eps_data = financials.T 
        eps_cols = [c for c in eps_data.columns if 'EPS' in str(c) or 'Earnings' in str(c)]
        if not eps_cols: return None
        
        eps_series = eps_data[eps_cols[0]].sort_index()
        
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
            
        avg_historical_pe = sum(pe_ratios) / len(pe_ratios)

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

col1, col2, col3 = st.columns([1, 1, 1])

with col1:
    # CHOIX DE L'INDICE
    selected_index = st.selectbox("1. Choisir l'Indice", ["S&P 500", "Nasdaq 100"])

with col2:
    # SLIDER ADAPTATIF
    # On définit le max selon l'indice choisi
    max_slider = 100 if selected_index == "Nasdaq 100" else 500
    # On définit une valeur par défaut cohérente (ex: 50)
    nb_stocks = st.slider(f"2. Nombre d'actions (Max {max_slider})", 
                          min_value=10, max_value=max_slider, value=50, step=10)

with col3:
    st.write(" ") # Espace blanc pour aligner verticalement le bouton
    st.write(" ")
    start_btn = st.button("🚀 Lancer l'Analyse", type="primary", use_container_width=True)

if start_btn:
    
    # 1. Récupération liste
    top_tickers = get_top_tickers(selected_index, nb_stocks)
    st.success(f"Cible : Top {len(top_tickers)} du {selected_index}.")
    
    # 2. Analyse
    df = run_analysis(top_tickers)
    
    if not df.empty:
        st.divider()
        
        # Stats Rapides
        c1, c2 = st.columns(2)
        c1.metric("Actions Analysées", len(df))
        med = df['Premium/Discount'].median()
        c2.metric("Valorisation Médiane", f"{med:+.1f}%", 
                  delta="Bon marché" if med < 0 else "Cher", delta_color="inverse")

        # --- TREEMAP ---
        custom_scale = [
            "#00008B", "#0000FF", "#00BFFF", "#2E8B57", "#32CD32", 
            "#FFFF00", "#FFD700", "#FF8C00", "#FF0000", "#800080"
        ]

        st.subheader(f"🗺️ Carte Thermique : {selected_index} (Top {nb_stocks})")
        
        fig = px.treemap(
            df,
            path=[px.Constant(selected_index), 'Sector', 'Ticker'],
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
        
        fig.update_layout(height=750, margin=dict(t=30, l=10, r=10, b=10))
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
        st.error("Aucune donnée trouvée.")
