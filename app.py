import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.express as px
import time

# --- CONFIGURATION ---
st.set_page_config(page_title="Tech Value Screener", layout="wide")
st.title("🧩 Nasdaq Tech Screener : Valorisation Relative")
st.markdown("""
Ce scanner compare la valorisation actuelle (**Forward P/E**) à la **moyenne historique** de l'action.
* **Vert** : L'action est moins chère que sa moyenne historique (Décote).
* **Rouge** : L'action est plus chère que sa moyenne historique (Prime).
""")

# Liste ciblée Tech / Growth (Nasdaq 100 Tech subset)
# Pour une vraie prod, on pourrait scraper la liste complète des tickers tech.
tickers_list = [
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "AVGO", "ADBE", 
    "CRM", "AMD", "INTC", "CSCO", "NFLX", "QCOM", "TXN", "AMAT", "ADP", 
    "ADI", "MU", "LRCX", "INTU", "KLAC", "SNPS", "CDNS", "PANW", "NXPI", 
    "FTNT", "MRVL", "MCHP", "ON", "CRWD", "WDAY", "ZS", "DDOG", "TEAM"
]

@st.cache_data(ttl=3600*24) # Cache les données pour 24h pour éviter de spammer Yahoo
def get_historical_valuation(ticker):
    """
    Tente de reconstruire un P/E historique et récupère le Forward P/E actuel.
    """
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        
        # 1. Filtre Secteur : On ne garde que la Tech
        # (Parfois Yahoo classe Amazon en "Cyclical", on est souple sur la condition)
        sector = info.get('sector', '')
        if 'Technology' not in sector and 'Communication' not in sector and 'Consumer' not in sector:
            return None

        # 2. Récupérer le Forward P/E actuel
        fwd_pe = info.get('forwardPE', None)
        if fwd_pe is None:
            return None

        # 3. Calculer le P/E Historique (Approximation)
        # Yahoo gratuit donne environ 4 ans de financials via .financials
        financials = stock.financials
        if financials.empty: 
            return None
            
        # On cherche le 'Basic EPS' ou 'Diluted EPS'
        try:
            # Transpose pour avoir les dates en index
            eps_data = financials.T 
            # On cherche une colonne qui ressemble à EPS
            eps_col = [c for c in eps_data.columns if 'EPS' in str(c) or 'Earnings Per Share' in str(c)]
            if not eps_col:
                return None
            
            # On prend la série d'EPS annuel
            eps_series = eps_data[eps_col[0]].sort_index()
            
            # On récupère l'historique de prix sur la même période (5 ans max en général pour financials)
            start_date = eps_series.index.min().strftime('%Y-%m-%d')
            history = stock.history(start=start_date)
            
            # On resample les prix en annuel (moyenne de l'année) pour simplifier le calcul
            yearly_prices = history['Close'].resample('YE').mean()
            
            # On aligne les index (approximatif par année) pour diviser Prix / EPS
            # Ceci est une estimation macro pour obtenir une "baseline" de valorisation
            pe_ratios = []
            for date, eps in eps_series.items():
                # On trouve le prix moyen de l'année correspondante
                year = date.year
                try:
                    avg_price_that_year = history[history.index.year == year]['Close'].mean()
                    if avg_price_that_year and eps > 0:
                        pe_ratios.append(avg_price_that_year / eps)
                except:
                    pass
            
            if not pe_ratios:
                return None
                
            avg_historical_pe = sum(pe_ratios) / len(pe_ratios)
            
        except Exception as e:
            # Fallback si calcul complexe échoue: on retourne None
            return None

        # Calcul de la "Premium / Discount" en %
        # Si (15 - 20) / 20 = -0.25 (-25% -> Vert)
        valuation_diff = (fwd_pe - avg_historical_pe) / avg_historical_pe
        
        return {
            "Ticker": ticker,
            "Name": info.get('shortName', ticker),
            "Sector": sector,
            "Market Cap": info.get('marketCap', 0),
            "Forward P/E": fwd_pe,
            "Avg Hist P/E": avg_historical_pe,
            "Premium/Discount": valuation_diff * 100  # En pourcentage
        }

    except Exception as e:
        return None

def run_scanner():
    data = []
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    total = len(tickers_list)
    
    for i, ticker in enumerate(tickers_list):
        status_text.text(f"Analyse des fondamentaux de {ticker}...")
        result = get_historical_valuation(ticker)
        if result:
            data.append(result)
        
        # Petite pause pour être gentil avec l'API Yahoo
        time.sleep(0.1) 
        progress_bar.progress((i + 1) / total)
    
    progress_bar.empty()
    status_text.empty()
    return pd.DataFrame(data)

if st.button('Lancer l\'analyse Tech', type="primary"):
    df = run_scanner()
    
    if not df.empty:
        col1, col2 = st.columns(2)
        col1.metric("Tech Stocks Analysés", len(df))
        avg_premium = df['Premium/Discount'].median()
        col2.metric("Niveau médian du marché", f"{avg_premium:.1f}%", 
                    delta="Surévalué" if avg_premium > 0 else "Sous-évalué",
                    delta_color="inverse")

        st.write("---")
        
        # --- LOGIQUE COULEUR HEATMAP ---
        # On veut: Vert si Discount (négatif), Rouge si Premium (positif)
        # Plotly 'RdYlGn_r' fait : Vert (bas) -> Jaune -> Rouge (haut)
        # C'est exactement ce qu'il nous faut car nos valeurs "Discount" sont basses (négatives).
        
        # On borne les couleurs entre -50% et +50% pour éviter qu'une anomalie écrase tout
        fig = px.treemap(
            df,
            path=[px.Constant("Nasdaq Tech"), 'Ticker'],
            values='Market Cap',
            color='Premium/Discount',
            hover_data=['Name', 'Forward P/E', 'Avg Hist P/E', 'Premium/Discount'],
            color_continuous_scale='RdYlGn_r', 
            range_color=[-50, 50], 
            title="Heatmap de Valorisation Relative (Vs Historique 5 ans)"
        )
        
        # Customisation du tooltip pour qu'il soit lisible
        fig.update_traces(hovertemplate='<b>%{label}</b><br>Market Cap: $%{value}<br>Premium/Discount: %{color:.2f}%<extra></extra>')
        
        fig.update_layout(height=650)
        st.plotly_chart(fig, use_container_width=True)
        
        st.subheader("Données brutes")
        st.dataframe(
            df.sort_values("Premium/Discount").style.format({
                "Market Cap": "${:,.0f}",
                "Forward P/E": "{:.1f}",
                "Avg Hist P/E": "{:.1f}",
                "Premium/Discount": "{:+.1f}%"
            }),
            use_container_width=True
        )
    else:
        st.error("Aucune donnée trouvée ou erreur API.")
