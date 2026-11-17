import unicodedata
import gspread
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from google.oauth2.service_account import Credentials

# Configurações da planilha energia-ranchin-2026 (aba cadastro)
SHEET_ID = "1n5BB17H99z429qltuQZGWNvq6kdLsRNpwoAOnr-_A7o"
WORKSHEET_ID = 713758891
SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

st.set_page_config(
    page_title="App Elétrica Ranchin",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Paleta visual (mantendo identidade visual do Ranchin)
VERDE_ESCURO = "#173D32"
VERDE = "#2E6B50"
DOURADO = "#D5A84B"
FUNDO = "#F4F7F4"

st.markdown(
    f"""
    <style>
    .stApp {{ background-color: {FUNDO}; }}
    [data-testid="stMetric"] {{
        background: white;
        padding: 16px 18px;
        border-radius: 12px;
        border: 1px solid #E1E9E2;
        box-shadow: 0 1px 2px rgba(0,0,0,0.03);
    }}
    h1, h2, h3 {{ color: {VERDE_ESCURO}; }}
    </style>
    """,
    unsafe_allow_html=True,
)


def normalizar_chave(texto):
    t = str(texto or "").strip().lower()
    t = unicodedata.normalize("NFKD", t)
    return "".join(c for c in t if not unicodedata.combining(c))


def converter_numero(valor):
    if valor is None or str(valor).strip() == "":
        return np.nan
    if isinstance(valor, (int, float, np.number)):
        return float(valor)
    texto = str(valor).strip().replace("R$", "").replace(" ", "")
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    try:
        return float(texto)
    except ValueError:
        return np.nan


def moeda(valor):
    valor = float(valor or 0)
    return ("R$ " + f"{valor:,.2f}").replace(",", "X").replace(".", ",").replace("X", ".")


def numero_br(valor, casas=2):
    if pd.isna(valor):
        return "-"
    return f"{float(valor):,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


@st.cache_data(ttl=300, show_spinner="Atualizando leituras de energia...")
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

    # Trata cabeçalhos duplicados (ex.: 'chuveiro ??', 'tomada ??', 'iluminação ??')
    raw_headers = [str(h).strip() for h in rows[0]]
    seen = {}
    headers = []
    for h in raw_headers:
        base = h if h else "coluna"
        if base in seen:
            seen[base] += 1
            headers.append(f"{base} ({seen[base]})")
        else:
            seen[base] = 1
            headers.append(base)

    return pd.DataFrame(rows[1:], columns=headers)


def preparar_dados(raw):
    df = raw.copy()

    # Mapeamento flexível das colunas principais
    mapa_cols = {normalizar_chave(c): c for c in df.columns}

    def obter_col(nome_norm):
        return mapa_cols.get(nome_norm)

    col_kw_medido = obter_col("kw medido")
    col_hospedes = obter_col("hospedes")
    col_obs = obter_col("obs")
    col_dias = obter_col("dias decorridos")
    col_kw_periodo = obter_col("kw/periodo")
    col_kw_dia = obter_col("kw/dia")
    col_tarifa = obter_col("valor por kw")
    col_valor = obter_col("valor gasto")
    col_dia = obter_col("dia")
    col_mes = obter_col("mes")
    col_ano = obter_col("ano")
    col_dia_medido = obter_col("dia medido")

    # Reconstrução segura da data usando dia, mes, ano
    if col_dia and col_mes and col_ano:
        datas = pd.to_datetime(
            dict(
                year=pd.to_numeric(df[col_ano], errors="coerce"),
                month=pd.to_numeric(df[col_mes], errors="coerce"),
                day=pd.to_numeric(df[col_dia], errors="coerce"),
            ),
            errors="coerce",
        )
    else:
        datas = pd.to_datetime(df[col_dia_medido], dayfirst=True, errors="coerce")

    df["data_leitura"] = datas
    df = df.dropna(subset=["data_leitura"]).copy()
    df = df.sort_values("data_leitura").reset_index(drop=True)

    df["kw_medido"] = df[col_kw_medido].apply(converter_numero) if col_kw_medido else np.nan
    df["dias_decorridos"] = df[col_dias].apply(converter_numero) if col_dias else np.nan
    df["kw_periodo"] = df[col_kw_periodo].apply(converter_numero) if col_kw_periodo else np.nan
    df["kw_dia"] = df[col_kw_dia].apply(converter_numero) if col_kw_dia else np.nan
    df["tarifa_kw"] = df[col_tarifa].apply(converter_numero) if col_tarifa else np.nan
    df["valor_gasto"] = df[col_valor].apply(converter_numero) if col_valor else np.nan

    # Tratamento de hóspedes e categorias de ocupação
    if col_hospedes:
        hosp_num = df[col_hospedes].apply(converter_numero)
        df["hospedes_num"] = hosp_num
        df["hospedes_label"] = hosp_num.apply(
            lambda x: "Não informado" if pd.isna(x) else ("0 (Vazio)" if x == 0 else f"{int(x)} hóspede(s)")
        )
        df["status_ocupacao"] = hosp_num.apply(
            lambda x: "Não informado" if pd.isna(x) else ("Sem hóspedes" if x == 0 else "Com hóspedes")
        )
    else:
        df["hospedes_num"] = np.nan
        df["hospedes_label"] = "Não informado"
        df["status_ocupacao"] = "Não informado"

    df["obs"] = df[col_obs].fillna("").astype(str).str.strip() if col_obs else ""
    df["custo_dia"] = np.where(
        df["dias_decorridos"] > 0,
        df["valor_gasto"] / df["dias_decorridos"],
        0.0,
    )
    df["mes_inicio"] = df["data_leitura"].dt.to_period("M").dt.to_timestamp()
    df["mes_ano"] = df["data_leitura"].dt.strftime("%m/%Y")
    df["data_str"] = df["data_leitura"].dt.strftime("%d/%m/%Y")

    # Identifica colunas de disjuntores/circuitos (a partir da coluna 'geral')
    circuitos = []
    encontrou_geral = False
    for c in df.columns:
        if normalizar_chave(c) == "geral":
            encontrou_geral = True
        if encontrou_geral and c not in [
            "data_leitura", "kw_medido", "dias_decorridos", "kw_periodo",
            "kw_dia", "tarifa_kw", "valor_gasto", "hospedes_num",
            "hospedes_label", "status_ocupacao", "obs", "custo_dia",
            "mes_inicio", "mes_ano", "data_str",
        ]:
            circuitos.append(c)

    return df, circuitos


st.title("⚡ APP ELÉTRICA RANCHIN")
st.caption("Monitoramento de consumo energético (kWh), custos por período, ocupação e circuitos.")

try:
    bruto = carregar_dados()
    dados, cols_circuitos = preparar_dados(bruto)
except Exception as exc:
    st.error(f"Não foi possível carregar a planilha: {exc}")
    st.info(
        "Confira se a planilha 'energia-ranchin-2026' está compartilhada com o e-mail "
        "da conta de serviço e se [gcp_service_account] está configurado nos Secrets."
    )
    st.stop()

if dados.empty:
    st.warning("Não há registros válidos na aba 'cadastro'.")
    st.stop()

# ==================== BARRA LATERAL: FILTROS & SIMULADOR ====================
st.sidebar.header("Filtros")
data_min = dados["data_leitura"].min().date()
data_max = dados["data_leitura"].max().date()

periodo = st.sidebar.date_input(
    "Período das leituras",
    value=(data_min, data_max),
    min_value=data_min,
    max_value=data_max,
)
if isinstance(periodo, (tuple, list)) and len(periodo) == 2:
    inicio, fim = periodo
else:
    inicio = fim = periodo

opcoes_ocupacao = sorted(dados["status_ocupacao"].unique().tolist())
sel_ocupacao = st.sidebar.multiselect(
    "Ocupação no período",
    options=opcoes_ocupacao,
    default=opcoes_ocupacao,
)

busca_obs = st.sidebar.text_input(
    "Buscar nas observações",
    placeholder="Ex: Reinaldo, manutenção, festa...",
)

filtrado = dados[
    dados["data_leitura"].dt.date.between(inicio, fim)
    & dados["status_ocupacao"].isin(sel_ocupacao)
].copy()

if busca_obs.strip():
    filtrado = filtrado[
        filtrado["obs"].str.contains(busca_obs.strip(), case=False, na=False)
    ]

# Simulador rápido de conta / leitura na sidebar
st.sidebar.divider()
st.sidebar.subheader("🧮 Simulador de Consumo")
tarifa_recente = float(dados["tarifa_kw"].dropna().iloc[-1]) if not dados["tarifa_kw"].dropna().empty else 1.14
ultima_leitura_relogio = float(dados["kw_medido"].dropna().iloc[-1]) if not dados["kw_medido"].dropna().empty else 0.0

leitura_simulada = st.sidebar.number_input(
    f"Nova leitura do relógio (última: {int(ultima_leitura_relogio)} kWh)",
    min_value=0.0,
    value=float(ultima_leitura_relogio + 100),
    step=10.0,
)
tarifa_simulada = st.sidebar.number_input(
    "Tarifa (R$ / kWh)",
    min_value=0.0,
    value=tarifa_recente,
    step=0.01,
    format="%.3f",
)
diff_kwh = max(0.0, leitura_simulada - ultima_leitura_relogio)
st.sidebar.info(
    f"**Consumo estimado:** {numero_br(diff_kwh, 1)} kWh\n\n"
    f"**Custo estimado:** {moeda(diff_kwh * tarifa_simulada)}"
)

st.sidebar.divider()
if st.sidebar.button("Atualizar dados agora", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

st.sidebar.caption("Fonte: Google Sheets (energia-ranchin-2026).")

if filtrado.empty:
    st.warning("Nenhuma leitura encontrada para os filtros selecionados.")
    st.stop()

# ==================== INDICADORES PRINCIPAIS (KPIs) ====================
total_gasto = filtrado["valor_gasto"].sum()
total_kwh = filtrado["kw_periodo"].sum()
total_dias = filtrado["dias_decorridos"].sum()
media_kwh_dia = (total_kwh / total_dias) if total_dias > 0 else filtrado["kw_dia"].mean()
media_custo_dia = (total_gasto / total_dias) if total_dias > 0 else filtrado["custo_dia"].mean()
leitura_atual = filtrado["kw_medido"].dropna().iloc[-1]
data_ultima = filtrado["data_str"].iloc[-1]

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Gasto Total no Período", moeda(total_gasto))
c2.metric("Consumo Total", f"{numero_br(total_kwh, 0)} kWh")
c3.metric("Média Diária (kWh)", f"{numero_br(media_kwh_dia, 2)} kWh/dia")
c4.metric("Custo Médio Diário", f"{moeda(media_custo_dia)}/dia")
c5.metric(
    "Última Leitura Medidor",
    f"{numero_br(leitura_atual, 0)} kWh",
    delta=f"Em {data_ultima}",
    delta_color="off",
)

st.caption(
    f"Exibindo {len(filtrado)} leitura(s) · {int(total_dias)} dias acumulados · "
    f"Tarifa vigente: {moeda(tarifa_recente)}/kWh."
)

# ==================== ABAS DE NAVEGAÇÃO ====================
aba1, aba2, aba3, aba4 = st.tabs(
    ["📊 Visão Geral", "🏡 Hóspedes & Ocupação", "🔌 Circuitos & Tarifa", "📋 Histórico de Leituras"]
)

with aba1:
    st.subheader("Consumo e gasto consolidado por mês")
    mensal = (
        filtrado.groupby(["mes_inicio", "mes_ano"], as_index=False)
        .agg(
            gasto=("valor_gasto", "sum"),
            kwh=("kw_periodo", "sum"),
            dias=("dias_decorridos", "sum"),
            leituras=("kw_medido", "count"),
        )
        .sort_values("mes_inicio")
    )
    mensal["kw_dia_medio"] = np.where(mensal["dias"] > 0, mensal["kwh"] / mensal["dias"], 0)

    col_g1, col_g2 = st.columns(2)
    with col_g1:
        fig_gasto = px.bar(
            mensal,
            x="mes_ano",
            y="gasto",
            text_auto=".2s",
            title="Valor Gasto por Mês (R$)",
            labels={"mes_ano": "Mês/Ano", "gasto": "Valor (R$)"},
            color_discrete_sequence=[VERDE_ESCURO],
        )
        fig_gasto.update_traces(textposition="outside")
        st.plotly_chart(fig_gasto, use_container_width=True)

    with col_g2:
        fig_kwh = px.bar(
            mensal,
            x="mes_ano",
            y="kwh",
            text_auto=".0f",
            title="Consumo Acumulado por Mês (kWh)",
            labels={"mes_ano": "Mês/Ano", "kwh": "Consumo (kWh)"},
            color_discrete_sequence=[VERDE],
        )
        fig_kwh.update_traces(textposition="outside")
        st.plotly_chart(fig_kwh, use_container_width=True)

    st.subheader("Evolução da média diária de consumo (kWh/dia) por leitura")
    leituras_validas_dia = filtrado[filtrado["dias_decorridos"] > 0].copy()
    if not leituras_validas_dia.empty:
        fig_linha = px.line(
            leituras_validas_dia,
            x="data_leitura",
            y="kw_dia",
            markers=True,
            hover_data={
                "data_str": True,
                "kw_periodo": ":.1f",
                "valor_gasto": ":.2f",
                "dias_decorridos": True,
                "hospedes_label": True,
                "obs": True,
                "data_leitura": False,
            },
            labels={
                "data_leitura": "Data da Leitura",
                "kw_dia": "Média Diária (kWh/dia)",
                "data_str": "Data",
                "kw_periodo": "kWh no período",
                "valor_gasto": "Valor (R$)",
                "dias_decorridos": "Dias",
                "hospedes_label": "Ocupação",
                "obs": "Observação",
            },
        )
        fig_linha.update_traces(line_color=VERDE_ESCURO, marker_size=8)
        fig_linha.add_hline(
            y=media_kwh_dia,
            line_dash="dash",
            line_color=DOURADO,
            annotation_text=f"Média geral: {numero_br(media_kwh_dia, 2)} kWh/dia",
        )
        st.plotly_chart(fig_linha, use_container_width=True)

with aba2:
    st.subheader("Impacto de Hóspedes e Ocupação no Consumo")
    st.markdown(
        "Compara o consumo médio diário (**kWh/dia**) e o custo diário (**R$/dia**) "
        "entre períodos com casa vazia/manutenção e períodos com hóspedes."
    )

    df_ocup = filtrado[filtrado["dias_decorridos"] > 0].copy()
    if not df_ocup.empty:
        resumo_ocup = (
            df_ocup.groupby("status_ocupacao", as_index=False)
            .agg(
                leituras=("data_leitura", "count"),
                dias_totais=("dias_decorridos", "sum"),
                kwh_total=("kw_periodo", "sum"),
                gasto_total=("valor_gasto", "sum"),
            )
        )
        resumo_ocup["kwh_dia_ponderado"] = resumo_ocup["kwh_total"] / resumo_ocup["dias_totais"]
        resumo_ocup["custo_dia_ponderado"] = resumo_ocup["gasto_total"] / resumo_ocup["dias_totais"]

        o1, o2 = st.columns(2)
        with o1:
            fig_oc1 = px.bar(
                resumo_ocup,
                x="status_ocupacao",
                y="kwh_dia_ponderado",
                text_auto=".2f",
                title="Consumo Médio Diário por Perfil de Ocupação (kWh/dia)",
                labels={"status_ocupacao": "Ocupação", "kwh_dia_ponderado": "kWh / dia"},
                color="status_ocupacao",
                color_discrete_map={
                    "Sem hóspedes": VERDE,
                    "Com hóspedes": DOURADO,
                    "Não informado": "#8C9A9E",
                },
            )
            fig_oc1.update_layout(showlegend=False)
            st.plotly_chart(fig_oc1, use_container_width=True)

        with o2:
            fig_oc2 = px.bar(
                resumo_ocup,
                x="status_ocupacao",
                y="custo_dia_ponderado",
                text_auto=".2f",
                title="Custo Médio Diário por Perfil de Ocupação (R$/dia)",
                labels={"status_ocupacao": "Ocupação", "custo_dia_ponderado": "R$ / dia"},
                color="status_ocupacao",
                color_discrete_map={
                    "Sem hóspedes": VERDE,
                    "Com hóspedes": DOURADO,
                    "Não informado": "#8C9A9E",
                },
            )
            fig_oc2.update_layout(showlegend=False)
            st.plotly_chart(fig_oc2, use_container_width=True)

        tabela_ocup = resumo_ocup.copy()
        tabela_ocup["kwh_total"] = tabela_ocup["kwh_total"].map(lambda x: f"{numero_br(x, 1)} kWh")
        tabela_ocup["gasto_total"] = tabela_ocup["gasto_total"].map(moeda)
        tabela_ocup["kwh_dia_ponderado"] = tabela_ocup["kwh_dia_ponderado"].map(lambda x: f"{numero_br(x, 2)} kWh/dia")
        tabela_ocup["custo_dia_ponderado"] = tabela_ocup["custo_dia_ponderado"].map(lambda x: f"{moeda(x)}/dia")
        tabela_ocup.columns = [
            "Perfil de Ocupação", "Leituras", "Dias Acumulados",
            "Consumo Total", "Gasto Total", "Média kWh/dia", "Custo Médio/dia"
        ]
        st.dataframe(tabela_ocup, use_container_width=True, hide_index=True)

with aba3:
    st.subheader("Histórico da Tarifa (Valor por kWh)")
    fig_tarifa = px.step(
        filtrado,
        x="data_leitura",
        y="tarifa_kw",
        markers=True,
        labels={"data_leitura": "Data da Leitura", "tarifa_kw": "Tarifa (R$/kWh)"},
    )
    fig_tarifa.update_traces(line_color=VERDE_ESCURO)
    st.plotly_chart(fig_tarifa, use_container_width=True)

    st.subheader("Status dos Circuitos / Disjuntores nas Leituras")
    if cols_circuitos:
        ultima_linha = filtrado.iloc[-1]
        st.markdown(f"**Estado na última leitura filtrada ({ultima_linha['data_str']}):**")
        cols_cards = st.columns(5)
        for idx, circ in enumerate(cols_circuitos):
            estado = str(ultima_linha[circ]).strip().upper() or "-"
            icone = "🟢" if estado == "ON" else ("🔴" if estado == "OFF" else "⚪")
            cols_cards[idx % 5].info(f"{icone} **{circ}**\n\nStatus: `{estado}`")

        with st.expander("Ver matriz histórica completa dos circuitos"):
            tabela_circ = filtrado[["data_str", "kw_dia", "hospedes_label"] + cols_circuitos].sort_index(ascending=False)
            st.dataframe(tabela_circ, use_container_width=True, hide_index=True)
    else:
        st.info("Nenhuma coluna de circuito identificada na planilha.")

with aba4:
    st.subheader("Registro detalhado de leituras")
    tabela_hist = filtrado[
        [
            "data_str", "kw_medido", "dias_decorridos", "kw_periodo",
            "kw_dia", "tarifa_kw", "valor_gasto", "hospedes_label", "obs"
        ]
    ].sort_index(ascending=False).copy()

    tabela_hist["kw_medido"] = tabela_hist["kw_medido"].map(lambda x: numero_br(x, 0))
    tabela_hist["dias_decorridos"] = tabela_hist["dias_decorridos"].map(lambda x: numero_br(x, 0))
    tabela_hist["kw_periodo"] = tabela_hist["kw_periodo"].map(lambda x: numero_br(x, 1))
    tabela_hist["kw_dia"] = tabela_hist["kw_dia"].map(lambda x: numero_br(x, 2))
    tabela_hist["tarifa_kw"] = tabela_hist["tarifa_kw"].map(lambda x: moeda(x) if pd.notna(x) else "-")
    tabela_hist["valor_gasto"] = tabela_hist["valor_gasto"].map(moeda)

    tabela_hist.columns = [
        "Data", "Leitura (kWh)", "Dias", "Consumo (kWh)",
        "Média kWh/dia", "Tarifa", "Valor Gasto", "Ocupação", "Observações"
    ]
    st.dataframe(tabela_hist, use_container_width=True, hide_index=True)

    csv_export = filtrado.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        label="📥 Baixar dados filtrados (CSV)",
        data=csv_export,
        file_name="energia_ranchin_filtrado.csv",
        mime="text/csv",
    )
