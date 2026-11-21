"""
Identidade visual do GESTAV.

Concentra a paleta de cores, a tipografia, o logótipo e os componentes
visuais (cartões de indicadores, cabeçalhos, alertas). Para mudar as
cores do sistema basta alterar o bloco PALETA abaixo.
"""

import html
import itertools
from datetime import datetime

import streamlit as st

# ----------------------------------------------------------------------
# Paleta (verde FAVET com toques terrosos)
# ----------------------------------------------------------------------
PALETA = {
    "g900": "#143620",   # verde muito escuro (menu lateral)
    "g800": "#1F4D2B",   # verde principal
    "g700": "#2C6A3A",
    "g500": "#4C8A55",
    "g100": "#E3EDDD",
    "g50": "#F4F7F0",    # fundo geral
    "ouro": "#C8963E",   # dourado (milho/ração)
    "ouro100": "#F6ECD9",
    "terra": "#6B4F2A",
    "tinta": "#1D2B20",  # texto principal
    "cinza": "#65705E",  # texto secundário
    "linha": "#E1E7DA",  # bordas
    "verm": "#B4392C",
    "verm100": "#FBE9E6",
    "amar": "#B7800A",
    "amar100": "#FCF1D6",
    "azul": "#2F6690",
    "azul100": "#E5EEF5",
}
P = PALETA

TONS = {
    "verde": (P["g700"], P["g100"]),
    "ouro": (P["terra"], P["ouro100"]),
    "verm": (P["verm"], P["verm100"]),
    "amar": (P["amar"], P["amar100"]),
    "azul": (P["azul"], P["azul100"]),
    "neutro": (P["cinza"], "#EEF1EA"),
}


# ----------------------------------------------------------------------
# Logótipo: frango com volume, luz e sombra (avicultura)
# ----------------------------------------------------------------------
_N_LOGO = itertools.count()


