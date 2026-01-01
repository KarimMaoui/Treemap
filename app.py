import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.express as px
import time

# --- 1. CONFIGURATION DE LA PAGE ---
st.set_page_config(page_title="Nasdaq Tech Value Screener", layout="wide")

st.title("🧩 Nasdaq Tech Screener : Valorisation Relative")
st.markdown("""
**Analyse de la "Cherté" des actions Tech par rapport à leur propre histoire.**
* L'outil compare le **Forward P/E** (Attentes futures) au **P/E Moyen Historique** (5 dernières années).
* **Couleurs** :
    * 🟢 **Vert** : L'action est moins chère que d'habitude (Décote).
    * ⚪ **Gris** : L'action est à son prix historique normal.
    * 🔴 **Rouge** : L'action est plus chère que d'habitude (Prime).
""")

# --- 2. LISTE DES TICKERS (Nasdaq Tech / Growth Selection) ---
# Une sélection représentative de ~40 valeurs Tech majeures
tickers_list = [
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "AVGO", "ADBE", 
    "CRM", "AMD", "INTC", "CSCO", "NFLX", "QCOM", "TXN", "AMAT", "ADP", 
    "ADI", "MU", "LRCX", "INTU", "KLAC", "SNPS", "CDNS", "PANW", "NXPI", 
    "FTNT", "MRVL", "MCHP", "ON", "CRWD", "WDAY", "ZS", "DDOG", "TEAM", 
    "PLTR", "UBER", "ABNB", "TTD", "NET"
]

# --- 3. FONCTIONS DE RÉCUPÉRATION ET CALCUL ---

@st.cache_data(ttl=3600*12) # Cache de 12h pour ne pas recharger à chaque clic
def get_historical_valuation(ticker):
    """
    Récupère le Forward P/E et tente de reconstruire le P/E historique moyen sur ~5 ans.
    Renvoie None si données insuffisantes ou secteur non pertinent.
    """
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        
        # A. Filtre : On garde principalement la Tech et comms
        # (Certains comme Amazon sont "Consumer Cyclical", on accepte pour la pertinence)
        relevant_sectors = ['Technology', 'Communication Services', 'Consumer Cyclical']
        sector = info.get('sector', 'Unknown')
        
        if sector not in relevant_sectors:
            return None

        # B. Récupération Forward P/E
        fwd_pe = info.get('forwardPE', None)
        if fwd_pe is None:
            return None # Pas de prévision de bénéfice, on ignore

        # C. Calcul du P/E Historique (Estimation via Financials & History)
        financials = stock.financials
        if financials.empty: 
            return None
            
        # Trouver la ligne EPS (Basic ou Diluted)
        eps_data = financials.T 
        eps_cols = [c for c in eps_data.columns if 'EPS' in str(c) or 'Earnings' in str(c)]
        
        if not eps_cols:
            return None
            
        # Série EPS annuel
        eps_series = eps_data[eps_cols[0]].sort_index()
        
        # Historique de prix (5 ans)
        start_date = eps_series.index.min().strftime('%Y-%m-%d')
        history = stock.history(start=start_date)
        
        # Calcul des P/E annuels passés
        pe_ratios = []
        for date, eps in eps_series.items():
            year = date.year
            # Prix moyen de l'année concernée
            mask = history.index.year == year
            if not mask.any(): continue
            
            avg_price = history.loc[mask, 'Close'].mean()
            
            if avg_price and eps > 0: # On ignore les années de pertes pour la moyenne P/E
                pe_ratios.append(avg_price / eps)
        
        if not pe_ratios:
            return None
            
        avg_historical_pe = sum(pe_ratios) / len(pe_ratios)

        # D. Calcul de la Prime/Décote en %
        # Exemple: Fwd=20, Hist=25 -> (20-25)/25 = -0.20 (-20%)
        valuation_diff = (fwd_pe - avg_historical_pe) / avg_historical_pe
        
        return {
            "Ticker": ticker,
            "Name": info.get('shortName', ticker),
            "Sector": sector,
            "Market Cap": info.get('marketCap', 0),
            "Forward P/E": fwd_pe,
            "Avg Hist P/E": avg_historical_pe,
            "Premium/Discount": valuation_diff * 100  # Conversion en pourcentage
        }

    except Exception as e:
        return None

