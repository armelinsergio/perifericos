import streamlit as st
import pandas as pd
from datetime import datetime
import io
from PIL import Image
import time
from sqlalchemy import text
import pytz

# ==========================================
# 1. CONFIGURAÇÕES INICIAIS
# ==========================================
SENHA_ADMIN_MASTER = "admin123" # Senha para funções críticas (Reset de Catálogo)
fuso_br = pytz.timezone('America/Sao_Paulo')

st.set_page_config(page_title="Controle de Estoque TOTVS", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 2. BANCO DE DADOS E TABELAS
# ==========================================
conn = st.connection("postgresql", type="sql", url=st.secrets["PG_URL"])

@st.cache_resource
def init_db():
    try:
        with conn.session as session:
            # Tabela de Unidades
            session.execute(text("""
                CREATE TABLE IF NOT EXISTS unidades (
                    nome TEXT PRIMARY KEY
                );
            """))
            # Tabela de Produtos
            session.execute(text("""
                CREATE TABLE IF NOT EXISTS produtos (
                    unidade TEXT, item TEXT, quantidade INTEGER, limite_minimo INTEGER,
                    PRIMARY KEY (unidade, item)
                );
            """))
            # Tabela de Histórico
            session.execute(text("""
                CREATE TABLE IF NOT EXISTS historico (
                    id SERIAL PRIMARY KEY, unidade TEXT, colaborador TEXT, item TEXT,
                    data TEXT, tipo TEXT, chamado TEXT, quantidade INTEGER, nf TEXT
                );
            """))
            # Tabela de Usuários
            session.execute(text("""
                CREATE TABLE IF NOT EXISTS usuarios (
                    username TEXT PRIMARY KEY,
                    password TEXT,
                    perfil TEXT,
                    unidade TEXT,
                    primeiro_acesso BOOLEAN DEFAULT TRUE
                );
            """))
            
            # Popula unidades iniciais se estiver vazio
            res_u = session.execute(text("SELECT count(*) FROM unidades")).fetchone()
            if res_u[0] == 0:
                for u in ["MATRIZ", "FILIAL SÃO PAULO", "FILIAL RIO DE JANEIRO"]:
                    session.execute(text("INSERT INTO unidades (nome) VALUES (:n)"), {"n": u})
            
            # Cria Admin padrão
            session.execute(text("""
                INSERT INTO usuarios (username, password, perfil, unidade, primeiro_acesso) 
                VALUES ('admin', '123', 'GLOBAL', 'TODAS', FALSE) 
                ON CONFLICT (username) DO NOTHING;
            """))
            session.commit()
    except Exception as e:
        st.error(f"Erro ao inicializar banco: {e}")

init_db()

def get_unidades():
    df = conn.query("SELECT nome FROM unidades ORDER BY nome ASC", ttl=0)
    return df['nome'].tolist()

# ==========================================
# 3. SISTEMA DE LOGIN
# ==========================================
if "autenticado" not in st.session_state:
    st.session_state["autenticado"] = False
    st.session_state["usuario"] = None
    st.session_state["perfil"] = None
    st.session_state["unidade_acesso"] = None
    st.session_state["primeiro_acesso"] = False

if not st.session_state["autenticado"]:
    st.markdown("<br><br>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        try: st.image(Image.open("logo_totvs_2025_white.png"), use_container_width=True)
        except: st.markdown("<h2 style='text-align: center;'>TOTVS</h2>", unsafe_allow_html=True)
        
        with st.form("login_form"):
            st.markdown("<h3 style='text-align: center;'>🔐 Login</h3>", unsafe_allow_html=True)
            user_input = st.text_input("Usuário").lower().strip()
            pass_input = st.text_input("Senha", type="password")
            if st.form_submit_button("Entrar", use_container_width=True):
                df_user = conn.query("SELECT * FROM usuarios WHERE username = :u", params={"u": user_input}, ttl=0)
                if not df_user.empty and df_user.iloc[0]["password"] == pass_input:
                    st.session_state["autenticado"] = True
                    st.session_state["usuario"] = user_input
                    st.session_state["perfil"] = df_user.iloc[0]["perfil"]
                    st.session_state["unidade_acesso"] = df_user.iloc[0]["unidade"]
                    st.session_state["primeiro_acesso"] = df_user.iloc[0]["primeiro_acesso"]
                    st.rerun()
                else: st.error("❌ Acesso negado")
    st.stop()

if st.session_state["primeiro_acesso"]:
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        st.warning("🔒 Primeiro acesso: Altere sua senha.")
        with st.form("form_pwd"):
            p1 = st.text_input("Nova Senha", type="password")
            p2 = st.text_input("Confirme Senha", type="password")
            if st.form_submit_button("Atualizar"):
                if p1 == p2 and p1:
                    with conn.session as s:
                        s.execute(text("UPDATE usuarios SET password = :p, primeiro_acesso = FALSE WHERE username = :u"), {"p": p1, "u": st.session_state["usuario"]})
                        s.commit()
                    st.session_state["primeiro_acesso"] = False
                    st.success("Sucesso!")
                    time.sleep(1); st.rerun()
                else: st.error("Senhas não conferem.")
    st.stop()

# ==========================================
# 4. FUNÇÕES GERAIS
# ==========================================
def get_data_br(): return datetime.now(fuso_br).strftime("%d/%m/%Y %H:%M")

def gerar_excel(df, nome_aba, titulo):
    output = io.BytesIO()
    writer = pd.ExcelWriter(output, engine='xlsxwriter')
    df.to_excel(writer, index=False, sheet_name=nome_aba, startrow=3)
    workbook = writer.book
    worksheet = writer.sheets[nome_aba]
    fmt_titulo = workbook.add_format({'bold': True, 'font_size': 14, 'font_color': 'white', 'bg_color': 'black', 'align': 'center'})
    worksheet.merge_range('A1:G2', titulo, fmt_titulo)
    writer.close()
    return output.getvalue()

# ==========================================
# 5. SIDEBAR E MENU
# ==========================================
st.sidebar.write(f"👤 **{st.session_state['usuario'].upper()}**")
if st.sidebar.button("Sair"):
    st.session_state["autenticado"] = False; st.rerun()

UNIDADES_LISTA = get_unidades()

if st.session_state["perfil"] == "GLOBAL":
    unidade_atual = st.sidebar.selectbox("🏢 Unidade", UNIDADES_LISTA)
else:
    unidade_atual = st.session_state["unidade_acesso"]
    st.sidebar.info(f"📍 {unidade_atual}")

choice = st.sidebar.selectbox("Menu", ["📊 Dashboard", "📤 Saída", "📥 Entrada", "⚙️ Gestão", "📜 Histórico"])

# ==========================================
# 6. TELAS
# ==========================================

if choice == "📊 Dashboard":
    st.header(f"Painel - {unidade_atual}")
    if st.session_state["perfil"] == "GLOBAL":
        df_alertas = conn.query("SELECT unidade, item, quantidade FROM produtos WHERE quantidade <= limite_minimo", ttl=0)
        if not df_alertas.empty:
            with st.expander("🚨 ALERTAS GLOBAIS", expanded=True):
                st.dataframe(df_alertas, use_container_width=True)

    df_u = conn.query("SELECT item, quantidade, limite_minimo FROM produtos WHERE unidade = :u", params={"u": unidade_atual}, ttl=0)
    if df_u.empty: st.info("Vazio.")
    else:
        st.dataframe(df_u, use_container_width=True)

elif choice == "📤 Saída":
    st.header("Registrar Saída")
    df_p = conn.query("SELECT item, quantidade FROM produtos WHERE unidade = :u", params={"u": unidade_atual}, ttl=0)
    if df_p.empty: st.warning("Cadastre itens primeiro.")
    else:
        with st.form("saida"):
            colab = st.text_input("Colaborador").upper()
            it = st.selectbox("Item", df_p['item'].tolist())
            qtd = st.number_input("Qtd", min_value=1)
            cham = st.text_input("Chamado").upper()
            if st.form_submit_button("Confirmar"):
                estoque = df_p.loc[df_p['item']==it, 'quantidade'].values[0]
                if estoque >= qtd:
                    with conn.session as s:
                        s.execute(text("UPDATE produtos SET quantidade = quantidade - :q WHERE unidade = :un AND item = :it"), {"q": qtd, "un": unidade_atual, "it": it})
                        s.execute(text("INSERT INTO historico (unidade, colaborador, item, data, tipo, chamado, quantidade, nf) VALUES (:un, :c, :it, :d, 'SAÍDA', :ch, :q, 'N/A')"),
                                  {"un": unidade_atual, "c": colab, "it": it, "d": get_data_br(), "ch": cham, "q": qtd})
                        s.commit()
                    st.success("Registrado!"); time.sleep(0.5); st.rerun()
                else: st.error("Sem estoque!")

elif choice == "📥 Entrada":
    st.header("Entrada de Material")
    df_p = conn.query("SELECT item FROM produtos WHERE unidade = :u", params={"u": unidade_atual}, ttl=0)
    if df_p.empty: st.warning("Cadastre itens primeiro.")
    else:
        with st.form("entrada"):
            it = st.selectbox("Item", df_p['item'].tolist())
            qtd = st.number_input("Qtd", min_value=1)
            nf = st.text_input("Nota Fiscal").upper()
            if st.form_submit_button("Confirmar"):
                if nf:
                    with conn.session as s:
                        s.execute(text("UPDATE produtos SET quantidade = quantidade + :q WHERE unidade = :un AND item = :it"), {"q": qtd, "un": unidade_atual, "it": it})
                        s.execute(text("INSERT INTO historico (unidade, colaborador, item, data, tipo, chamado, quantidade, nf) VALUES (:un, 'SISTEMA', :it, :d, 'ENTRADA', 'REPOSIÇÃO', :q, :nf)"),
                                  {"un": unidade_atual, "it": it, "d": get_data_br(), "q": qtd, "nf": nf})
                        s.commit()
                    st.success("Estoque atualizado!"); time.sleep(0.5); st.rerun()
                else: st.error("NF obrigatória.")

elif choice == "⚙️ Gestão":
    st.header("Configurações do Sistema")
    
    tab_list = ["📦 Itens", "📜 Limpeza"]
    if st.session_state["perfil"] == "GLOBAL":
        tab_list += ["👥 Usuários", "🏢 Unidades"]
    
    tabs = st.tabs(tab_list)
    
    with tabs[0]: # ITENS
        st.subheader("Novo Item")
        with st.form("new_item"):
            ni = st.text_input("Nome").upper()
            nq = st.number_input("Qtd Inicial", min_value=0)
            nm = st.number_input("Mínimo", min_value=1, value=5)
            if st.form_submit_button("Cadastrar"):
                if ni:
                    try:
                        with conn.session as s:
                            s.execute(text("INSERT INTO produtos (unidade, item, quantidade, limite_minimo) VALUES (:u, :i, :q, :m)"), {"u": unidade_atual, "i": ni, "q": nq, "m": nm})
                            s.commit()
                        st.success("Cadastrado!"); st.rerun()
                    except: st.error("Já existe.")

    with tabs[1]: # LIMPEZA
        st.subheader("Reset de Dados")
        pw = st.text_input("Senha Master", type="password")
        if pw == SENHA_ADMIN_MASTER:
            if st.button("🚨 LIMPAR HISTÓRICO DESTA UNIDADE"):
                with conn.session as s:
                    s.execute(text("DELETE FROM historico WHERE unidade = :u"), {"u": unidade_atual})
                    s.commit()
                st.success("Limpo!")

    if st.session_state["perfil"] == "GLOBAL":
        with tabs[2]: # GESTÃO DE USUÁRIOS
            st.subheader("Novo Colaborador")
            with st.form("create_user"):
                nu = st.text_input("Login").lower().strip()
                ns = st.text_input("Senha Inicial")
                np = st.selectbox("Perfil", ["LOCAL", "GLOBAL"])
                nu_base = st.selectbox("Unidade", ["TODAS"] + UNIDADES_LISTA)
                if st.form_submit_button("Criar"):
                    with conn.session as s:
                        s.execute(text("INSERT INTO usuarios (username, password, perfil, unidade, primeiro_acesso) VALUES (:u, :p, :perf, :un, TRUE)"),
                                  {"u": nu, "p": ns, "perf": np, "un": nu_base})
                        s.commit()
                    st.success("Criado!"); st.rerun()
            
            st.divider()
            st.subheader("Ações em Usuários")
            df_users = conn.query("SELECT username FROM usuarios WHERE username != 'admin'", ttl=0)
            if not df_users.empty:
                col_u = st.selectbox("Selecione Usuário", df_users['username'].tolist())
                
                # Dividido em 3 colunas para acomodar a Exclusão
                c1, c2, c3 = st.columns(3)
                
                with c1:
                    st.write("**Renomear Usuário**")
                    novo_login = st.text_input("Novo Login").lower().strip()
                    if st.button("Atualizar Login"):
                        if novo_login:
                            with conn.session as s:
                                s.execute(text("UPDATE usuarios SET username = :n WHERE username = :o"), {"n": novo_login, "o": col_u})
                                s.commit()
                            st.success("Login alterado!"); st.rerun()
                
                with c2:
                    st.write("**Resetar Senha**")
                    if st.button("Gerar Senha Genérica (1234)"):
                        with conn.session as s:
                            s.execute(text("UPDATE usuarios SET password = '1234', primeiro_acesso = TRUE WHERE username = :u"), {"u": col_u})
                            s.commit()
                        st.warning(f"Senha do {col_u} agora é '1234'.")

                with c3:
                    st.write("**Remover Usuário**")
                    if st.checkbox(f"Confirmar exclusão de {col_u}"):
                        # Adicionado botão vermelho (type="primary" no Streamlit escuro fica com destaque)
                        if st.button("Deletar Usuário", type="primary"):
                            with conn.session as s:
                                s.execute(text("DELETE FROM usuarios WHERE username = :u"), {"u": col_u})
                                s.commit()
                            st.success(f"Usuário {col_u} deletado!")
                            time.sleep(1); st.rerun()

        with tabs[3]: # GESTÃO DE UNIDADES
            st.subheader("Nova Unidade")
            with st.form("add_unid"):
                nome_u = st.text_input("Nome da Nova Filial").upper().strip()
                if st.form_submit_button("Adicionar Unidade"):
                    if nome_u:
                        with conn.session as s:
                            s.execute(text("INSERT INTO unidades (nome) VALUES (:n) ON CONFLICT DO NOTHING"), {"n": nome_u})
                            s.commit()
                        st.success("Unidade adicionada!"); st.rerun()
            
            st.divider()
            st.subheader("Renomear Unidade Existente")
            st.warning("⚠️ Isso atualizará todos os itens e históricos vinculados!")
            u_velha = st.selectbox("Escolha a Unidade", UNIDADES_LISTA, key="u_velha")
            u_nova = st.text_input("Novo Nome da Unidade").upper().strip()
            if st.button("Confirmar Mudança de Nome"):
                if u_nova and u_nova != u_velha:
                    with conn.session as s:
                        s.execute(text("INSERT INTO unidades (nome) VALUES (:n)"), {"n": u_nova})
                        s.execute(text("UPDATE produtos SET unidade = :n WHERE unidade = :o"), {"n": u_nova, "o": u_velha})
                        s.execute(text("UPDATE historico SET unidade = :n WHERE unidade = :o"), {"n": u_nova, "o": u_velha})
                        s.execute(text("UPDATE usuarios SET unidade = :n WHERE unidade = :o"), {"n": u_nova, "o": u_velha})
                        s.execute(text("DELETE FROM unidades WHERE nome = :o"), {"o": u_velha})
                        s.commit()
                    st.success("Unidade renomeada e registros atualizados!"); st.rerun()

elif choice == "📜 Histórico":
    st.header("Movimentações")
    df_h = conn.query("SELECT * FROM historico WHERE unidade = :u ORDER BY id DESC", params={"u": unidade_atual}, ttl=0)
    st.dataframe(df_h, use_container_width=True)