def _frango_svg(tamanho=44, fundo=False, k="gv", escala=1.0, raio=56):
    d = f'''<defs>
<radialGradient id="{k}bg" cx="35%" cy="28%" r="85%"><stop offset="0" stop-color="#2E7043"/><stop offset=".55" stop-color="#173D24"/><stop offset="1" stop-color="#0B2113"/></radialGradient>
<filter id="{k}sh" x="-30%" y="-30%" width="160%" height="160%"><feDropShadow dx="0" dy="7" stdDeviation="7" flood-color="#000" flood-opacity=".38"/></filter>
<filter id="{k}shp" x="-30%" y="-30%" width="160%" height="160%"><feDropShadow dx="0" dy="3" stdDeviation="3" flood-color="#000" flood-opacity=".35"/></filter>
<filter id="{k}b4" x="-60%" y="-60%" width="220%" height="220%"><feGaussianBlur stdDeviation="4"/></filter>
<filter id="{k}b8" x="-80%" y="-80%" width="260%" height="260%"><feGaussianBlur stdDeviation="8"/></filter>
<radialGradient id="{k}corpo" cx="55%" cy="35%" r="75%"><stop offset="0" stop-color="#F1C87E"/><stop offset=".45" stop-color="#D0943F"/><stop offset=".85" stop-color="#9A6226"/><stop offset="1" stop-color="#734515"/></radialGradient>
<linearGradient id="{k}asa" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#C4843A"/><stop offset="1" stop-color="#7A4A18"/></linearGradient>
<linearGradient id="{k}cauda" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#5A3410"/><stop offset="1" stop-color="#A86C2A"/></linearGradient>
<linearGradient id="{k}crista" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#F0604C"/><stop offset="1" stop-color="#A3261C"/></linearGradient>
<linearGradient id="{k}bico" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#F7D163"/><stop offset="1" stop-color="#C98E22"/></linearGradient>
<linearGradient id="{k}perna" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#E9B23F"/><stop offset="1" stop-color="#B07A1C"/></linearGradient>
</defs>'''
    f = (f'<rect width="256" height="256" rx="{raio}" fill="url(#{k}bg)"/>' if fundo else "")
    c = f'''<ellipse cx="128" cy="226" rx="74" ry="9" fill="#000" opacity=".35" filter="url(#{k}b4)"/>
<path d="M78 150 C52 120 48 82 60 58 C70 88 86 108 104 120 Z" fill="url(#{k}cauda)"/>
<path d="M74 142 C60 116 66 86 82 70 C84 96 96 112 110 122 Z" fill="#8A561E"/>
<g stroke="url(#{k}perna)" stroke-width="8" stroke-linecap="round" fill="none"><path d="M112 196 L110 222"/><path d="M146 196 L148 222"/><path d="M110 222 L96 226 M110 222 L114 227 M110 222 L124 225"/><path d="M148 222 L134 225 M148 222 L150 227 M148 222 L162 226"/></g>
<path d="M150 50 C146 34 158 26 164 38 C166 22 180 22 181 36 C188 26 200 32 194 50 Z" fill="url(#{k}crista)" filter="url(#{k}shp)"/>
<path d="M62 150 C62 112 94 92 132 96 C144 72 142 54 154 44 C168 34 188 40 192 56 C196 68 192 82 184 94 C208 110 216 136 208 160 C198 192 164 208 126 206 C88 204 62 184 62 150 Z" fill="url(#{k}corpo)" filter="url(#{k}sh)"/>
<ellipse cx="176" cy="126" rx="16" ry="26" fill="#FFF3D6" opacity=".35" filter="url(#{k}b8)"/>
<path d="M90 142 C108 118 152 116 174 138 C164 170 130 186 100 178 C88 168 86 154 90 142 Z" fill="url(#{k}asa)" filter="url(#{k}shp)"/>
<g fill="none" stroke="#5E3812" stroke-opacity=".55" stroke-width="3" stroke-linecap="round"><path d="M100 150 C118 140 146 140 164 146"/><path d="M98 160 C118 152 142 154 158 160"/><path d="M102 170 C118 166 136 168 148 172"/></g>
<path d="M189 58 L210 66 L189 74 Z" fill="url(#{k}bico)"/><path d="M189 66 L209 66" stroke="#9C6A18" stroke-width="1.5"/>
<path d="M184 76 C180 92 194 98 197 84 C198 79 194 76 190 76 Z" fill="url(#{k}crista)"/>
<circle cx="171" cy="60" r="7" fill="#2A1A08"/><circle cx="173.5" cy="57.5" r="2.4" fill="#fff"/>'''
    off = 128 - 128 * escala
    corpo = f'<g transform="translate({off} {off}) scale({escala})">{c}</g>' if escala != 1.0 else c
    s = f'<svg width="{tamanho}" height="{tamanho}" viewBox="0 0 256 256" xmlns="http://www.w3.org/2000/svg" aria-label="GESTAV">{d}{f}{corpo}</svg>'
    return "".join(l.strip() for l in s.splitlines())


def logo_svg(tamanho: int = 44, fundo: str | None = None) -> str:
    """Devolve o logótipo em SVG. Cada chamada usa ids próprios para os
    gradientes, para o logótipo poder aparecer várias vezes na mesma página."""
    return _frango_svg(tamanho, fundo=bool(fundo), k=f"gv{next(_N_LOGO)}_")


