import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.express as px
import time
import requests
from io import StringIO

# --- 1. CONFIGURATION DE LA PAGE ---
st.set_page_config(page_title="Super Market Screener", layout="wide")

st.title("🚀 Super Market Screener : Multi-Indices")
st.markdown("""
**Analysez la valorisation du marché US.**
* **Vert** : Les bénéfices attendus sont supérieurs aux bénéfices actuels (Dynamique positive / "Moins cher" dans le futur).
* **Rouge** : Les bénéfices attendus sont inférieurs (Dynamique négative / "Plus cher" dans le futur).
""")

# --- 2. RÉCUPÉRATION DES LISTES (CORRECTIF ANTI-403) ---

@st.cache_data
def get_tickers(index_name):
    """
    Récupère la liste des tickers depuis Wikipedia.
    Utilise un 'User-Agent' pour éviter l'erreur HTTP 403 Forbidden.
    """
    tickers = []
    
    # C'est ici que la magie opère : on fait croire qu'on est un navigateur Chrome
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }

    try:
        if index_name == "Nasdaq 100":
            url = "https://en.wikipedia.org/wiki/Nasdaq-100"
            response = requests.get(url, headers=headers)
            # On utilise StringIO pour convertir le texte en fichier lisible par pandas
            tables = pd.read_html(StringIO(response.text))
            
            for table in tables:
                if 'Ticker' in table.columns:
                    tickers = table['Ticker'].tolist()
                    break
                if 'Symbol' in table.columns:
                    tickers = table['Symbol'].tolist()
                    break
            
        elif index_name == "S&P 500":
            url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
            response = requests.get(url, headers=headers)
            table = pd.read_html(StringIO(response.text))[0]
            tickers = table['Symbol'].tolist()
            # Yahoo utilise des tirets au lieu des points (ex: BRK-B)
            tickers = [t.replace('.', '-') for t in tickers]

        elif index_name == "Dow Jones 30":
            url = "https://en.wikipedia.org/wiki/Dow_Jones_Industrial_Average"
            response = requests.get(url, headers=headers)
            table = pd.read_html(StringIO(response.text))[1]
            tickers = table['Symbol'].tolist()
            
        elif index_name == "Tech Small Caps (Demo)":
            tickers = [
                "PLTR", "PATH", "U", "DKNG", "RBLX", "AFRM", "HOOD", "DUOL", 
                "MDB", "NET", "OKTA", "TWLO", "DOCU", "ZS", "CRWD", "BILL", 
                "GTLB", "HCP", "S", "IOT", "APP", "ASAN", "CFLT", "MNDY"
            ]
            
    except Exception as e:
        st.error(f"Erreur lors de la récupération de l'indice : {e}")
        return []
    
    return tickers

# --- 3. MOTEUR D'ANALYSE ---

@st.cache_data(ttl=3600*12)
def analyze_market(tickers, max_items=100):
    
    # Limitation pour la performance (Yahoo peut être lent)
    if len(tickers) > max_items:
        st.warning(f"⚠️ Analyse limitée aux {max_items} premières actions de l'indice pour la rapidité.")
        tickers = tickers[:max_items]

    data = []
    # Barre de progression
    progress_bar = st.progress(0)
    status_text = st.empty()
    total = len(tickers)
    
    for i, ticker in enumerate(tickers):
        status_text.text(f"Scan en cours : {ticker}")
        
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            
            market_cap = info.get('marketCap', 0)
            if not market_cap: continue

            # Pour le scan rapide multi-indices, on compare Forward vs Trailing
            # C'est le meilleur proxy de "Tendance de Valorisation" instantané
            fwd_pe = info.get('forwardPE', None)
            trailing_pe = info.get('trailingPE', None)
            
            sector = info.get('sector', 'Inconnu')
            industry = info.get('industry', 'Inconnu')
            name = info.get('shortName', ticker)

            val_score = 0
            
            if fwd_pe and trailing_pe:
                # Si Fwd < Trailing : L'action devient "moins chère" (Bénéfices en hausse) -> Score Négatif (Vert)
                # Si Fwd > Trailing : L'action devient "plus chère" (Bénéfices en baisse) -> Score Positif (Rouge)
                val_score = ((fwd_pe - trailing_pe) / trailing_pe) * 100
            
            if fwd_pe is not None:
                data.append({
                    "Ticker": ticker,
                    "Name": name,
                    "Sector": sector,
                    "Industry": industry,
                    "Market Cap": market_cap,
                    "Forward P/E": fwd_pe,
                    "Trailing P/E": trailing_pe if trailing_pe else 0,
                    "Valuation Trend": val_score 
                })

        except Exception:
            pass
        
        # Mise à jour barre progression
        progress_bar.progress((i + 1) / total)
    
    progress_bar.empty()
    status_text.empty()
    return pd.DataFrame(data)

