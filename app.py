import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.express as px

# Configuration de la page
st.set_page_config(page_title="Nasdaq P/E Screener", layout="wide")

st.title("📊 Nasdaq Market Screener - Analyse P/E")
st.markdown("Cet outil récupère les données en temps réel via Yahoo Finance.")

# 1. Liste des Tickers (Top Nasdaq 100 pour la démo)
# Dans une version avancée, on pourrait charger un CSV complet.
tickers_list = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "TSLA", "META", "AVGO", "PEP", 
    "COST", "CSCO", "TMUS", "CMCSA", "ADBE", "TXN", "NFLX", "AMD", "QCOM", 
    "INTC", "AMGN", "HON", "INTU", "SBUX", "GILD", "BKNG", "ADI", "MDLZ", 
    "ISRG", "REGN", "VRTX", "LRCX", "PANW", "SNPS", "KLAC", "CDNS", "CHTR", 
    "MAR", "CSX", "ORLY", "MNST", "MELI", "LULU", "WDA", "ASML", "NXPI"
]

@st.cache_data
def get_stock_data(tickers):
    data = []
    # Barre de progression
    progress_bar = st.progress(0)
    
    # Récupération des données par paquets pour optimiser
    # yfinance permet de télécharger plusieurs tickers, mais pour les infos détaillées (info), 
    # il est souvent plus stable d'itérer ou d'utiliser Tickers object.
    
    total = len(tickers)
    
    for i, ticker in enumerate(tickers):
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            
            # On récupère uniquement ce qui nous intéresse
            pe_ratio = info.get('trailingPE', None)
            market_cap = info.get('marketCap', 0)
            sector = info.get('sector', 'Unknown')
            name = info.get('shortName', ticker)
            
            # On ne garde que les actions qui ont un P/E (les entreprises profitables)
            if pe_ratio is not None:
                data.append({
                    "Ticker": ticker,
                    "Name": name,
                    "P/E Ratio": pe_ratio,
                    "Market Cap": market_cap,
                    "Sector": sector
                })
        except Exception as e:
            continue
        
        # Mise à jour de la barre
        progress_bar.progress((i + 1) / total)
            
    progress_bar.empty()
    return pd.DataFrame(data)

# Bouton pour lancer l'analyse
if st.button('Lancer le Scan (Top Nasdaq)', type="primary"):
    with st.spinner('Récupération des données fondamentales...'):
        df = get_stock_data(tickers_list)
        
        if not df.empty:
            # Stats rapides
            col1, col2, col3 = st.columns(3)
            col1.metric("Actions Analysées", len(df))
            col2.metric("P/E Moyen", round(df['P/E Ratio'].mean(), 2))
            col3.metric("Secteurs Uniques", df['Sector'].nunique())

            st.write("---")

            # --- VISUALISATION TREEMAP ---
            st.subheader("Carte du Marché (Taille = Market Cap | Couleur = P/E Ratio)")
            
            # On plafonne le P/E pour la couleur (sinon un P/E de 1000 écrase tout le spectre)
            # Les P/E > 60 seront de la même couleur maximale
            fig = px.treemap(
                df, 
                path=[px.Constant("Nasdaq"), 'Sector', 'Ticker'], 
                values='Market Cap',
                color='P/E Ratio',
                hover_data=['Name', 'P/E Ratio', 'Market Cap'],
                color_continuous_scale='RdYlGn_r', # Rouge = Cher (Haut P/E), Vert = Pas cher (Bas P/E)
                range_color=[10, 60], # Plage de couleur pour le P/E
                title="Nasdaq Heatmap par P/E Ratio"
            )
            
            fig.update_layout(margin = dict(t=50, l=25, r=25, b=25), height=600)
            st.plotly_chart(fig, use_container_width=True)
            
            # --- TABLEAU DE DONNÉES ---
            st.subheader("Données Détaillées")
            st.dataframe(
                df.sort_values(by="P/E Ratio", ascending=True)
                .style.format({"Market Cap": "${:,.0f}", "P/E Ratio": "{:.2f}"}),
                use_container_width=True
            )
        else:
            st.error("Aucune donnée récupérée. Vérifiez votre connexion internet.")