# ----------------------------------------------------------------------
# Ícones (traço simples, estilo Lucide)
# ----------------------------------------------------------------------
_ICONES = {
    "calendario": '<rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/>',
    "ovo": '<path d="M12 22c6.23-.05 7.87-5.57 7.5-10-.36-4.34-3.95-9.96-7.5-10-3.55.04-7.14 5.66-7.5 10-.37 4.43 1.27 9.95 7.5 10z"/>',
    "peso": '<circle cx="12" cy="5" r="3"/><path d="M6.5 8a2 2 0 0 0-1.9 1.46L2.1 18.5A2 2 0 0 0 4 21h16a2 2 0 0 0 1.93-2.54L19.4 9.5A2 2 0 0 0 17.48 8Z"/>',
    "subida": '<polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/><polyline points="16 7 22 7 22 13"/>',
    "descida": '<polyline points="22 17 13.5 8.5 8.5 13.5 2 7"/><polyline points="16 17 22 17 22 11"/>',
    "pulso": '<polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>',
    "escudo": '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="m9 12 2 2 4-4"/>',
    "ciclo": '<path d="m17 2 4 4-4 4"/><path d="M3 11v-1a4 4 0 0 1 4-4h14"/><path d="m7 22-4-4 4-4"/><path d="M21 13v1a4 4 0 0 1-4 4H3"/>',
    "medalha": '<circle cx="12" cy="8" r="6"/><path d="M15.48 12.89 17 22l-5-3-5 3 1.52-9.11"/>',
    "carteira": '<path d="M21 12V7H5a2 2 0 0 1 0-4h14v4"/><path d="M3 5v14a2 2 0 0 0 2 2h16v-5"/><path d="M18 12a2 2 0 0 0 0 4h4v-4Z"/>',
    "nota": '<rect x="2" y="6" width="20" height="12" rx="2"/><circle cx="12" cy="12" r="2"/><path d="M6 12h.01M18 12h.01"/>',
    "percent": '<line x1="19" y1="5" x2="5" y2="19"/><circle cx="6.5" cy="6.5" r="2.5"/><circle cx="17.5" cy="17.5" r="2.5"/>',
    "aviso": '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>',
    "info": '<circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/>',
    "ok": '<path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/>',
    "lampada": '<path d="M9 18h6"/><path d="M10 22h4"/><path d="M15.09 14c.18-.98.65-1.74 1.41-2.5A4.65 4.65 0 0 0 18 8 6 6 0 0 0 6 8c0 1 .23 2.23 1.5 3.5A4.61 4.61 0 0 1 8.91 14"/>',
    "racao": '<path d="M2 22 16 8"/><path d="M3.47 12.53 5 11l1.53 1.53a3.5 3.5 0 0 1 0 4.94L5 19l-1.53-1.53a3.5 3.5 0 0 1 0-4.94Z"/><path d="M7.47 8.53 9 7l1.53 1.53a3.5 3.5 0 0 1 0 4.94L9 15l-1.53-1.53a3.5 3.5 0 0 1 0-4.94Z"/><path d="M11.47 4.53 13 3l1.53 1.53a3.5 3.5 0 0 1 0 4.94L13 11l-1.53-1.53a3.5 3.5 0 0 1 0-4.94Z"/><path d="M20 2h2v2a4 4 0 0 1-4 4h-2V6a4 4 0 0 1 4-4Z"/>',
    "camada": '<path d="m12 2 10 5-10 5L2 7l10-5z"/><path d="m2 17 10 5 10-5"/><path d="m2 12 10 5 10-5"/>',
}


def icone(nome: str, tamanho: int = 18, cor: str = "currentColor") -> str:
    corpo = _ICONES.get(nome, _ICONES["info"])
    return (
        f'<svg width="{tamanho}" height="{tamanho}" viewBox="0 0 24 24" fill="none" '
        f'stroke="{cor}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">{corpo}</svg>'
    )


# ----------------------------------------------------------------------
# Formatação de números (padrão moçambicano: 1.234,56)
# ----------------------------------------------------------------------
def num(valor, casas: int = 0) -> str:
    try:
        v = float(valor)
    except (TypeError, ValueError):
        return "–"
    if v != v or v in (float("inf"), float("-inf")):
        return "–"
    txt = f"{v:,.{casas}f}"
    return txt.replace(",", "§").replace(".", ",").replace("§", ".")


def mzn(valor, casas: int = 0) -> str:
    return f"{num(valor, casas)} MZN"


def _e(txt) -> str:
    return html.escape(str(txt)) if txt is not None else ""


# ----------------------------------------------------------------------
# CSS global
# ----------------------------------------------------------------------
_CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,650&family=Manrope:wght@400;500;600;700;800&display=swap');

:root {{
  --g900:{P['g900']}; --g800:{P['g800']}; --g700:{P['g700']}; --g500:{P['g500']};
  --g100:{P['g100']}; --g50:{P['g50']}; --ouro:{P['ouro']}; --ouro100:{P['ouro100']};
  --terra:{P['terra']}; --tinta:{P['tinta']}; --cinza:{P['cinza']}; --linha:{P['linha']};
  --verm:{P['verm']}; --verm100:{P['verm100']}; --amar:{P['amar']}; --amar100:{P['amar100']};
  --azul:{P['azul']}; --azul100:{P['azul100']};
}}

