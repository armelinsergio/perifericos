import streamlit as st
import pandas as pd
from datetime import datetime
import io
from PIL import Image
import time

# --- CONFIGURAÇÕES INICIAIS ---
UNIDADES = ["MATRIZ", "RIO DE JANEIRO", "JOINVILLE", "BELO HORIZONTE"]
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

# --- CONEXÃO NATIVA (POOL DE CONEXÕES) ---
# O st.connection gerencia automaticamente a abertura/fechamento e o "heartbeat"
conn = st.connection("postgresql", type="sql", url=st.secrets["PG_URL"])

def init_db():
    # Usamos o .session para garantir que o comando seja executado e fechado
    with conn.session as session:
        session.execute("""
            CREATE TABLE IF NOT EXISTS produtos (
                unidade TEXT, item TEXT, quantidade INTEGER, limite_minimo INTEGER,
                PRIMARY KEY (unidade, item)
            );
        """)
        session.execute("""
            CREATE TABLE IF NOT EXISTS historico (
                id SERIAL PRIMARY KEY, unidade TEXT, colaborador TEXT, item TEXT,
                data TEXT, tipo TEXT, chamado TEXT, quantidade INTEGER, nf TEXT
            );
        """)
        session.commit()

init_db()

# --- FUNÇÕES DE APOIO ---
def to_excel(df):
    output = io.BytesIO()
    writer = pd.ExcelWriter(output, engine='xlsxwriter')
    df.to_excel(writer, index=False, sheet_name='Histórico')
    writer.close()
    return output.getvalue()

# --- LOGO ---
col_esq, col_centro, col_dir = st.columns([2, 1, 2])
with col_centro:
    try:
        logo = Image.open("logo_totvs_2025_white.png")
        st.image(logo, use_container_width=True)
    except:
        st.warning("⚠️ Logo não carregado.")

# --- MENU ---
st.sidebar.title("🏢 Unidade")
unidade_atual = st.sidebar.selectbox("Selecione", UNIDADES)
st.sidebar.divider()
menu = ["📊 Dashboard", "📤 Saída", "📥 Entrada", "⚙️ Gestão", "📜 Histórico"]
choice = st.sidebar.selectbox("Menu Principal", menu)

# --- TELAS ---

if choice == "📊 Dashboard":
    st.header(f"Painel de Controle - {unidade_atual}")
    # O query() do st.connection já usa cache automático por 10 minutos (TTL)
    # se você quiser que ele seja instantâneo, use ttl=0
    df_u = conn.query(f"SELECT item, quantidade, limite_minimo FROM produtos WHERE unidade = :unid ORDER BY item ASC", 
                      params={"unid": unidade_atual}, ttl=0)

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
    df_itens = conn.query(f"SELECT item, quantidade FROM produtos WHERE unidade = :unid ORDER BY item ASC", 
                          params={"unid": unidade_atual}, ttl=0)
    
    c1, col2 = st.columns(2)
    with c1:
        user = st.text_input("Colaborador").upper()
        cham = st.text_input("Número do Chamado").upper()
    with col2:
        if not df_itens.empty:
            it_sel = st.selectbox("Selecione o Produto", df_itens['item'].tolist())
            q_sai = st.number_input("Quantidade", min_value=1, step=1)
            
            if st.button("Confirmar Baixa"):
                if user and cham:
                    saldo = df_itens.loc[df_itens['item'] == it_sel, 'quantidade'].values[0]
                    if saldo >= q_sai:
                        with conn.session as s:
                            s.execute("UPDATE produtos SET quantidade = quantidade - :q WHERE unidade = :unid AND item = :it", 
                                      {"q": q_sai, "unid": unidade_atual, "it": it_sel})
                            s.execute("INSERT INTO historico (unidade, colaborador, item, data, tipo, chamado, quantidade, nf) VALUES (:unid, :user, :it, :dt, 'SAÍDA', :ch, :q, 'N/A')",
                                      {"unid": unidade_atual, "user": user, "it": it_sel, "dt": datetime.now().strftime("%d/%m/%Y %H:%M"), "ch": cham, "q": q_sai})
                            s.commit()
                        st.toast(f"✅ Saída registrada!", icon="✅")
                        time.sleep(0.5)
                        st.rerun()
                    else: st.error("Estoque insuficiente.")
                else: st.error("Preencha todos os campos.")
        else: st.warning("Nenhum item cadastrado.")