# --- 4. BARRE LATÉRALE ---

with st.sidebar:
    st.header("⚙️ Réglages")
    
    selected_index = st.selectbox(
        "Indice à scanner :",
        ("Nasdaq 100", "Dow Jones 30", "S&P 500", "Tech Small Caps (Demo)")
    )
    
    # Slider vital pour ne pas attendre 10 minutes sur le S&P 500
    limit_stocks = st.slider("Limite nombre d'actions", 10, 500, 50)
    
    st.divider()
    
    if st.button("Lancer l'analyse", type="primary"):
        st.session_state['run_analysis'] = True

# --- 5. VISUALISATION ---

if st.session_state.get('run_analysis'):
    
    # 1. Récupération liste
    tickers = get_tickers(selected_index)
    
    if tickers:
        st.info(f"🔍 {len(tickers)} actions trouvées dans {selected_index}. Lancement du scan...")
        
        # 2. Scan
        df = analyze_market(tickers, max_items=limit_stocks)
        
        if not df.empty:
            st.write("---")
            
            # 3. Configuration des couleurs (Ton échelle 10 couleurs)
            custom_scale = [
                "#00008B", # Bleu Nuit   (-80%) 
                "#0000FF", # Bleu        (-60%) 
                "#00BFFF", # Cyan        (-40%) 
                "#2E8B57", # Vert Mer    (-20%) 
                "#32CD32", # Vert Lime   ( -5%) 
                "#FFFF00", # Jaune       ( +5%) 
                "#FFD700", # Or          (+20%) 
                "#FF8C00", # Orange      (+40%) 
                "#FF0000", # Rouge       (+60%) 
                "#800080"  # Violet      (+80%) 
            ]

            st.subheader(f"🗺️ Heatmap : {selected_index}")
            st.caption("Cliquez sur un secteur pour zoomer (Drill-down).")
            
            # Création de la Treemap
            fig = px.treemap(
                df,
                # Hiérarchie pour le zoom : Indice -> Secteur -> Industrie -> Action
                path=[px.Constant(selected_index), 'Sector', 'Industry', 'Ticker'], 
                values='Market Cap',
                color='Valuation Trend',
                
                # Tes réglages visuels
                color_continuous_scale=custom_scale,
                range_color=[-80, 80],
                
                hover_data={
                    'Valuation Trend': ':.1f%',
                    'Forward P/E': ':.1f',
                    'Trailing P/E': ':.1f',
                    'Sector': False,
                    'Ticker': False
                }
            )
            
            fig.update_traces(
                textinfo="label+text",
                hovertemplate="<b>%{label}</b><br>Val Trend: %{color:.1f}%<br>Fwd P/E: %{customdata[1]}<extra></extra>"
            )
            
            fig.update_layout(height=800, margin=dict(t=30, l=10, r=10, b=10))
            st.plotly_chart(fig, use_container_width=True)
            
            # Tableau de données
            st.subheader("Données détaillées")
            st.dataframe(
                df.sort_values("Valuation Trend")
                .style.format({
                    "Market Cap": "${:,.0f}", 
                    "Forward P/E": "{:.1f}", 
                    "Valuation Trend": "{:+.1f}%"
                }),
                use_container_width=True
            )
            
        else:
            st.warning("Aucune donnée récupérée. Vérifiez votre connexion internet.")
    else:
        st.error("Impossible de récupérer la liste de l'indice.")

else:
    st.info("👈 Choisissez un indice à gauche et cliquez sur le bouton pour démarrer.")