/* Base */
.stApp {{ background: var(--g50); color: var(--tinta); }}
.stApp, .stApp p, .stApp li, .stApp label, .stApp input, .stApp textarea,
.stApp button, .stApp td, .stApp th, .stApp span, .stApp div[data-baseweb] {{
  font-family: 'Manrope', system-ui, -apple-system, 'Segoe UI', sans-serif;
}}
.stApp [data-testid="stIconMaterial"], .stApp span[class*="material"] {{
  font-family: 'Material Symbols Rounded' !important;
}}
.stApp h1, .stApp h2, .stApp h3, .stApp h4 {{
  font-family: 'Manrope', system-ui, sans-serif; color: var(--tinta);
  letter-spacing: -0.01em;
}}
.gv-cab h1 *, .gv-hero h1 *, .gv-login-arte h1 *, .gv-login-titulo h2 * {{ font-family: inherit !important; }}
.stApp [data-testid="stHeaderActionElements"] {{ display: none; }}
header[data-testid="stHeader"] {{ background: transparent; }}
[data-testid="stDecoration"] {{ display: none; }}
[data-testid="stToolbarActions"], [data-testid="stAppDeployButton"], #MainMenu {{ display: none; }}
[data-testid="stMainBlockContainer"], .block-container {{
  padding-top: 2.2rem; padding-bottom: 3rem; max-width: 1240px;
}}

