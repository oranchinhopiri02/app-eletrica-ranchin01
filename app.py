import re
import unicodedata
from datetime import date

import gspread
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st
from google.oauth2.service_account import Credentials

SHEET_ID = "1IUCnDgYntjco9oV0Tqr45ZOpVvP4XC7p5UUmusbtdho"
WORKSHEET_ID = 734599707
SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

st.set_page_config(
    page_title="App Custos Ranchin",
    page_icon="🌿",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Paleta visual
VERDE_ESCURO = "#173D32"
VERDE = "#2E6B50"
FUNDO = "#F4F7F4"

st.markdown(
    f"""
    <style>
    .stApp {{ background-color: {FUNDO}; }}
    [data-testid="stMetric"] {{
        background: white; padding: 16px 18px; border-radius: 12px;
        border: 1px solid #E1E9E2;
    }}
    h1, h2, h3 {{ color: {VERDE_ESCURO}; }}
    </style>
    """,
    unsafe_allow_html=True,
)

def normalizar_texto(valor):
    texto = str(valor or "").strip().lower()
    texto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in texto if not unicodedata.combining(c))

def converter_valor(valor):
    if valor is None or str(valor).strip() == "":
        return np.nan
    if isinstance(valor, (int, float, np.number)):
        return float(valor)
    texto = str(valor).strip().replace("R$", "").replace(" ", "")
    # Formato brasileiro: 1.234,56. Também aceita decimal com ponto.
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    try:
        return float(texto)
    except ValueError:
        return np.nan

@st.cache_data(ttl=300, show_spinner="Atualizando dados da planilha...")
def carregar_dados():
    if "gcp_service_account" not in st.secrets:
        raise RuntimeError(
            "Credenciais não configuradas. Adicione [gcp_service_account] "
            "em Settings > Secrets no Streamlit."
        )
    info = dict(st.secrets["gcp_service_account"])
    credentials = Credentials.from_service_account_info(info, scopes=SCOPES)
    client = gspread.authorize(credentials)
    spreadsheet = client.open_by_key(SHEET_ID)
    worksheet = next(
        (ws for ws in spreadsheet.worksheets() if ws.id == WORKSHEET_ID),
        None,
    )
    if worksheet is None:
        raise RuntimeError(f"A aba com gid {WORKSHEET_ID} não foi encontrada.")
    rows = worksheet.get_all_values()
    if not rows:
        return pd.DataFrame()
    headers = [str(h).strip() for h in rows[0]]
    data = rows[1:]
    frame = pd.DataFrame(data, columns=headers)
    return frame

def preparar_dados(raw):
    df = raw.copy()
    for col in ["tipo", "produto", "obs", "verba"]:
        if col not in df:
            df[col] = ""
        df[col] = df[col].fillna("").astype(str).str.strip()

    if "valor" not in df or "data" not in df:
        raise RuntimeError("A planilha precisa conter as colunas 'data' e 'valor'.")

    df["valor"] = df["valor"].apply(converter_valor)
    df["data"] = pd.to_datetime(df["data"], dayfirst=True, errors="coerce")
    df["tipo"] = df["tipo"].apply(normalizar_texto)
    df["verba"] = df["verba"].str.upper().str.strip()
    df["produto"] = df["produto"].replace("", "SEM PRODUTO")
    df["responsavel"] = df["verba"].replace("", "NÃO INFORMADO")
    df["mes_inicio"] = df["data"].dt.to_period("M").dt.to_timestamp()
    df["mes_ano"] = df["mes_inicio"].dt.strftime("%m/%Y")
    return df

def moeda(valor):
    valor = float(valor or 0)
    return ("R$ " + f"{valor:,.2f}").replace(",", "X").replace(".", ",").replace("X", ".")

st.title("🌿 APP CUSTOS RANCHIN")
st.caption("Painel de acompanhamento de custos, investimentos e despesas.")

try:
    bruto = carregar_dados()
    dados = preparar_dados(bruto)
except Exception as exc:
    st.error(f"Não foi possível carregar a planilha: {exc}")
    st.info(
        "Confira se a planilha foi compartilhada com o e-mail da conta de serviço "
        "e se as credenciais foram adicionadas aos Secrets."
    )
    st.stop()

# Apenas datas e valores válidos entram nas análises financeiras.
dados_validos = dados.dropna(subset=["data", "valor"]).copy()
if dados_validos.empty:
    st.warning("Não há lançamentos com data e valor válidos.")
    st.stop()

# Filtros globais
st.sidebar.header("Filtros")
data_min = dados_validos["data"].min().date()
data_max = dados_validos["data"].max().date()
periodo = st.sidebar.date_input(
    "Período",
    value=(data_min, data_max),
    min_value=data_min,
    max_value=data_max,
)
if isinstance(periodo, (tuple, list)) and len(periodo) == 2:
    inicio, fim = periodo
else:
    inicio = fim = periodo

produtos = sorted(dados_validos["produto"].dropna().unique().tolist())
responsaveis = sorted(dados_validos["responsavel"].dropna().unique().tolist())
sel_produtos = st.sidebar.multiselect("Produto / categoria", produtos, default=produtos)
sel_resp = st.sidebar.multiselect("Responsável (verba)", responsaveis, default=responsaveis)

filtrado = dados_validos[
    dados_validos["data"].dt.date.between(inicio, fim)
    & dados_validos["produto"].isin(sel_produtos)
    & dados_validos["responsavel"].isin(sel_resp)
].copy()

custos = filtrado[filtrado["tipo"] == "custo"].copy()
investimentos = filtrado[filtrado["tipo"] == "investimento"].copy()
pendentes = filtrado[~filtrado["tipo"].isin(["custo", "investimento"])].copy()

