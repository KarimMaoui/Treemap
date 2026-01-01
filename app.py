import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.express as px
import time
import requests
from io import StringIO

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="Global Market Screener", layout="wide")

st.title("🌍 Global Market Screener : US & Europe")
st.markdown("""
Analysez la valorisation historique (P/E vs Moyenne 5 ans) sur les marchés US et Européens.
* **Bleu/Vert** = Sous-évalué (Opportunité ?)
* **Rouge/Violet** = Surévalué (Risque ?)
""")

# --- 2. RÉCUPÉRATION ET FILTRAGE DYNAMIQUE (CORRIGÉ) ---

@st.cache_data(ttl=3600*24)
def get_top_tickers(index_name, limit):
    """
    Récupère les tickers, gère INTELLIGEMMENT les suffixes (évite le .PA.PA),
    trie par Market Cap et renvoie le Top 'limit'.
    """
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
    status = st.empty()
    status.text(f"⏳ Récupération de la liste {index_name}...")
    
    tickers = []
    
    try:
        # --- ETATS-UNIS ---
        if index_name == "S&P 500":
            url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
            r = requests.get(url, headers=headers)
            # Table 0 is usually S&P 500 components
            table = pd.read_html(StringIO(r.text))[0]
            tickers = table['Symbol'].tolist()
            tickers = [t.replace('.', '-') for t in tickers] 
            
        elif index_name == "Nasdaq 100":
            url = "https://en.wikipedia.org/wiki/Nasdaq-100"
            r = requests.get(url, headers=headers)
            tables = pd.read_html(StringIO(r.text))
            for t in tables:
                if 'Ticker' in t.columns:
                    tickers = t['Ticker'].tolist()
                    break
                if 'Symbol' in t.columns:
                    tickers = t['Symbol'].tolist()
                    break

        # --- EUROPE (CORRECTION DOUBLE SUFFIXE) ---
        elif index_name == "CAC 40 (France)":
            url = "https://en.wikipedia.org/wiki/CAC_40"
            r = requests.get(url, headers=headers)
            tables = pd.read_html(StringIO(r.text))
            
            raw_tickers = []
            for t in tables:
                if 'Ticker' in t.columns:
                    raw_tickers = t['Ticker'].tolist()
                    break
            
            # Correction : On n'ajoute .PA que s'il n'est pas déjà là
            tickers = []
            for t in raw_tickers:
                t = str(t).strip()
                if t.endswith('.PA'):
                    tickers.append(t)
                else:
                    tickers.append(f"{t}.PA")
        
        elif index_name == "DAX 40 (Allemagne)":
            url = "https://en.wikipedia.org/wiki/DAX"
            r = requests.get(url, headers=headers)
            tables = pd.read_html(StringIO(r.text))
            
            raw_tickers = []
            for t in tables:
                if 'Ticker' in t.columns:
                    raw_tickers = t['Ticker'].tolist()
                    break
            
            # Correction : On n'ajoute .DE que s'il n'est pas déjà là
            tickers = []
            for t in raw_tickers:
                t = str(t).strip()
                if t.endswith('.DE'):
                    tickers.append(t)
                else:
                    tickers.append(f"{t}.DE")

        # --- TRI PAR MARKET CAP ---
        if not tickers:
            st.error("Aucun ticker trouvé sur Wikipédia.")
            return []

        status.text(f"⚡ Tri des {limit} plus grosses entreprises du {index_name}...")
        
        market_caps = {}
        
        # Sécurité pour les petits indices
        safe_limit = min(limit, len(tickers))

        # Batching
        batch_size = 50
        for i in range(0, len(tickers), batch_size):
            batch = tickers[i:i+batch_size]
            for t in batch:
                try:
                    # fast_info est très rapide et léger
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
        st.error(f"Erreur récupération {index_name} : {e}")
        return []

# --- 3. ANALYSE PROFONDE ---

@st.cache_data(ttl=3600*12)
def get_historical_valuation(ticker):
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        
        # Données de base
        sector = info.get('sector', 'Unknown')
        fwd_pe = info.get('forwardPE', None)
        currency = info.get('currency', 'USD')
        
        # Si pas de Forward PE (fréquent en Europe), on tente le Trailing PE comme fallback
        if fwd_pe is None:
            fwd_pe = info.get('trailingPE', None)
        
        if fwd_pe is None: return None

        # Historique
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
            
        avg_historical_pe = sum(pe_ratios) / len(pe_ratios)
        
        # Sécurité division par zéro
        if avg_historical_pe == 0: return None
        
        valuation_diff = (fwd_pe - avg_historical_pe) / avg_historical_pe
        
        return {
            "Ticker": ticker,
            "Name": info.get('shortName', ticker),
            "Sector": sector,
            "Currency": currency,
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
        status_text.text(f"Analyse en cours : {ticker} ({i+1}/{total})")
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
    selected_index = st.selectbox(
        "1. Choisir l'Indice", 
        ["S&P 500", "Nasdaq 100", "CAC 40 (France)", "DAX 40 (Allemagne)"]
    )

with col2:
    if "CAC 40" in selected_index or "DAX" in selected_index:
        max_val = 40
        default_val = 40
    elif "Nasdaq" in selected_index:
        max_val = 100
        default_val = 50
    else:
        max_val = 500
        default_val = 50
        
    nb_stocks = st.slider(f"2. Nombre d'actions (Max {max_val})", 
                          min_value=5, max_value=max_val, value=default_val, step=5)

with col3:
    st.write(" ")
    st.write(" ")
    start_btn = st.button("🚀 Lancer l'Analyse", type="primary", use_container_width=True)

if start_btn:
    
    top_tickers = get_top_tickers(selected_index, nb_stocks)
    
    if not top_tickers:
        st.error("Impossible de récupérer la liste. Essayez de relancer ou vérifiez votre connexion.")
    else:
        st.success(f"Cible identifiée : {len(top_tickers)} entreprises.")
        df = run_analysis(top_tickers)
        
        if not df.empty:
            st.divider()
            
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

            st.subheader(f"🗺️ Carte Thermique : {selected_index}")
            
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
                hovertemplate="<b>%{label}</b><br>Diff Moyenne: %{color:.1f}%<br>P/E: %{customdata[1]}<extra></extra>"
            )
            
            fig.update_layout(height=750, margin=dict(t=30, l=10, r=10, b=10))
            st.plotly_chart(fig, use_container_width=True)
            
            # Tableau
            st.subheader("Données Détaillées")
            
            currency_symbol = "€" if "France" in selected_index or "Allemagne" in selected_index else "$"

            def color_val(val):
                if val < -20: return 'color: blue; font-weight: bold'
                if val < 0: return 'color: green'
                if val > 40: return 'color: red; font-weight: bold'
                if val > 0: return 'color: orange'
                return 'color: black'

            st.dataframe(
                df.sort_values("Premium/Discount").style
                .format({
                    "Market Cap": currency_symbol + "{:,.0f}",
                    "Forward P/E": "{:.1f}",
                    "Avg Hist P/E": "{:.1f}",
                    "Premium/Discount": "{:+.1f}%"
                })
                .map(color_val, subset=['Premium/Discount']),
                use_container_width=True
            )
        else:
            st.warning("Aucune donnée disponible. Yahoo Finance peut manquer de données prévisionnelles (Forward P/E) sur certaines actions européennes aujourd'hui.")