/* Menu lateral */
[data-testid="stSidebar"] {{ background: var(--g900); border-right: 0; }}
[data-testid="stSidebar"] * {{ color: #DCE7D6; }}
[data-testid="stSidebar"] [data-testid="stSidebarHeader"] {{ padding-bottom: 0; }}
[data-testid="stSidebar"] .stButton button {{
  justify-content: flex-start; border-radius: 10px; padding: .42rem .8rem;
  min-height: 2.35rem; border: 0; background: transparent; font-weight: 500;
  font-size: .93rem; transition: background .15s ease;
}}
[data-testid="stSidebar"] .stButton button > div,
[data-testid="stSidebar"] .stButton button > div > span {{ justify-content: flex-start !important; width: 100%; gap: .65rem; }}
[data-testid="stSidebar"] .stButton button:hover {{ background: rgba(255,255,255,.07); }}
[data-testid="stSidebar"] [data-testid="stIconMaterial"] {{ color: #9FBDA4 !important; }}
[data-testid="stSidebar"] [data-testid="stBaseButton-primary"] [data-testid="stIconMaterial"] {{ color: var(--ouro) !important; }}
[data-testid="stSidebar"] .stButton button[kind="primary"],
[data-testid="stSidebar"] [data-testid="stBaseButton-primary"] {{
  background: rgba(200,150,62,.16); box-shadow: inset 3px 0 0 var(--ouro);
}}
[data-testid="stSidebar"] [data-testid="stBaseButton-primary"] * {{ color: #F3D9A6; font-weight: 700; }}
[data-testid="stSidebar"] [data-testid="stVerticalBlock"] {{ gap: .15rem; }}
[data-testid="stSidebar"] hr {{ border-color: rgba(255,255,255,.08); margin: .6rem 0; }}

.gv-marca {{ display:flex; align-items:center; gap:.7rem; padding:.2rem .2rem 1rem; }}
.gv-marca b {{ font-family:'Fraunces',serif; font-size:1.45rem; font-weight:650; color:#FFFFFF !important; letter-spacing:.01em; display:block; line-height:1; }}
.gv-marca small {{ font-size:.7rem; letter-spacing:.14em; text-transform:uppercase; color:#93AE97 !important; }}
.gv-grupo {{ font-size:.68rem; letter-spacing:.14em; text-transform:uppercase; color:#7F9C84 !important; font-weight:700; margin:.95rem 0 0 .8rem; padding-bottom:1.15rem; }}
.gv-utilizador {{ display:flex; align-items:center; gap:.65rem; padding:.6rem .7rem; border-radius:12px; background:rgba(255,255,255,.05); margin-top:.4rem; }}
.gv-utilizador .av {{ width:34px; height:34px; border-radius:50%; background:var(--ouro); color:var(--g900) !important; font-weight:800; display:flex; align-items:center; justify-content:center; font-size:.85rem; flex:none; }}
.gv-utilizador b {{ display:block; font-size:.85rem; color:#FFFFFF !important; line-height:1.2; }}
.gv-utilizador small {{ font-size:.72rem; color:#93AE97 !important; }}

/* Botões, formulários e campos na área principal */
.stApp [data-testid="stBaseButton-primary"] {{
  background: var(--g800); border-color: var(--g800); border-radius: 10px; font-weight: 700;
}}
.stApp [data-testid="stBaseButton-primary"]:hover {{ background: var(--g700); border-color: var(--g700); }}
.stApp [data-testid="stBaseButton-secondary"] {{ border-radius: 10px; border-color: var(--linha); background:#fff; font-weight:600; }}
.stApp [data-testid="stBaseButton-secondary"]:hover {{ border-color: var(--g500); color: var(--g800); }}
[data-testid="stForm"] {{
  background:#FFFFFF; border:1px solid var(--linha); border-radius:16px;
  padding:1.3rem 1.5rem 1.1rem; box-shadow:0 1px 2px rgba(20,54,32,.04);
}}
.stApp div[data-baseweb="input"], .stApp div[data-baseweb="select"] > div,
.stApp div[data-baseweb="textarea"], .stApp div[data-baseweb="base-input"] {{ border-radius:10px; }}
[data-testid="stExpander"] details {{ background:#FFFFFF; border:1px solid var(--linha); border-radius:14px; }}
[data-testid="stDataFrame"] {{ border:1px solid var(--linha); border-radius:12px; overflow:hidden; background:#fff; }}
[data-testid="stAlert"] {{ border-radius:12px; }}
[data-testid="stFileUploaderDropzone"] {{ background:#fff; border-radius:14px; border:1.5px dashed #BFCDB6; }}

.st-key-atalhos button {{ min-height:66px; border-radius:14px !important; background:#fff; border:1px solid var(--linha) !important; font-weight:700 !important; color:var(--tinta) !important; }}
.st-key-atalhos button:hover {{ border-color:var(--g500) !important; background:var(--g100) !important; }}
.st-key-atalhos [data-testid="stIconMaterial"] {{ color:var(--g700) !important; font-size:1.35rem !important; }}
.stApp [class*="st-key-caixa"] {{ background:#FFFFFF; border-radius:16px !important; border-color:var(--linha) !important; padding:1rem 1.1rem .6rem; }}

/* Cabeçalho de página */
.gv-cab {{ margin: 0 0 1.4rem; }}
.gv-cab .eyebrow {{ font-size:.72rem; letter-spacing:.16em; text-transform:uppercase; color:var(--g700); font-weight:800; }}
.gv-cab h1 {{ font-family:'Fraunces',serif !important; font-weight:650; font-size:2.1rem; margin:.15rem 0 .25rem; padding:0; color:var(--tinta); line-height:1.15; }}
.gv-cab p {{ color:var(--cinza); margin:0; font-size:.98rem; max-width:62ch; }}

.gv-secao {{ display:flex; align-items:baseline; gap:.6rem; margin:1.6rem 0 .7rem; }}
.gv-secao h3 {{ font-size:1.12rem !important; font-weight:800; margin:0; padding:0; color:var(--tinta) !important; }}
.gv-secao span {{ color:var(--cinza); font-size:.85rem; }}

/* Cartões de indicadores */
.gv-grid {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(190px, 1fr)); gap:14px; }}
.gv-kpi {{ background:#FFFFFF; border:1px solid var(--linha); border-radius:16px; padding:14px 16px 13px; min-width:0; }}
.gv-kpi .topo {{ display:flex; align-items:center; gap:.55rem; color:var(--cinza); font-size:.8rem; font-weight:600; }}
.gv-kpi .chip {{ width:30px; height:30px; border-radius:9px; display:flex; align-items:center; justify-content:center; flex:none; }}
.gv-kpi .valor {{ font-size:1.65rem; font-weight:800; color:var(--tinta); margin-top:.55rem; line-height:1.1; font-variant-numeric:tabular-nums; letter-spacing:-0.02em; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
.gv-kpi .valor small {{ font-size:.85rem; font-weight:600; color:var(--cinza); margin-left:.2rem; letter-spacing:0; }}
.gv-kpi .nota {{ font-size:.78rem; color:var(--cinza); margin-top:.3rem; }}

/* Comparação com a referência */
.gv-sema {{ background:#FFFFFF; border:1px solid var(--linha); border-radius:16px; padding:14px 16px; border-left:5px solid var(--cor); }}
.gv-sema .nome {{ font-size:.82rem; color:var(--cinza); font-weight:700; }}
.gv-sema .linha {{ display:flex; align-items:baseline; justify-content:space-between; gap:.5rem; margin-top:.35rem; }}
.gv-sema .actual {{ font-size:1.5rem; font-weight:800; font-variant-numeric:tabular-nums; }}
.gv-sema .ref {{ font-size:.8rem; color:var(--cinza); }}
.gv-pilula {{ display:inline-flex; align-items:center; gap:.3rem; padding:.18rem .55rem; border-radius:999px; font-size:.74rem; font-weight:800; background:var(--fundo); color:var(--cor); white-space:nowrap; }}
.gv-barra {{ height:6px; background:#EEF1EA; border-radius:99px; margin-top:.6rem; overflow:hidden; }}
.gv-barra i {{ display:block; height:100%; background:var(--cor); border-radius:99px; }}

/* Faixa de alerta */
.gv-faixa {{ display:flex; align-items:center; gap:.8rem; background:var(--verm100); border:1px solid #F1C9C2; color:var(--verm); border-radius:14px; padding:.8rem 1rem; margin-bottom:1rem; font-size:.92rem; }}
.gv-faixa b {{ color:var(--verm); }}

/* Cartão de alerta */
.gv-alerta {{ background:#FFFFFF; border:1px solid var(--linha); border-radius:16px; padding:14px 18px 12px; border-left:5px solid var(--cor); margin-bottom:.4rem; }}
.gv-alerta .meta {{ display:flex; flex-wrap:wrap; align-items:center; gap:.5rem; font-size:.78rem; color:var(--cinza); }}
.gv-alerta h4 {{ margin:.45rem 0 .2rem !important; font-size:1.02rem !important; font-weight:800; padding:0 !important; }}
.gv-alerta p {{ margin:0; color:var(--tinta); font-size:.92rem; }}
.gv-dica {{ display:flex; gap:.55rem; align-items:flex-start; margin-top:.7rem; background:var(--g50); border-radius:10px; padding:.6rem .75rem; font-size:.87rem; color:var(--tinta); }}
.gv-dica svg {{ flex:none; margin-top:2px; }}

/* Página inicial */
.gv-hero {{
  position:relative; overflow:hidden; border-radius:22px; padding:2rem 2.2rem;
  background: radial-gradient(circle at 88% 15%, rgba(200,150,62,.35), transparent 42%),
              radial-gradient(circle at 70% 120%, rgba(76,138,85,.45), transparent 50%),
              linear-gradient(135deg, var(--g900), var(--g800) 60%, #24603A);
  color:#fff; margin-bottom:1.2rem;
}}
.gv-hero .data {{ font-size:.75rem; letter-spacing:.16em; text-transform:uppercase; color:#BFD6C2; font-weight:700; }}
.gv-hero h1 {{ font-family:'Fraunces',serif !important; color:#FFFFFF !important; font-size:2.3rem; font-weight:650; margin:.3rem 0 .4rem; padding:0; line-height:1.12; }}
.gv-hero p {{ color:#D7E5D8; margin:0; max-width:56ch; font-size:1rem; }}
.gv-hero .marca-agua {{ position:absolute; right:-18px; bottom:-26px; opacity:.16; }}
.gv-hero-stats {{ display:flex; flex-wrap:wrap; gap:.7rem; margin-top:1.3rem; }}
.gv-hero-stats div {{ background:rgba(255,255,255,.1); border:1px solid rgba(255,255,255,.14); border-radius:12px; padding:.55rem .9rem; font-size:.82rem; color:#D7E5D8; }}
.gv-hero-stats b {{ display:block; color:#FFFFFF; font-size:1.25rem; font-weight:800; }}

/* Ecrã de entrada */
.gv-login-arte {{
  border-radius:24px; min-height:520px; padding:2.4rem; color:#fff; display:flex; flex-direction:column; justify-content:space-between;
  background: radial-gradient(circle at 85% 12%, rgba(200,150,62,.42), transparent 40%),
              radial-gradient(circle at 10% 110%, rgba(76,138,85,.55), transparent 55%),
              linear-gradient(150deg, var(--g900), var(--g800));
  position:relative; overflow:hidden;
}}
.gv-login-arte h1 {{ font-family:'Fraunces',serif !important; color:#fff !important; font-size:3rem; font-weight:650; margin:1.4rem 0 .4rem; padding:0; line-height:1; }}
.gv-login-arte .lema {{ color:#D7E5D8; font-size:1.05rem; max-width:34ch; margin:0; }}
.gv-login-arte ul {{ list-style:none; padding:0; margin:1.6rem 0 0; }}
.gv-login-arte li {{ display:flex; gap:.6rem; align-items:center; color:#E6EFE3; font-size:.93rem; margin:.55rem 0; }}
.gv-login-arte li span {{ width:26px; height:26px; border-radius:8px; background:rgba(255,255,255,.12); display:flex; align-items:center; justify-content:center; flex:none; }}
.gv-login-arte footer {{ font-size:.75rem; letter-spacing:.14em; text-transform:uppercase; color:#A9C3AD; }}
.gv-login-titulo {{ margin:3.2rem 0 1rem; }}
.gv-login-titulo h2 {{ font-family:'Fraunces',serif !important; font-size:1.9rem; font-weight:650; margin:0; padding:0; }}
.gv-login-titulo p {{ color:var(--cinza); margin:.3rem 0 0; }}
.gv-dica-acesso {{ font-size:.82rem; color:var(--cinza); background:#fff; border:1px dashed #C9D5C1; border-radius:12px; padding:.6rem .8rem; margin-top:.9rem; }}
.gv-dica-acesso code {{ background:var(--g100); color:var(--g800); border-radius:6px; padding:.05rem .35rem; }}

.gv-vazio {{ background:#fff; border:1px dashed #C9D5C1; border-radius:16px; padding:1.6rem; text-align:center; color:var(--cinza); }}
</style>
"""


def aplicar_estilo():
    st.markdown(_CSS, unsafe_allow_html=True)


# ----------------------------------------------------------------------
# Componentes
# ----------------------------------------------------------------------
def cabecalho(titulo: str, subtitulo: str = "", eyebrow: str = ""):
    st.markdown(
        f'<div class="gv-cab">'
        f'{f"<div class=eyebrow>{_e(eyebrow)}</div>" if eyebrow else ""}'
        f"<h1>{_e(titulo)}</h1>"
        f'{f"<p>{_e(subtitulo)}</p>" if subtitulo else ""}'
        f"</div>",
        unsafe_allow_html=True,
    )


def secao(titulo: str, nota: str = ""):
    st.markdown(
        f'<div class="gv-secao"><h3>{_e(titulo)}</h3>'
        f'{f"<span>{_e(nota)}</span>" if nota else ""}</div>',
        unsafe_allow_html=True,
    )


def kpi_html(rotulo: str, valor: str, unidade: str = "", nota: str = "",
             ico: str = "info", tom: str = "verde") -> str:
    cor, fundo = TONS.get(tom, TONS["neutro"])
    uni = f"<small>{_e(unidade)}</small>" if unidade else ""
    nt = f'<div class="nota">{_e(nota)}</div>' if nota else ""
    return (
        f'<div class="gv-kpi"><div class="topo">'
        f'<span class="chip" style="background:{fundo}">{icone(ico, 17, cor)}</span>'
        f"{_e(rotulo)}</div>"
        f'<div class="valor">{_e(valor)}{uni}</div>{nt}</div>'
    )


def grelha(cartoes: list[str], minimo: int = 190, preencher: bool = False):
    modo = "auto-fill" if preencher else "auto-fit"
    estilo_grid = f"grid-template-columns:repeat({modo}, minmax({minimo}px, 1fr))"
    st.markdown(f'<div class="gv-grid" style="{estilo_grid}">{"".join(cartoes)}</div>',
                unsafe_allow_html=True)


def semaforo_html(nome: str, actual: float, ref: float, cor_nome: str, desvio: float,
                  casas: int = 1) -> str:
    mapa = {"verde": ("verde", "Dentro da meta"), "amarelo": ("amar", "Atenção"),
            "vermelho": ("verm", "Crítico")}
    tom, rotulo = mapa.get(cor_nome, ("neutro", "Sem dados"))
    cor, fundo = TONS[tom]
    # Barra: proporção do valor actual face à referência (limitada a 100%)
    prop = 0 if not ref else max(0, min(100, actual / ref * 100))
    sinal = "+" if desvio > 0 else ""
    return (
        f'<div class="gv-sema" style="--cor:{cor};--fundo:{fundo}">'
        f'<div class="nome">{_e(nome)}</div>'
        f'<div class="linha"><span class="actual">{num(actual, casas)}</span>'
        f'<span class="gv-pilula">{rotulo} · {sinal}{num(desvio, 1)}%</span></div>'
        f'<div class="ref">Referência Ross 308: {num(ref, casas)}</div>'
        f'<div class="gv-barra"><i style="width:{prop:.0f}%"></i></div></div>'
    )


NIVEIS = {
    "critico": ("verm", "Crítico", "aviso"),
    "aviso": ("amar", "Aviso", "aviso"),
    "info": ("azul", "Informativo", "info"),
}


def alerta_html(a: dict) -> str:
    tom, rotulo, ico = NIVEIS.get(a.get("nivel"), ("neutro", "Alerta", "info"))
    cor, fundo = TONS[tom]
    dica = ""
    if a.get("recomendacao"):
        dica = (f'<div class="gv-dica">{icone("lampada", 16, P["ouro"])}'
                f'<span><b>Recomendação:</b> {_e(a["recomendacao"])}</span></div>')
    return (
        f'<div class="gv-alerta" style="--cor:{cor};--fundo:{fundo}">'
        f'<div class="meta"><span class="gv-pilula">{icone(ico, 13, cor)} {rotulo}</span>'
        f'<span>Ciclo <b>{_e(a.get("ciclo_codigo", ""))}</b></span><span>·</span>'
        f'<span>{_e(a.get("data", ""))}</span></div>'
        f'<h4>{_e(a.get("titulo", ""))}</h4><p>{_e(a.get("mensagem", ""))}</p>{dica}</div>'
    )


def faixa_alerta(n_criticos: int):
    st.markdown(
        f'<div class="gv-faixa">{icone("aviso", 20, P["verm"])}'
        f'<span><b>{n_criticos} alerta(s) crítico(s) por resolver.</b> '
        f'Abra o módulo Alertas para ver a intervenção recomendada.</span></div>',
        unsafe_allow_html=True,
    )


def vazio(texto: str):
    st.markdown(f'<div class="gv-vazio">{_e(texto)}</div>', unsafe_allow_html=True)


def saudacao() -> str:
    h = datetime.now().hour
    if h < 12:
        return "Bom dia"
    if h < 18:
        return "Boa tarde"
    return "Boa noite"


MESES = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho",
         "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
DIAS = ["Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira",
        "Sexta-feira", "Sábado", "Domingo"]


def data_extenso(d=None) -> str:
    d = d or datetime.now()
    return f"{DIAS[d.weekday()]}, {d.day} de {MESES[d.month - 1]} de {d.year}"


def iniciais(nome: str) -> str:
    partes = [p for p in nome.split() if p]
    if not partes:
        return "?"
    if len(partes) == 1:
        return partes[0][:2].upper()
    return (partes[0][0] + partes[-1][0]).upper()


# ----------------------------------------------------------------------
# Gráficos (Altair, já incluído no Streamlit)
# ----------------------------------------------------------------------
def tema_grafico(chart):
    return (
        chart.configure(font="Manrope", background="transparent")
        .configure_view(strokeWidth=0)
        .configure_axis(labelColor=P["cinza"], titleColor=P["cinza"], gridColor="#EDF1E8",
                        domainColor=P["linha"], tickColor=P["linha"], labelFontSize=11,
                        titleFontSize=11, titleFontWeight=600)
        .configure_legend(labelColor=P["tinta"], titleColor=P["cinza"], orient="top",
                          labelFontSize=12)
    )
