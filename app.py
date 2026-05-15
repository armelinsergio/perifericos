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
SENHA_ADMIN_MASTER = "admin123" # Senha para funções críticas
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
    def executar_criacao():
        with conn.session as session:
            session.execute(text("CREATE TABLE IF NOT EXISTS unidades (nome TEXT PRIMARY KEY);"))
            session.execute(text("CREATE TABLE IF NOT EXISTS produtos (unidade TEXT, item TEXT, quantidade INTEGER, limite_minimo INTEGER, PRIMARY KEY (unidade, item));"))
            session.execute(text("CREATE TABLE IF NOT EXISTS historico (id SERIAL PRIMARY KEY, unidade TEXT, colaborador TEXT, item TEXT, data TEXT, tipo TEXT, chamado TEXT, quantidade INTEGER, nf TEXT);"))
            session.execute(text("CREATE TABLE IF NOT EXISTS usuarios (username TEXT PRIMARY KEY, password TEXT, perfil TEXT, unidade TEXT, primeiro_acesso BOOLEAN DEFAULT TRUE, permissao TEXT DEFAULT 'EDICAO');"))
            
            res_u = session.execute(text("SELECT count(*) FROM unidades")).fetchone()
            if res_u[0] == 0:
                for u in ["MATRIZ", "FILIAL SÃO PAULO", "FILIAL RIO DE JANEIRO"]:
                    session.execute(text("INSERT INTO unidades (nome) VALUES (:n)"), {"n": u})
            
            session.execute(text("INSERT INTO usuarios (username, password, perfil, unidade, primeiro_acesso, permissao) VALUES ('admin', '123', 'GLOBAL', 'TODAS', FALSE, 'EDICAO') ON CONFLICT (username) DO NOTHING;"))
            session.commit()

    try:
        executar_criacao()
    except Exception:
        conn.reset()
        try: executar_criacao()
        except Exception as e: st.error(f"Erro ao inicializar banco: {e}")

init_db()

def get_unidades():
    df = conn.query("SELECT nome FROM unidades ORDER BY nome ASC", ttl=0)
    return df['nome'].tolist()

# ==========================================
# 3. SISTEMA DE LOGIN
# ==========================================
if "autenticado" not in st.session_state:
    st.session_state.update({"autenticado": False, "usuario": None, "perfil": None, "unidade_acesso": None, "primeiro_acesso": False, "permissao": None})

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
                    st.session_state.update({
                        "autenticado": True, "usuario": user_input,
                        "perfil": df_user.iloc[0]["perfil"],
                        "unidade_acesso": df_user.iloc[0]["unidade"],
                        "primeiro_acesso": df_user.iloc[0]["primeiro_acesso"],
                        "permissao": df_user.iloc[0]["permissao"] if pd.notna(df_user.iloc[0]["permissao"]) else "EDICAO"
                    })
                    st.rerun()
                else: st.error("❌ Acesso negado")
    st.stop()

if st.session_state["primeiro_acesso"]:
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        st.warning("🔒 Altere sua senha.")
        with st.form("form_pwd"):
            p1 = st.text_input("Nova Senha", type="password")
            p2 = st.text_input("Confirme Senha", type="password")
            if st.form_submit_button("Atualizar"):
                if p1 == p2 and p1:
                    with conn.session as s:
                        s.execute(text("UPDATE usuarios SET password = :p, primeiro_acesso = FALSE WHERE username = :u"), {"p": p1, "u": st.session_state["usuario"]})
                        s.commit()
                    st.session_state["primeiro_acesso"] = False
                    st.success("Sucesso!"); time.sleep(1); st.rerun()
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
    unidades_permitidas = UNIDADES_LISTA
else:
    unidades_permitidas = st.session_state["unidade_acesso"].split(",")

unidade_atual = st.sidebar.selectbox("🏢 Unidade Ativa", unidades_permitidas)

menu_disponivel = ["📊 Dashboard", "📜 Histórico"]
if st.session_state["permissao"] == "EDICAO" or st.session_state["perfil"] == "GLOBAL":
    menu_disponivel = ["📊 Dashboard", "📤 Saída", "📥 Entrada", "⚙️ Gestão", "📜 Histórico"]