def run_scanner():
    data = []
    # Barre de progression visuelle
    progress_text = "Analyse fondamentale en cours (Yahoo Finance API)..."
    my_bar = st.progress(0, text=progress_text)
    
    total = len(tickers_list)
    
    for i, ticker in enumerate(tickers_list):
        res = get_historical_valuation(ticker)
        if res:
            data.append(res)
        
        # Mise à jour progression
        time.sleep(0.05) # Petite pause technique
        my_bar.progress((i + 1) / total, text=f"Analyse de {ticker}...")
    
    my_bar.empty()
    return pd.DataFrame(data)

# --- 4. INTERFACE UTILISATEUR & VISUALISATION ---

if st.button('🚀 Lancer le Market Screen', type="primary"):
    df = run_scanner()
    
    if not df.empty:
        # --- Metrics ---
        col1, col2, col3 = st.columns(3)
        col1.metric("Actions Analysées", len(df))
        
        median_val = df['Premium/Discount'].median()
        col2.metric("Valorisation Médiane", f"{median_val:+.1f}%", 
                    delta="Cher" if median_val > 0 else "Pas cher", delta_color="inverse")
        
        cheapest = df.loc[df['Premium/Discount'].idxmin()]
        col3.metric("La plus grosse décote", cheapest['Ticker'], f"{cheapest['Premium/Discount']:.1f}%")

        st.divider()

        # --- TREEMAP CONFIGURATION ---
        
       # --- TREEMAP CONFIGURATION ---
        
        # Échelle à 10 couleurs distinctes pour bien discriminer les zones
        # Du "Froid/Pas cher" (Bleu) vers le "Brûlant/Cher" (Rouge/Violet)
        custom_scale = [
            "#00008B", # 1. Bleu Nuit   (-80%) : Opportunité extrême
            "#0000FF", # 2. Bleu        (-60%) : Très sous-évalué
            "#00BFFF", # 3. Cyan        (-40%) : Sous-évalué
            "#2E8B57", # 4. Vert Mer    (-20%) : Bon prix
            "#32CD32", # 5. Vert Lime   ( -5%) : Légère décote
            "#FFFF00", # 6. Jaune       ( +5%) : Prix Juste / Légère prime
            "#FFD700", # 7. Or          (+20%) : Commence à être cher
            "#FF8C00", # 8. Orange Foncé(+40%) : Cher
            "#FF0000", # 9. Rouge       (+60%) : Très cher
            "#800080"  # 10. Violet     (+80%) : Bulle spéculative
        ]

        st.subheader("🗺️ Carte Thermique de Valorisation (10 Niveaux)")
        st.caption("Échelle : Bleu (Pas cher) ➔ Vert ➔ Jaune ➔ Rouge (Très cher)")

        fig = px.treemap(
            df,
            path=[px.Constant("Nasdaq Tech"), 'Sector', 'Ticker'],
            values='Market Cap',
            color='Premium/Discount',
            
            # Application de l'échelle à 10 couleurs
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
        
        # Amélioration du template visuel
        fig.update_traces(
            textinfo="label+text",
            hovertemplate=(
                "<b>%{label}</b><br>"
                "Premium/Discount: %{color:.1f}%<br>"
                "Fwd P/E: %{customdata[1]} (Moy: %{customdata[2]})"
            )
        )
        
        fig.update_layout(
            margin=dict(t=30, l=10, r=10, b=10),
            height=650,
        )
        
        st.plotly_chart(fig, use_container_width=True)
        
        # --- TABLEAU DÉTAILLÉ ---
        st.subheader("📋 Données Détaillées")
        
        # Fonction pour colorer le texte dans le tableau
        def color_valuation_text(val):
            if val < -10: color = 'green'
            elif val > 10: color = 'red'
            else: color = 'gray'
            return f'color: {color}; font-weight: bold'

        st.dataframe(
            df.sort_values("Premium/Discount").style
            .format({
                "Market Cap": "${:,.0f}",
                "Forward P/E": "{:.1f}",
                "Avg Hist P/E": "{:.1f}",
                "Premium/Discount": "{:+.1f}%"
            })
            .map(color_valuation_text, subset=['Premium/Discount']),
            use_container_width=True,
            height=400
        )
        
    else:
        st.error("Erreur : Impossible de récupérer les données. Vérifiez votre connexion.")
