import streamlit as st
import pandas as pd
import psycopg2
from datetime import datetime
import io
from PIL import Image
import time

# --- CONFIGURAÇÕES INICIAIS ---
UNIDADES = ["MATRIZ", "BELO HORIZONTE", "JOINVILLE", "RIO DE JANEIRO"]
SENHA_ADMIN = "admin123"

st.set_page_config(page_title="Controle de Estoque TOTVS", layout="wide", initial_sidebar_state="expanded")

# --- ESTILIZAÇÃO CSS ---
st.markdown("""
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    [data-testid="stAppDeployButton"] {display: none;}
    [data-testid="stToolbar"] {visibility: hidden;}
    [data-testid="stDecoration"] {display: none;}
    [data-testid="collapsedControl"] {visibility: visible !important; display: flex !important;}
    </style>
""", unsafe_allow_html=True)

# --- CONEXÃO OTIMIZADA (CACHE) ---
@st.cache_resource
def get_connection():
    # Mantém a conexão aberta para evitar lentidão
    return psycopg2.connect(st.secrets["PG_URL"])

def init_db():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS produtos (
            unidade TEXT, item TEXT, quantidade INTEGER, limite_minimo INTEGER,
            PRIMARY KEY (unidade, item)
        );
        CREATE TABLE IF NOT EXISTS historico (
            id SERIAL PRIMARY KEY, unidade TEXT, colaborador TEXT, item TEXT,
            data TEXT, tipo TEXT, chamado TEXT, quantidade INTEGER
        );
    """)
    conn.commit()
    cur.close()

init_db()

# --- FUNÇÕES DE APOIO ---
def to_excel(df):
    output = io.BytesIO()
    writer = pd.ExcelWriter(output, engine='xlsxwriter')
    df.to_excel(writer, index=False, sheet_name='Histórico')
    writer.close()
    return output.getvalue()

# --- LOGO CENTRALIZADO ---
col_esq, col_centro, col_dir = st.columns([2, 1, 2])
with col_centro:
    try:
        logo = Image.open("logo_totvs_2025_white.png")
        st.image(logo, use_container_width=True)
    except:
        st.warning("⚠️ Logo não carregado.")

# --- BARRA LATERAL ---
st.sidebar.title("🏢 Unidade")
unidade_atual = st.sidebar.selectbox("Selecione", UNIDADES)
st.sidebar.divider()
menu = ["📊 Dashboard", "📤 Saída", "📥 Entrada", "⚙️ Gestão", "📜 Histórico"]
choice = st.sidebar.selectbox("Menu Principal", menu)

# --- LÓGICA DAS TELAS ---

if choice == "📊 Dashboard":
    st.header(f"Painel de Controle - {unidade_atual}")
    conn = get_connection()
    df_u = pd.read_sql(f"SELECT item, quantidade, limite_minimo FROM produtos WHERE unidade = '{unidade_atual}' ORDER BY item ASC", conn)

    if df_u.empty:
        st.info("Nenhum item cadastrado.")
    else:
        df_zerado = df_u[df_u['quantidade'] <= 0]
        if not df_zerado.empty:
            st.error("### 🔴 ESTOQUE ZERADO")
            st.dataframe(df_zerado, use_container_width=True)
        
        df_limite = df_u[(df_u['quantidade'] > 0) & (df_u['quantidade'] <= df_u['limite_minimo'])]
        if not df_limite.empty:
            st.warning("### 🟡 LIMITE MÍNIMO ATINGIDO")
            st.dataframe(df_limite, use_container_width=True)

        df_ok = df_u[df_u['quantidade'] > df_u['limite_minimo']]
        if not df_ok.empty:
            st.success("### 🟢 ESTOQUE SAUDÁVEL")
            st.dataframe(df_ok, use_container_width=True)

elif choice == "📤 Saída":
    st.header(f"Registrar Entrega - {unidade_atual}")
    conn = get_connection()
    df_itens = pd.read_sql(f"SELECT item, quantidade FROM produtos WHERE unidade = '{unidade_atual}' ORDER BY item ASC", conn)
    
    c1, c2 = st.columns(2)
    with c1:
        user = st.text_input("Colaborador").upper()
        cham = st.text_input("Número do Chamado").upper()
    with c2:
        if not df_itens.empty:
            it_sel = st.selectbox("Selecione o Produto", df_itens['item'].tolist())
            q_sai = st.number_input("Quantidade", min_value=1, step=1)
            
            if st.button("Confirmar Baixa"):
                if user and cham:
                    saldo = df_itens.loc[df_itens['item'] == it_sel, 'quantidade'].values[0]
                    if saldo >= q_sai:
                        cur = conn.cursor()
                        cur.execute("UPDATE produtos SET quantidade = quantidade - %s WHERE unidade = %s AND item = %s", (q_sai, unidade_atual, it_sel))
                        cur.execute("INSERT INTO historico (unidade, colaborador, item, data, tipo, chamado, quantidade) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                                    (unidade_atual, user, it_sel, datetime.now().strftime("%d/%m/%Y %H:%M"), "SAÍDA", cham, q_sai))
                        conn.commit()
                        cur.close()
                        st.toast(f"✅ Saída registrada: {q_sai}x {it_sel}", icon="✅")
                        time.sleep(1) # Pequena pausa para o usuário ver o processamento
                        st.rerun()
                    else: st.error("Estoque insuficiente.")
                else: st.error("Preencha todos os campos.")

elif choice == "📥 Entrada":
    st.header(f"Entrada de Material - {unidade_atual}")
    conn = get_connection()
    df_itens = pd.read_sql(f"SELECT item FROM produtos WHERE unidade = '{unidade_atual}' ORDER BY item ASC", conn)
    
    if not df_itens.empty:
        it_ent = st.selectbox("Produto", df_itens['item'].tolist())
        q_ent = st.number_input("Qtd Recebida", min_value=1, step=1)
        if st.button("Adicionar ao Estoque"):
            cur = conn.cursor()
            cur.execute("UPDATE produtos SET quantidade = quantidade + %s WHERE unidade = %s AND item = %s", (q_ent, unidade_atual, it_ent))
            cur.execute("INSERT INTO historico (unidade, colaborador, item, data, tipo, chamado, quantidade) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                        (unidade_atual, "SISTEMA", it_ent, datetime.now().strftime("%d/%m/%Y %H:%M"), "ENTRADA", "REPOSIÇÃO", q_ent))
            conn.commit()
            cur.close()
            st.toast(f"📥 Estoque de {it_ent} atualizado!", icon="📥")
            time.sleep(1)
            st.rerun()

elif choice == "⚙️ Gestão":
    st.header(f"Gerenciamento - {unidade_atual}")
    t1, t2, t3, t4, t5, t6 = st.tabs(["🆕 Novo", "✏️ Ajustar", "📝 Renomear", "🗑️ Remover", "🧹 Histórico", "🚀 Reset"])
    conn = get_connection()
    
    with t1:
        n_it = st.text_input("Nome do Periférico").upper()
        n_q = st.number_input("Qtd Inicial", min_value=0)
        n_m = st.number_input("Limite Mínimo", min_value=1, value=5)
        if st.button("Salvar Cadastro"):
            if n_it:
                try:
                    cur = conn.cursor()
                    cur.execute("INSERT INTO produtos (unidade, item, quantidade, limite_minimo) VALUES (%s, %s, %s, %s)", (unidade_atual, n_it, n_q, n_m))
                    cur.execute("INSERT INTO historico (unidade, colaborador, item, data, tipo, chamado, quantidade) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                                (unidade_atual, "SISTEMA", n_it, datetime.now().strftime("%d/%m/%Y %H:%M"), "CADASTRO", "N/A", n_q))
                    conn.commit()
                    cur.close()
                    st.toast(f"✨ {n_it} cadastrado com sucesso!", icon="✨")
                    time.sleep(1)
                    st.rerun()
                except Exception as e:
                    st.error("Este item já existe.")
                    conn.rollback()

    with t2:
        df_itens = pd.read_sql(f"SELECT item, quantidade, limite_minimo FROM produtos WHERE unidade = '{unidade_atual}' ORDER BY item ASC", conn)
        if not df_itens.empty:
            it_edit = st.selectbox("Editar configurações de:", df_itens['item'].tolist())
            linha = df_itens[df_itens['item'] == it_edit].iloc[0]
            nova_q = st.number_input("Nova Quantidade", value=int(linha['quantidade']))
            novo_m = st.number_input("Novo Limite Mínimo", value=int(linha['limite_minimo']))
            if st.button("Salvar Ajustes"):
                cur = conn.cursor()
                cur.execute("UPDATE produtos SET quantidade = %s, limite_minimo = %s WHERE unidade = %s AND item = %s", (nova_q, novo_m, unidade_atual, it_edit))
                conn.commit()
                cur.close()
                st.toast("💾 Ajustes salvos!", icon="💾")
                time.sleep(1)
                st.rerun()

    with t3:
        df_ren = pd.read_sql(f"SELECT item FROM produtos WHERE unidade = '{unidade_atual}' ORDER BY item ASC", conn)
        if not df_ren.empty:
            it_ren = st.selectbox("Item para renomear:", df_ren['item'].tolist())
            novo_nome = st.text_input("Novo Nome").upper()
            if st.button("Confirmar Renomeação"):
                if novo_nome:
                    cur = conn.cursor()
                    cur.execute("UPDATE produtos SET item = %s WHERE unidade = %s AND item = %s", (novo_nome, unidade_atual, it_ren))
                    cur.execute("UPDATE historico SET item = %s WHERE unidade = %s AND item = %s", (novo_nome, unidade_atual, it_ren))
                    conn.commit()
                    cur.close()
                    st.toast("📝 Nome atualizado!", icon="📝")
                    time.sleep(1)
                    st.rerun()

    with t4:
        df_rem = pd.read_sql(f"SELECT item FROM produtos WHERE unidade = '{unidade_atual}' ORDER BY item ASC", conn)
        if not df_rem.empty:
            it_rem = st.selectbox("Escolha o item para remover", df_rem['item'].tolist())
            if st.checkbox(f"Confirmo a remoção de {it_rem}"):
                if st.button("Remover Agora"):
                    cur = conn.cursor()
                    cur.execute("DELETE FROM produtos WHERE unidade = %s AND item = %s", (unidade_atual, it_rem))
                    conn.commit()
                    cur.close()
                    st.toast("🗑️ Item removido!", icon="🗑️")
                    time.sleep(1)
                    st.rerun()

    with t5:
        senha_h = st.text_input("Senha Admin (Histórico)", type="password")
        if senha_h == SENHA_ADMIN:
            if st.button("Apagar Histórico da Unidade"):
                cur = conn.cursor()
                cur.execute("DELETE FROM historico WHERE unidade = %s", (unidade_atual,))
                conn.commit()
                cur.close()
                st.toast("🧹 Histórico zerado!", icon="🧹")
                time.sleep(1)
                st.rerun()

    with t6:
        st.error("⚠️ RESET TOTAL")
        senha_r = st.text_input("Senha Admin (Reset)", type="password")
        if senha_r == SENHA_ADMIN:
            if st.text_input("Digite CONFIRMAR:").upper() == "CONFIRMAR":
                if st.button("ZERAR CATÁLOGO"):
                    cur = conn.cursor()
                    cur.execute("DELETE FROM produtos WHERE unidade = %s", (unidade_atual,))
                    conn.commit()
                    cur.close()
                    st.toast("🚀 Catálogo resetado!", icon="🚀")
                    time.sleep(1)
                    st.rerun()

elif choice == "📜 Histórico":
    st.header(f"Histórico - {unidade_atual}")
    conn = get_connection()
    df_h = pd.read_sql(f"SELECT colaborador, item, quantidade, data, tipo, chamado FROM historico WHERE unidade = '{unidade_atual}' ORDER BY id DESC", conn)
    
    if not df_h.empty:
        st.dataframe(df_h, use_container_width=True)
        st.download_button("📥 Baixar Excel", to_excel(df_h), f"hist_{unidade_atual}.xlsx")
    else:
        st.info("Nenhuma movimentação.")