elif choice == "📥 Entrada":
    st.header(f"Entrada de Material (Reposição) - {unidade_atual}")
    df_itens = conn.query(f"SELECT item FROM produtos WHERE unidade = :unid ORDER BY item ASC", 
                          params={"unid": unidade_atual}, ttl=0)
    
    c1, c2 = st.columns(2)
    with c1:
        if not df_itens.empty:
            it_ent = st.selectbox("Produto", df_itens['item'].tolist())
            q_ent = st.number_input("Qtd Recebida", min_value=1, step=1)
    with c2:
        nf_ent = st.text_input("Número da NF").upper()
            
    if st.button("Confirmar Entrada"):
        if not nf_ent:
            st.error("Obrigatório informar o número da NF.")
        else:
            with conn.session as s:
                s.execute("UPDATE produtos SET quantidade = quantidade + :q WHERE unidade = :unid AND item = :it", 
                          {"q": q_ent, "unid": unidade_atual, "it": it_ent})
                s.execute("INSERT INTO historico (unidade, colaborador, item, data, tipo, chamado, quantidade, nf) VALUES (:unid, 'SISTEMA', :it, :dt, 'ENTRADA', 'REPOSIÇÃO', :q, :nf)",
                          {"unid": unidade_atual, "it": it_ent, "dt": datetime.now().strftime("%d/%m/%Y %H:%M"), "q": q_ent, "nf": nf_ent})
                s.commit()
            st.toast(f"📥 Estoque atualizado!", icon="📥")
            time.sleep(0.5)
            st.rerun()

elif choice == "⚙️ Gestão":
    st.header(f"Gerenciamento - {unidade_atual}")
    t1, t2, t3, t4, t5, t6 = st.tabs(["🆕 Novo", "✏️ Ajustar", "📝 Renomear", "🗑️ Remover", "🧹 Histórico", "🚀 Reset"])
    
    with t1:
        n_it = st.text_input("Nome do Periférico").upper()
        n_q = st.number_input("Qtd Inicial", min_value=0)
        n_m = st.number_input("Limite Mínimo", min_value=1, value=5)
        n_nf = st.text_input("NF (Opcional)").upper()
        if st.button("Salvar Cadastro"):
            if n_it:
                try:
                    with conn.session as s:
                        s.execute("INSERT INTO produtos (unidade, item, quantidade, limite_minimo) VALUES (:unid, :it, :q, :m)", 
                                  {"unid": unidade_atual, "it": n_it, "q": n_q, "m": n_m})
                        s.execute("INSERT INTO historico (unidade, colaborador, item, data, tipo, chamado, quantidade, nf) VALUES (:unid, 'SISTEMA', :it, :dt, 'CADASTRO', 'N/A', :q, :nf)",
                                  {"unid": unidade_atual, "it": n_it, "dt": datetime.now().strftime("%d/%m/%Y %H:%M"), "q": n_q, "nf": n_nf if n_nf else "N/A"})
                        s.commit()
                    st.toast("✨ Item cadastrado!", icon="✨")
                    time.sleep(0.5)
                    st.rerun()
                except:
                    st.error("Erro: Item já existe ou problema no banco.")

    with t2:
        df_itens = conn.query(f"SELECT item, quantidade, limite_minimo FROM produtos WHERE unidade = :unid ORDER BY item ASC", 
                              params={"unid": unidade_atual}, ttl=0)
        if not df_itens.empty:
            it_edit = st.selectbox("Editar:", df_itens['item'].tolist())
            linha = df_itens[df_itens['item'] == it_edit].iloc[0]
            nq = st.number_input("Nova Qtd", value=int(linha['quantidade']))
            nm = st.number_input("Novo Mínimo", value=int(linha['limite_minimo']))
            if st.button("Salvar Ajustes"):
                with conn.session as s:
                    s.execute("UPDATE produtos SET quantidade = :q, limite_minimo = :m WHERE unidade = :unid AND item = :it", 
                              {"q": nq, "m": nm, "unid": unidade_atual, "it": it_edit})
                    s.commit()
                st.toast("💾 Salvo!")
                time.sleep(0.5)
                st.rerun()

elif choice == "📜 Histórico":
    st.header(f"Histórico - {unidade_atual}")
    df_h = conn.query(f"SELECT colaborador, item, quantidade, nf, data, tipo, chamado FROM historico WHERE unidade = :unid ORDER BY id DESC", 
                      params={"unid": unidade_atual}, ttl=0)
    
    if not df_h.empty:
        st.dataframe(df_h, use_container_width=True)
        st.download_button("📥 Excel", to_excel(df_h), f"hist_{unidade_atual}.xlsx")
    else:
        st.info("Nenhuma movimentação.")