st.sidebar.divider()
choice = st.sidebar.selectbox("Menu", menu_disponivel)

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

    df_u = conn.query("SELECT item, quantidade, limite_minimo FROM produtos WHERE unidade = :u ORDER BY item ASC", params={"u": unidade_atual}, ttl=0)
    if df_u.empty: st.info("Nenhum item cadastrado.")
    else: st.dataframe(df_u, use_container_width=True)

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
                    st.success("Estoque!"); time.sleep(0.5); st.rerun()
                else: st.error("NF obrigatória.")

elif choice == "⚙️ Gestão":
    st.header("Gestão do Sistema")
    tab_list = ["📦 Itens"]
    if st.session_state["perfil"] == "GLOBAL":
        tab_list += ["🧹 Limpeza", "👥 Usuários", "🏢 Unidades"]
    tabs = st.tabs(tab_list)
    
    with tabs[0]: # ITENS
        st.subheader("Novo Item")
        with st.form("new_item"):
            ni, nq, nm = st.text_input("Nome").upper(), st.number_input("Qtd", min_value=0), st.number_input("Min", min_value=1, value=5)
            if st.form_submit_button("Cadastrar"):
                if ni:
                    try:
                        with conn.session as s:
                            s.execute(text("INSERT INTO produtos (unidade, item, quantidade, limite_minimo) VALUES (:u, :i, :q, :m)"), {"u": unidade_atual, "i": ni, "q": nq, "m": nm})
                            s.commit(); st.success("Ok!"); st.rerun()
                    except: st.error("Já existe.")
        st.divider()
        df_geral = conn.query("SELECT item, quantidade, limite_minimo FROM produtos WHERE unidade = :u ORDER BY item ASC", params={"u": unidade_atual}, ttl=0)
        if not df_geral.empty:
            it_edit = st.selectbox("Editar/Remover:", df_geral['item'].tolist())
            linha = df_geral[df_geral['item'] == it_edit].iloc[0]
            c1, c2 = st.columns(2)
            with c1:
                nq2, nm2 = st.number_input("Qtd", value=int(linha['quantidade'])), st.number_input("Mín", value=int(linha['limite_minimo']))
                if st.button("Salvar Ajuste"):
                    with conn.session as s:
                        s.execute(text("UPDATE produtos SET quantidade = :q, limite_minimo = :m WHERE unidade = :u AND item = :it"), {"q": nq2, "m": nm2, "u": unidade_atual, "it": it_edit})
                        s.commit(); st.success("Salvo!"); st.rerun()
            with c2:
                st.write("Ações Críticas")
                if st.checkbox("Confirmar exclusão definitiva"):
                    if st.button("🗑️ Remover Item", type="primary"):
                        with conn.session as s:
                            s.execute(text("DELETE FROM produtos WHERE unidade = :u AND item = :it"), {"u": unidade_atual, "it": it_edit})
                            s.commit(); st.success("Removido!"); st.rerun()

    if st.session_state["perfil"] == "GLOBAL":
        with tabs[1]: # LIMPEZA
            st.subheader("Reset")
            pw = st.text_input("Senha Master", type="password")
            if pw == SENHA_ADMIN_MASTER:
                if st.button("🚨 LIMPAR TUDO DESTA UNIDADE"):
                    with conn.session as s:
                        s.execute(text("DELETE FROM historico WHERE unidade = :u"), {"u": unidade_atual})
                        s.execute(text("DELETE FROM produtos WHERE unidade = :u"), {"u": unidade_atual})
                        s.commit(); st.success("Resetado!"); st.rerun()

        with tabs[2]: # USUÁRIOS
            st.subheader("Novo Usuário")
            with st.form("create_user"):
                nu, ns = st.text_input("Login").lower().strip(), st.text_input("Senha")
                c_perf, c_perm = st.columns(2)
                with c_perf: np = st.selectbox("Perfil", ["LOCAL", "GLOBAL"])
                with c_perm: n_perm = st.selectbox("Permissão", ["EDICAO", "LEITURA"])
                u_sel = st.multiselect("Unidades", UNIDADES_LISTA) if np == "LOCAL" else ["TODAS"]
                if st.form_submit_button("Criar"):
                    if nu and ns and (u_sel or np=="GLOBAL"):
                        try:
                            with conn.session as s:
                                s.execute(text("INSERT INTO usuarios (username, password, perfil, unidade, primeiro_acesso, permissao) VALUES (:u, :p, :perf, :un, TRUE, :perm)"),
                                          {"u": nu, "p": ns, "perf": np, "un": ",".join(u_sel), "perm": n_perm})
                                s.commit(); st.success("Criado!"); st.rerun()
                        except: st.error("Login já existe.")
            
            st.divider()
            st.subheader("Editar / Gerenciar Usuários")
            df_users = conn.query("SELECT * FROM usuarios WHERE username != 'admin'", ttl=0)
            if not df_users.empty:
                col_u = st.selectbox("Selecione Colaborador:", df_users['username'].tolist())
                dados_u = df_users[df_users['username'] == col_u].iloc[0]
                
                with st.expander(f"✏️ Editar: {col_u}", expanded=True):
                    c1, c2 = st.columns(2)
                    with c1:
                        # Edição de Unidades e Permissão
                        cur_units = dados_u['unidade'].split(",") if dados_u['perfil'] == "LOCAL" else []
                        nova_unid = st.multiselect("Unidades de Acesso:", UNIDADES_LISTA, default=[u for u in cur_units if u in UNIDADES_LISTA]) if dados_u['perfil'] == "LOCAL" else ["TODAS"]
                        nova_perm = st.selectbox("Nível de Acesso:", ["EDICAO", "LEITURA"], index=0 if dados_u['permissao'] == "EDICAO" else 1)
                        if st.button("Atualizar Acessos"):
                            with conn.session as s:
                                s.execute(text("UPDATE usuarios SET unidade = :un, permissao = :perm WHERE username = :u"), {"un": ",".join(nova_unid), "perm": nova_perm, "u": col_u})
                                s.commit(); st.success("Atualizado!"); time.sleep(0.5); st.rerun()
                    with c2:
                        # Login e Senha
                        novo_login = st.text_input("Mudar Login:", placeholder=col_u).lower().strip()
                        if st.button("Mudar Login"):
                            if novo_login:
                                with conn.session as s:
                                    s.execute(text("UPDATE usuarios SET username = :n WHERE username = :o"), {"n": novo_login, "o": col_u})
                                    s.commit(); st.success("Login mudou!"); st.rerun()
                        if st.button("Resetar Senha (1234)"):
                            with conn.session as s:
                                s.execute(text("UPDATE usuarios SET password = '1234', primeiro_acesso = TRUE WHERE username = :u"), {"u": col_u})
                                s.commit(); st.warning("Senha agora é 1234."); st.rerun()
                
                if st.checkbox(f"Deletar usuário {col_u}"):
                    if st.button("Confirmar Exclusão", type="primary"):
                        with conn.session as s:
                            s.execute(text("DELETE FROM usuarios WHERE username = :u"), {"u": col_u})
                            s.commit(); st.success("Deletado!"); st.rerun()

        with tabs[3]: # UNIDADES
            st.subheader("Configurar Filiais")
            with st.form("add_u"):
                nu_nome = st.text_input("Nova Filial").upper().strip()
                if st.form_submit_button("Adicionar"):
                    if nu_nome:
                        with conn.session as s:
                            s.execute(text("INSERT INTO unidades (nome) VALUES (:n) ON CONFLICT DO NOTHING"), {"n": nu_nome})
                            s.commit(); st.success("Adicionada!"); st.rerun()
            st.divider()
            u_v = st.selectbox("Renomear:", UNIDADES_LISTA)
            u_n = st.text_input("Novo Nome:").upper().strip()
            if st.button("Alterar Nome"):
                if u_n and u_n != u_v:
                    with conn.session as s:
                        s.execute(text("INSERT INTO unidades (nome) VALUES (:n)"), {"n": u_n})
                        s.execute(text("UPDATE produtos SET unidade = :n WHERE unidade = :o"), {"n": u_n, "o": u_v})
                        s.execute(text("UPDATE historico SET unidade = :n WHERE unidade = :o"), {"n": u_n, "o": u_v})
                        s.execute(text("DELETE FROM unidades WHERE nome = :o"), {"o": u_v})
                        s.commit(); st.success("Pronto!"); st.rerun()

elif choice == "📜 Histórico":
    st.header("Movimentações")
    df_h = conn.query("SELECT colaborador, item, quantidade, tipo, chamado, data FROM historico WHERE unidade = :u ORDER BY id DESC", params={"u": unidade_atual}, ttl=0)
    st.dataframe(df_h, use_container_width=True)
