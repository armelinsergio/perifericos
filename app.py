import streamlit as st
import pandas as pd
from datetime import datetime
import io
from PIL import Image
import time
from sqlalchemy import text
import pytz
import uuid

# ==========================================
# 1. CONFIGURAÇÕES INICIAIS
# ==========================================
SENHA_ADMIN_MASTER = "admin123" 
fuso_br = pytz.timezone('America/Sao_Paulo')

st.set_page_config(page_title="Controle de Estoque TOTVS", layout="wide", initial_sidebar_state="expanded")

# CSS para esconder Git/Deploy e travar o menu lateral
st.markdown("""
    <style>
    footer {visibility: hidden;}
    header [data-testid="stHeaderActionElements"] {display: none !important;}
    [data-testid="stToolbar"] {display: none !important;}
    [data-testid="stSidebar"] [data-testid="stSidebarCollapseButton"] {display: none !important;}
    [data-testid="collapsedControl"] {display: flex !important; visibility: visible !important;}
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
            session.execute(text("CREATE TABLE IF NOT EXISTS usuarios (username TEXT PRIMARY KEY, password TEXT, perfil TEXT, unidade TEXT, primeiro_acesso BOOLEAN DEFAULT TRUE, permissao TEXT DEFAULT 'EDICAO', session_token TEXT);"))
            session.execute(text("CREATE TABLE IF NOT EXISTS reset_requests (username TEXT PRIMARY KEY, data_solicitacao TEXT);"))
            
            res_u = session.execute(text("SELECT count(*) FROM unidades")).fetchone()
            if res_u[0] == 0:
                for u in ["MATRIZ", "FILIAL SÃO PAULO", "FILIAL RIO DE JANEIRO"]:
                    session.execute(text("INSERT INTO unidades (nome) VALUES (:n)"), {"n": u})
            
            session.execute(text("INSERT INTO usuarios (username, password, perfil, unidade, primeiro_acesso, permissao) VALUES ('master', 'admin123', 'MASTER', 'TODAS', TRUE, 'EDICAO') ON CONFLICT (username) DO NOTHING;"))
            session.commit()

    try: executar_criacao()
    except Exception:
        conn.reset()
        try: executar_criacao()
        except Exception as e: st.error(f"Erro ao inicializar banco: {e}")

init_db()

def get_unidades():
    df = conn.query("SELECT nome FROM unidades ORDER BY nome ASC", ttl=0)
    return df['nome'].tolist()

# ==========================================
# 3. LOGIN E AUTO-LOGIN (F5)
# ==========================================
if "autenticado" not in st.session_state:
    st.session_state.update({"autenticado": False, "usuario": None, "perfil": None, "unidade_acesso": None, "primeiro_acesso": False, "permissao": None})

if not st.session_state["autenticado"] and "session" in st.query_params:
    token_url = st.query_params["session"]
    df_token = conn.query("SELECT * FROM usuarios WHERE session_token = :t", params={"t": token_url}, ttl=0)
    if not df_token.empty:
        u_info = df_token.iloc[0]
        st.session_state.update({"autenticado": True, "usuario": u_info["username"], "perfil": u_info["perfil"], "unidade_acesso": u_info["unidade"], "primeiro_acesso": u_info["primeiro_acesso"], "permissao": u_info["permissao"]})

if not st.session_state["autenticado"]:
    st.markdown("<br><br>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        try: st.image(Image.open("logo_totvs_2025_white.png"), use_container_width=True)
        except: st.markdown("<h2 style='text-align: center;'>TOTVS</h2>", unsafe_allow_html=True)
        
        t_log, t_res = st.tabs(["🔐 Acesso", "❓ Esqueci a Senha"])
        with t_log:
            with st.form("login_form"):
                u_in, p_in = st.text_input("Usuário").lower().strip(), st.text_input("Senha", type="password")
                if st.form_submit_button("Entrar", use_container_width=True):
                    df_u = conn.query("SELECT * FROM usuarios WHERE username = :u", params={"u": u_in}, ttl=0)
                    if not df_u.empty and df_u.iloc[0]["password"] == p_in:
                        tk = str(uuid.uuid4())
                        with conn.session as s:
                            s.execute(text("UPDATE usuarios SET session_token = :t WHERE username = :u"), {"t": tk, "u": u_in})
                            s.commit()
                        st.query_params["session"] = tk
                        st.session_state.update({"autenticado": True, "usuario": u_in, "perfil": df_u.iloc[0]["perfil"], "unidade_acesso": df_u.iloc[0]["unidade"], "primeiro_acesso": df_u.iloc[0]["primeiro_acesso"], "permissao": df_u.iloc[0]["permissao"]})
                        st.rerun()
                    else: st.error("❌ Acesso negado")
        with t_res:
            with st.form("reset_form"):
                ur = st.text_input("Seu Usuário?").lower().strip()
                if st.form_submit_button("Solicitar Reset"):
                    if ur:
                        with conn.session as s:
                            s.execute(text("INSERT INTO reset_requests (username, data_solicitacao) VALUES (:u, :d) ON CONFLICT DO NOTHING"), {"u": ur, "d": datetime.now(fuso_br).strftime("%d/%m/%Y %H:%M")})
                            s.commit()
                        st.success("✅ Enviado ao Admin Master!")
    st.stop()

if st.session_state["primeiro_acesso"]:
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        st.warning("🔒 Altere sua senha provisória.")
        with st.form("f_pwd"):
            p1, p2 = st.text_input("Nova Senha", type="password"), st.text_input("Repita a Senha", type="password")
            if st.form_submit_button("Salvar e Entrar"):
                if p1 == p2 and p1:
                    with conn.session as s:
                        s.execute(text("UPDATE usuarios SET password = :p, primeiro_acesso = FALSE WHERE username = :u"), {"p": p1, "u": st.session_state["usuario"]})
                        s.commit()
                    st.session_state["primeiro_acesso"] = False
                    st.success("✅ Senha atualizada!"); time.sleep(1); st.rerun()
                else: st.error("❌ Senhas não conferem.")
    st.stop()

# ==========================================
# 4. FUNÇÕES GERAIS
# ==========================================
def get_data_br(): return datetime.now(fuso_br).strftime("%d/%m/%Y %H:%M")

# ==========================================
# 5. SIDEBAR E MENU
# ==========================================
try: st.sidebar.image(Image.open("logo_totvs_2025_white.png"), use_container_width=True)
except: st.sidebar.markdown("### TOTVS STOCK")

st.sidebar.write(f"👤 **{st.session_state['usuario'].upper()}**")

if st.sidebar.button("Sair (Logout)"):
    with conn.session as s:
        s.execute(text("UPDATE usuarios SET session_token = NULL WHERE username = :u"), {"u": st.session_state["usuario"]})
        s.commit()
    st.query_params.clear()
    st.session_state["autenticado"] = False
    st.rerun()

UNIDADES_LISTA = get_unidades()
if st.session_state["perfil"] in ["MASTER", "GLOBAL"]: un_perm = UNIDADES_LISTA
else: un_perm = st.session_state["unidade_acesso"].split(",")

un_atual = st.sidebar.selectbox("🏢 Unidade", un_perm)

m_disp = ["📊 Dashboard", "📜 Histórico"]
if st.session_state["permissao"] == "EDICAO" or st.session_state["perfil"] in ["MASTER", "GLOBAL"]:
    m_disp = ["📊 Dashboard", "📤 Saída", "📥 Entrada", "⚙️ Gestão", "📜 Histórico"]

st.sidebar.divider()
choice = st.sidebar.selectbox("Menu", m_disp)

# ==========================================
# 6. TELAS
# ==========================================

if choice == "📊 Dashboard":
    df_al = conn.query("SELECT unidade, item, quantidade, limite_minimo FROM produtos WHERE quantidade <= limite_minimo ORDER BY unidade, item ASC", ttl=0)
    if not df_al.empty:
        df_m = df_al if st.session_state["perfil"] in ["MASTER", "GLOBAL"] else df_al[df_al['unidade'].isin(un_perm)]
        if not df_m.empty:
            st.error("🚨 **ALERTA: ITENS COM ESTOQUE CRÍTICO OU ZERADO**")
            st.dataframe(df_m, use_container_width=True)
            st.divider()

    st.header(f"Painel - {un_atual}")
    df_u = conn.query("SELECT item as \"Produto\", quantidade as \"Estoque\", limite_minimo as \"Mínimo\" FROM produtos WHERE unidade = :u ORDER BY item ASC", params={"u": un_atual}, ttl=0)
    if df_u.empty: st.info("Vazio.")
    else: st.dataframe(df_u, use_container_width=True)

elif choice == "📤 Saída":
    st.header("Registrar Saída")
    df_p = conn.query("SELECT item, quantidade FROM produtos WHERE unidade = :u", params={"u": un_atual}, ttl=0)
    if df_p.empty: st.warning("Cadastre itens.")
    else:
        with st.form("saida"):
            c, it = st.text_input("Colaborador").upper(), st.selectbox("Item", df_p['item'].tolist())
            q, ch = st.number_input("Qtd", min_value=1), st.text_input("Chamado").upper()
            if st.form_submit_button("Confirmar Saída"):
                est = df_p.loc[df_p['item']==it, 'quantidade'].values[0]
                if est >= q:
                    with conn.session as s:
                        s.execute(text("UPDATE produtos SET quantidade = quantidade - :q WHERE unidade = :un AND item = :it"), {"q": q, "un": un_atual, "it": it})
                        s.execute(text("INSERT INTO historico (unidade, colaborador, item, data, tipo, chamado, quantidade, nf) VALUES (:un, :c, :it, :d, 'SAÍDA', :ch, :q, 'N/A')"), {"un": un_atual, "c": c, "it": it, "d": get_data_br(), "ch": ch, "q": q})
                        s.commit()
                    st.success("✅ Registrado!"); time.sleep(1); st.rerun()
                else: st.error("❌ Estoque insuficiente!")

elif choice == "📥 Entrada":
    st.header("Entrada de Material")
    df_p = conn.query("SELECT item FROM produtos WHERE unidade = :u", params={"u": un_atual}, ttl=0)
    if df_p.empty: st.warning("Cadastre itens primeiro.")
    else:
        with st.form("entrada"):
            it, q = st.selectbox("Item", df_p['item'].tolist()), st.number_input("Qtd", min_value=1)
            nf = st.text_input("Nota Fiscal").upper()
            if st.form_submit_button("Confirmar Entrada"):
                if nf:
                    with conn.session as s:
                        s.execute(text("UPDATE produtos SET quantidade = quantidade + :q WHERE unidade = :un AND item = :it"), {"q": q, "un": un_atual, "it": it})
                        s.execute(text("INSERT INTO historico (unidade, colaborador, item, data, tipo, chamado, quantidade, nf) VALUES (:un, 'SISTEMA', :it, :d, 'ENTRADA', 'REPOSIÇÃO', :q, :nf)"), {"un": un_atual, "it": it, "d": get_data_br(), "q": q, "nf": nf})
                        s.commit()
                    st.success("✅ Estoque atualizado!"); time.sleep(1); st.rerun()
                else: st.error("❌ NF obrigatória.")

elif choice == "⚙️ Gestão":
    st.header("Gestão do Sistema")
    tab_list = ["📦 Itens"]
    if st.session_state["perfil"] == "MASTER": tab_list += ["🧹 Limpeza", "👥 Usuários", "🏢 Unidades"]
    tabs = st.tabs(tab_list)
    
    with tabs[0]: # ITENS
        st.subheader("Novo Item")
        with st.form("ni"):
            ni, nq, nm = st.text_input("Nome").upper(), st.number_input("Qtd Inicial", min_value=0), st.number_input("Min Alerta", min_value=1, value=5)
            if st.form_submit_button("Cadastrar"):
                if ni:
                    try:
                        with conn.session as s:
                            s.execute(text("INSERT INTO produtos (unidade, item, quantidade, limite_minimo) VALUES (:u, :i, :q, :m)"), {"u": un_atual, "i": ni, "q": nq, "m": nm})
                            s.commit(); st.success("✅ Item cadastrado!"); st.rerun()
                    except: st.error("❌ Já existe.")
        st.divider()
        df_edit = conn.query("SELECT * FROM produtos WHERE unidade = :u ORDER BY item ASC", params={"u": un_atual}, ttl=0)
        if not df_edit.empty:
            sel_it = st.selectbox("Editar/Remover Item:", df_edit['item'].tolist())
            dados_it = df_edit[df_edit['item'] == sel_it].iloc[0]
            c_e1, c_e2 = st.columns(2)
            with c_e1:
                nq_e = st.number_input("Nova Qtd", value=int(dados_it['quantidade']))
                nm_e = st.number_input("Novo Mínimo", value=int(dados_it['limite_minimo']))
                if st.button("Salvar Ajustes"):
                    with conn.session as s:
                        s.execute(text("UPDATE produtos SET quantidade = :q, limite_minimo = :m WHERE unidade = :u AND item = :i"), {"q": nq_e, "m": nm_e, "u": un_atual, "i": sel_it})
                        s.commit(); st.success("✅ Atualizado!"); st.rerun()
            with c_e2:
                if st.checkbox(f"Remover {sel_it}"):
                    if st.button("Confirmar Exclusão de Item", type="primary"):
                        with conn.session as s:
                            s.execute(text("DELETE FROM produtos WHERE unidade = :u AND item = :i"), {"u": un_atual, "i": sel_it})
                            s.commit(); st.success("✅ Removido!"); st.rerun()

    if st.session_state["perfil"] == "MASTER":
        with tabs[1]: # LIMPEZA
            st.subheader("Operações Críticas")
            if st.text_input("Senha Master", type="password") == SENHA_ADMIN_MASTER:
                if st.button("🚨 LIMPAR HISTÓRICO DESTA UNIDADE"):
                    with conn.session as s:
                        s.execute(text("DELETE FROM historico WHERE unidade = :u"), {"u": un_atual})
                        s.commit(); st.success("✅ Histórico Limpo!")
                if st.button("🚀 ZERAR ESTOQUE (Deletar tudo desta unidade)"):
                    with conn.session as s:
                        s.execute(text("DELETE FROM produtos WHERE unidade = :u"), {"u": un_atual})
                        s.commit(); st.success("✅ Estoque Zerado!"); st.rerun()

        with tabs[2]: # USUÁRIOS
            df_rq = conn.query("SELECT * FROM reset_requests", ttl=0)
            if not df_rq.empty:
                st.warning("⚠️ Solicitações de Senha")
                for i, r in df_rq.iterrows():
                    with st.expander(f"Reset: {r['username']}"):
                        sp = st.text_input(f"Senha para {r['username']}", key=f"r_{r['username']}")
                        if st.button("Aprovar Reset", key=f"b_{r['username']}"):
                            if sp:
                                with conn.session as s:
                                    s.execute(text("UPDATE usuarios SET password = :p, primeiro_acesso = TRUE WHERE username = :u"), {"p": sp, "u": r['username']})
                                    s.execute(text("DELETE FROM reset_requests WHERE username = :u"), {"u": r['username']})
                                    s.commit(); st.success("✅ Resetado!"); st.rerun()
            st.divider()
            st.subheader("Novo Usuário")
            with st.form("cu"):
                nu, ns = st.text_input("Login").lower().strip(), st.text_input("Senha")
                c_p, c_pe = st.columns(2)
                with c_p: np = st.selectbox("Perfil", ["LOCAL", "GLOBAL"])
                with c_pe: npe = st.selectbox("Ações", ["EDICAO", "LEITURA"])
                us = st.multiselect("Unidades", UNIDADES_LISTA) if np == "LOCAL" else ["TODAS"]
                if st.form_submit_button("Criar Usuário"):
                    try:
                        with conn.session as s:
                            s.execute(text("INSERT INTO usuarios (username, password, perfil, unidade, primeiro_acesso, permissao) VALUES (:u, :p, :perf, :un, TRUE, :perm)"), {"u": nu, "p": ns, "perf": np, "un": ",".join(us), "perm": npe})
                            s.commit(); st.success("✅ Usuário criado!"); st.rerun()
                    except: st.error("❌ Login já existe.")
            st.divider()
            st.subheader("Gerenciar Usuários")
            df_m_u = conn.query("SELECT * FROM usuarios WHERE username != 'master'", ttl=0)
            if not df_m_u.empty:
                sel_u = st.selectbox("Selecione Usuário para Editar:", df_m_u['username'].tolist())
                d_u = df_m_u[df_m_u['username'] == sel_u].iloc[0]
                with st.expander(f"✏️ Editar: {sel_u}", expanded=True):
                    c_m1, c_m2 = st.columns(2)
                    with c_m1:
                        new_log = st.text_input("Renomear Login:", value=sel_u).lower().strip()
                        if st.button("Gravar Novo Login"):
                            with conn.session as s:
                                s.execute(text("UPDATE usuarios SET username = :n WHERE username = :o"), {"n": new_log, "o": sel_u})
                                s.commit(); st.success("✅ Renomeado!"); st.rerun()
                        st.write("---")
                        s_man = st.text_input("Nova Senha Manual:", key="sman")
                        if st.button("Resetar Senha"):
                            with conn.session as s:
                                s.execute(text("UPDATE usuarios SET password = :p, primeiro_acesso = TRUE WHERE username = :u"), {"p": s_man, "u": sel_u})
                                s.commit(); st.success("✅ Senha Alterada!"); st.rerun()
                    with c_m2:
                        p_e = st.selectbox("Mudar Perfil:", ["LOCAL", "GLOBAL"], index=0 if d_u['perfil']=="LOCAL" else 1)
                        u_e = st.multiselect("Mudar Unidades:", UNIDADES_LISTA, default=d_u['unidade'].split(",") if d_u['perfil']=="LOCAL" else UNIDADES_LISTA) if p_e=="LOCAL" else ["TODAS"]
                        pe_e = st.selectbox("Mudar Nível:", ["EDICAO", "LEITURA"], index=0 if d_u['permissao']=="EDICAO" else 1)
                        if st.button("Salvar Perfil/Acessos"):
                            with conn.session as s:
                                s.execute(text("UPDATE usuarios SET perfil = :perf, unidade = :un, permissao = :perm WHERE username = :u"), {"perf": p_e, "un": ",".join(u_e), "perm": pe_e, "u": sel_u})
                                s.commit(); st.success("✅ Acessos Atualizados!"); st.rerun()
                if st.checkbox(f"Excluir definitivamente {sel_u}"):
                    if st.button("🗑️ Deletar Usuário", type="primary"):
                        with conn.session as s:
                            s.execute(text("DELETE FROM usuarios WHERE username = :u"), {"u": sel_u})
                            s.commit(); st.success("✅ Deletado!"); st.rerun()

        with tabs[3]: # UNIDADES
            st.subheader("Nova Filial")
            with st.form("au"):
                nn = st.text_input("Nome da Nova Unidade").upper().strip()
                if st.form_submit_button("Adicionar"):
                    with conn.session as s:
                        s.execute(text("INSERT INTO unidades (nome) VALUES (:n) ON CONFLICT DO NOTHING"), {"n": nn})
                        s.commit(); st.success("✅ Unidade Adicionada!"); st.rerun()
            st.divider()
            st.subheader("Renomear Filial")
            u_v = st.selectbox("Unidade Antiga:", UNIDADES_LISTA)
            u_n = st.text_input("Novo Nome:").upper().strip()
            if st.button("Gravar Alteração de Nome"):
                if u_n and u_n != u_v:
                    with conn.session as s:
                        s.execute(text("INSERT INTO unidades (nome) VALUES (:n)"), {"n": u_n})
                        s.execute(text("UPDATE produtos SET unidade = :n WHERE unidade = :o"), {"n": u_n, "o": u_v})
                        s.execute(text("UPDATE historico SET unidade = :n WHERE unidade = :o"), {"n": u_n, "o": u_v})
                        s.execute(text("UPDATE usuarios SET unidade = REPLACE(unidade, :o, :n) WHERE perfil = 'LOCAL'"), {"o": u_v, "n": u_n})
                        s.execute(text("DELETE FROM unidades WHERE nome = :o"), {"o": u_v})
                        s.commit(); st.success("✅ Unidade, Estoque e Usuários atualizados!"); st.rerun()

elif choice == "📜 Histórico":
    st.header("Movimentações")
    df_h = conn.query("SELECT colaborador, item, quantidade, tipo, chamado, data FROM historico WHERE unidade = :u ORDER BY id DESC", params={"u": un_atual}, ttl=0)
    st.dataframe(df_h, use_container_width=True)