# Indicadores
c1, c2, c3, c4 = st.columns(4)
c1.metric("Total de custos", moeda(custos["valor"].sum()))
c2.metric("Total de investimentos", moeda(investimentos["valor"].sum()))
c3.metric("Lançamentos filtrados", f"{len(filtrado)}")
c4.metric("Pendentes de classificação", f"{len(pendentes)}")

st.caption(
    f"Dados atualizados a partir do Google Sheets · "
    f"Última leitura sob demanda / cache de até 5 minutos · "
    f"{len(dados)} registros na base."
)

aba1, aba2, aba3, aba4, aba5 = st.tabs(
    ["Visão geral", "Produtos", "Despesas mensais", "Responsáveis", "Lançamentos"]
)

with aba1:
    st.subheader("Custos e investimentos ao longo do tempo")
    mensal_c = (
        custos.groupby("mes_inicio", as_index=False)["valor"]
        .sum().rename(columns={"valor": "Custos"})
    )
    mensal_i = (
        investimentos.groupby("mes_inicio", as_index=False)["valor"]
        .sum().rename(columns={"valor": "Investimentos"})
    )
    serie = pd.merge(mensal_c, mensal_i, on="mes_inicio", how="outer").fillna(0)
    if not serie.empty:
        serie = serie.sort_values("mes_inicio")
        serie = serie.melt(
            id_vars="mes_inicio", var_name="Tipo", value_name="Valor"
        )
        fig = px.bar(
            serie, x="mes_inicio", y="Valor", color="Tipo", barmode="group",
            labels={"mes_inicio": "Mês", "Valor": "Valor (R$)"},
            color_discrete_map={"Custos": VERDE_ESCURO, "Investimentos": "#D5A84B"},
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Não há dados para o período selecionado.")

    esq, dir = st.columns(2)
    with esq:
        st.subheader("Maiores custos por produto")
        ranking = custos.groupby("produto", as_index=False)["valor"].sum()
        ranking = ranking.sort_values("valor", ascending=False).head(8)
        if not ranking.empty:
            fig = px.bar(
                ranking.sort_values("valor"), x="valor", y="produto",
                orientation="h", labels={"valor": "Valor (R$)", "produto": "Produto"},
                color_discrete_sequence=[VERDE],
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Sem custos no filtro selecionado.")
    with dir:
        st.subheader("Distribuição dos custos")
        por_produto = custos.groupby("produto", as_index=False)["valor"].sum()
        if not por_produto.empty:
            fig = px.pie(por_produto, names="produto", values="valor", hole=0.55)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Sem custos no filtro selecionado.")

with aba2:
    st.subheader("Custos por produto / categoria")
    tabela = custos.groupby("produto", as_index=False).agg(
        total=("valor", "sum"), lancamentos=("valor", "count")
    ).sort_values("total", ascending=False)
    if not tabela.empty:
        tabela["total"] = tabela["total"].map(moeda)
        st.dataframe(tabela, use_container_width=True, hide_index=True)
    else:
        st.info("Sem custos no filtro selecionado.")

with aba3:
    st.subheader("Despesas mensais")
    mensal = custos.groupby("mes_inicio", as_index=False).agg(
        total=("valor", "sum"), quantidade=("valor", "count")
    ).sort_values("mes_inicio")
    if not mensal.empty:
        fig = px.line(
            mensal, x="mes_inicio", y="total", markers=True,
            labels={"mes_inicio": "Mês", "total": "Custos (R$)"},
        )
        fig.update_traces(line_color=VERDE_ESCURO)
        st.plotly_chart(fig, use_container_width=True)
        mensal["total"] = mensal["total"].map(moeda)
        st.dataframe(mensal, use_container_width=True, hide_index=True)
    else:
        st.info("Sem custos no filtro selecionado.")

with aba4:
    st.subheader("Custos por responsável")
    resp = custos.groupby("responsavel", as_index=False)["valor"].sum()
    resp = resp.sort_values("valor", ascending=False)
    if not resp.empty:
        fig = px.bar(
            resp, x="responsavel", y="valor",
            labels={"responsavel": "Responsável", "valor": "Custos (R$)"},
            color_discrete_sequence=[VERDE],
        )
        st.plotly_chart(fig, use_container_width=True)
        resp["valor"] = resp["valor"].map(moeda)
        st.dataframe(resp, use_container_width=True, hide_index=True)
    else:
        st.info("Sem custos no filtro selecionado.")
    st.caption(
        "Lançamentos com mais de um responsável permanecem agrupados "
        "na categoria conjunta; nenhum valor é duplicado ou dividido."
    )

with aba5:
    st.subheader("Todos os lançamentos do período")
    colunas = [
        c for c in ["data", "valor", "tipo", "produto", "responsavel", "obs"]
        if c in filtrado.columns
    ]
    tabela_lanc = filtrado[colunas].sort_values("data", ascending=False).copy()
    tabela_lanc["data"] = tabela_lanc["data"].dt.strftime("%d/%m/%Y")
    tabela_lanc["valor"] = tabela_lanc["valor"].map(moeda)
    st.dataframe(tabela_lanc, use_container_width=True, hide_index=True)

    st.subheader("Pendências de classificação")
    if not pendentes.empty:
        st.warning(
            f"{len(pendentes)} lançamento(s) sem tipo custo/investimento. "
            "Eles não entram nos totais classificados."
        )
        st.dataframe(
            pendentes[["data", "valor", "produto", "tipo", "responsavel", "obs"]],
            use_container_width=True, hide_index=True,
        )
    else:
        st.success("Nenhuma pendência de classificação neste filtro.")

st.sidebar.divider()
if st.sidebar.button("Atualizar dados agora", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

st.sidebar.caption("Fonte: planilha Google Sheets do App Custos Ranchin.")
