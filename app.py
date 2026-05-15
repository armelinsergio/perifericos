import streamlit as st
import pandas as pd
from datetime import datetime
import io
from PIL import Image
import time
from sqlalchemy import text
import pytz
import uuid # Biblioteca nativa para gerar tokens de segurança

# ==========================================
# 1. CONFIGURAÇÕES INICIAIS
# ==========================================
SENHA_ADMIN_MASTER = "admin123" 
fuso_br = pytz.timezone('America/Sao_Paulo')

st.set_page_config(page_title="Controle de Estoque TOTVS", layout="wide", initial_sidebar_state="expanded")

# CSS Ajustado: O 'header' foi removido para que a seta do menu lateral volte a aparecer
st.markdown("""
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
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
            session.execute(text("CREATE TABLE IF NOT EXISTS reset_requests (username TEXT PRIMARY KEY, data_solicitacao TEXT);"))
            
            res_u = session.execute(text("SELECT count(*) FROM unidades")).fetchone()
            if res_u[0] == 0:
                for u in ["MATRIZ", "FILIAL SÃO PAULO", "FILIAL RIO DE JANEIRO"]:
                    session.execute(text("INSERT INTO unidades (nome) VALUES (:n)"), {"n": u})
            
            session.execute(text("INSERT INTO usuarios (username, password, perfil, unidade, primeiro_acesso, permissao) VALUES ('master', 'admin123', 'MASTER', 'TODAS', TRUE, 'EDICAO') ON CONFLICT (username) DO NOTHING;"))
            session.execute(text("DELETE FROM usuarios WHERE username = 'admin';"))
            session.commit()

    try: executar_criacao()
    except Exception:
        conn.reset()
        try: executar_criacao()
        except Exception as e: st.error(f"Erro ao inicializar banco: {e}")

    # Adiciona a coluna de Token de Sessão (para sobrevivência ao F5) sem quebrar dados existentes
    try:
        with conn.session as s:
            s.execute(text("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS session_token TEXT;"))
            s.commit()
    except:
        pass 

init_db()

def get_unidades():
    df = conn.query("SELECT nome FROM unidades ORDER BY nome ASC", ttl=0)
    return df['nome'].tolist()

# ==========================================
# 3. SISTEMA DE LOGIN E RECUPERAÇÃO (COM TOKEN)
# ==========================================
if "autenticado" not in st.session_state:
    st.session_state.update({"autenticado": False, "usuario": None, "perfil": None, "unidade_acesso": None, "primeiro_acesso": False, "permissao": None})

# ---- TENTATIVA DE AUTO-LOGIN (O que impede o F5 de deslogar) ----
if not st.session_state["autenticado"] and "session" in st.query_params:
    token_url = st.query_params["session"]
    df_token = conn.query("SELECT * FROM usuarios WHERE session_token = :t", params={"t": token_url}, ttl=0)
    if not df_token.empty:
        user_info = df_token.iloc[0]
        st.session_state.update({
            "autenticado": True,
            "usuario": user_info["username"],
            "perfil": user_info["perfil"],
            "unidade_acesso": user_info["unidade"],
            "primeiro_acesso": user_info["primeiro_acesso"],
            "permissao": user_info["permissao"] if pd.notna(user_info["permissao"]) else "EDICAO"
        })

# ---- TELA DE LOGIN ----
if not st.session_state["autenticado"]:
    st.markdown("<br><br>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        try: st.image(Image.open("logo_totvs_2025_white.png"), use_container_width=True)
        except: st.markdown("<h2 style='text-align: center;'>TOTVS</h2>", unsafe_allow_html=True)
        
        tab_login, tab_reset = st.tabs(["🔐 Acesso", "❓ Esqueci a Senha"])
        
        with tab_login:
            with st.form("login_form"):
                user_input = st.text_input("Usuário").lower().strip()
                pass_input = st.text_input("Senha", type="password")
                if st.form_submit_button("Entrar", use_container_width=True):
                    df_user = conn.query("SELECT * FROM usuarios WHERE username = :u", params={"u": user_input}, ttl=0)
                    if not df_user.empty and df_user.iloc[0]["password"] == pass_input:
                        
                        # Gera um token único e salva no Banco e na URL para manter logado
                        novo_token = str(uuid.uuid4())
                        with conn.session as s:
                            s.execute(text("UPDATE usuarios SET session_token = :t WHERE username = :u"), {"t": novo_token, "u": user_input})
                            s.commit()
                        st.query_params["session"] = novo_token
                        
                        st.session_state.update({
                            "autenticado": True, "usuario": user_input,
                            "perfil": df_user.iloc[0]["perfil"],
                            "unidade_acesso": df_user.iloc[0]["unidade"],
                            "primeiro_acesso": df_user.iloc[0]["primeiro_acesso"],
                            "permissao": df_user.iloc[0]["permissao"] if pd.notna(df_user.iloc[0]["permissao"]) else "EDICAO"
                        })
                        st.rerun()
                    else: st.error("❌ Acesso negado")
                    
        with tab_reset:
            st.info("Solicite o reset da sua senha ao Administrador Master.")
            with st.form("reset_form"):
                user_reset = st.text_input("Qual é o seu Usuário?").lower().strip()
                if st.form_submit_button("Solicitar Reset", use_container_width=True):
                    if user_reset:
                        df_check = conn.query("SELECT username FROM usuarios WHERE username = :u", params={"u": user_reset}, ttl=0)
                        if not df_check.empty:
                            with conn.session as s:
                                s.execute(text("INSERT INTO reset_requests (username, data_solicitacao) VALUES (:u, :d) ON CONFLICT DO NOTHING"), {"u": user_reset, "d": datetime.now(fuso_br).strftime("%d/%m/%Y %H:%M")})
                                s.commit()
                            st.success(f"✅ Solicitação enviada! Informe o Admin Master.")
                        else: st.error("Usuário não encontrado.")
    st.stop()

if st.session_state["primeiro_acesso"]:
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        st.warning("🔒 Altere sua senha provisória para continuar.")
        with st.form("form_pwd"):
            p1 = st.text_input("Nova Senha", type="password")
            p2 = st.text_input("Confirme Nova Senha", type="password")
            if st.form_submit_button("Salvar e Entrar"):
                if p1 == p2 and p1:
                    with conn.session as s:
                        s.execute(text("UPDATE usuarios SET password = :p, primeiro_acesso = FALSE WHERE username = :u"), {"p": p1, "u": st.session_state["usuario"]})
                        s.commit()
                    st.session_state["primeiro_acesso"] = False
                    st.success("✅ Senha atualizada!"); time.sleep(1); st.rerun()
                else: st.error("Senhas não coincidem ou estão vazias.")
    st.stop()

# ==========================================
# 4. FUNÇÕES GERAIS E EXPORTAÇÃO
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

if st.sidebar.button("Sair (Logout)"):
    # Limpa o token do banco e da URL na hora de sair
    try:
        with conn.session as s:
            s.execute(text("UPDATE usuarios SET session_token = NULL WHERE username = :u"), {"u": st.session_state["usuario"]})
            s.commit()
    except: pass
    st.query_params.clear()
    st.session_state["autenticado"] = False
    st.rerun()

UNIDADES_LISTA = get_unidades()

if st.session_state["perfil"] in ["MASTER", "GLOBAL"]:
    unidades_permitidas = UNIDADES_LISTA
else:
    unidades_permitidas = st.session_state["unidade_acesso"].split(",")

unidade_atual = st.sidebar.selectbox("🏢 Unidade Ativa", unidades_permitidas)

menu_disponivel = ["📊 Dashboard", "📜 Histórico"]
if st.session_state["permissao"] == "EDICAO" or st.session_state["perfil"] in ["MASTER", "GLOBAL"]:
    menu_disponivel = ["📊 Dashboard", "📤 Saída", "📥 Entrada", "⚙️ Gestão", "📜 Histórico"]

st.sidebar.divider()
choice = st.sidebar.selectbox("Menu", menu_disponivel)

# ==========================================
# 6. TELAS
# ==========================================

if choice == "📊 Dashboard":
    df_alertas_full = conn.query("SELECT unidade, item, quantidade, limite_minimo FROM produtos WHERE quantidade <= limite_minimo ORDER BY unidade, item ASC", ttl=0)
    if not df_alertas_full.empty:
        if st.session_state["perfil"] in ["MASTER", "GLOBAL"]:
            df_mostrar = df_alertas_full
        else:
            df_mostrar = df_alertas_full[df_alertas_full['unidade'].isin(unidades_permitidas)]
            
        if not df_mostrar.empty:
            st.error("🚨 **ITENS COM ESTOQUE CRÍTICO OU ZERADO**")
            st.dataframe(df_mostrar, use_container_width=True)
            st.divider()

    st.header(f"Painel - {unidade_atual}")
    df_u = conn.query("SELECT item as \"Produto\", quantidade as \"Estoque\", limite_minimo as \"Mínimo\" FROM produtos WHERE unidade = :u ORDER BY item ASC", params={"u": unidade_atual}, ttl=0)
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
            if st.form_submit_button("Confirmar Saída"):
                estoque = df_p.loc[df_p['item']==it, 'quantidade'].values[0]
                if estoque >= qtd:
                    with conn.session as s:
                        s.execute(text("UPDATE produtos SET quantidade = quantidade - :q WHERE unidade = :un AND item = :it"), {"q": qtd, "un": unidade_atual, "it": it})
                        s.execute(text("INSERT INTO historico (unidade, colaborador, item, data, tipo, chamado, quantidade, nf) VALUES (:un, :c, :it, :d, 'SAÍDA', :ch, :q, 'N/A')"),
                                  {"un": unidade_atual, "c": colab, "it": it, "d": get_data_br(), "ch": cham, "q": qtd})
                        s.commit()
                    st.success("✅ Saída registrada!"); time.sleep(1); st.rerun()
                else: st.error("❌ Estoque insuficiente!")

elif choice == "📥 Entrada":
    st.header("Entrada de Material")
    df_p = conn.query("SELECT item FROM produtos WHERE unidade = :u", params={"u": unidade_atual}, ttl=0)
    if df_p.empty: st.warning("Cadastre itens primeiro.")
    else:
        with st.form("entrada"):
            it = st.selectbox("Item", df_p['item'].tolist())
            qtd = st.number_input("Qtd", min_value=1)
            nf = st.text_input("Nota Fiscal").upper()
            if st.form_submit_button("Confirmar Entrada"):
                if nf:
                    with conn.session as s:
                        s.execute(text("UPDATE produtos SET quantidade = quantidade + :q WHERE unidade = :un AND item = :it"), {"q": qtd, "un": unidade_atual, "it": it})
                        s.execute(text("INSERT INTO historico (unidade, colaborador, item, data, tipo, chamado, quantidade, nf) VALUES (:un, 'SISTEMA', :it, :d, 'ENTRADA', 'REPOSIÇÃO', :q, :nf)"),
                                  {"un": unidade_atual, "it": it, "d": get_data_br(), "q": qtd, "nf": nf})
                        s.commit()
                    st.success("✅ Entrada registrada!"); time.sleep(1); st.rerun()
                else: st.error("❌ NF é obrigatória.")

elif choice == "⚙️ Gestão":
    st.header("Gestão do Sistema")
    tab_list = ["📦 Itens"]
    if st.session_state["perfil"] == "MASTER":
        tab_list += ["🧹 Limpeza", "👥 Usuários", "🏢 Unidades"]
    tabs = st.tabs(tab_list)
    
    with tabs[0]: # ITENS
        st.subheader("Novo Item")
        with st.form("new_item"):
            ni, nq, nm = st.text_input("Nome").upper(), st.number_input("Qtd", min_value=0), st.number_input("Min", min_value=1, value=5)
            if st.form_submit_button("Salvar Cadastro"):
                if ni:
                    try:
                        with conn.session as s:
                            s.execute(text("INSERT INTO produtos (unidade, item, quantidade, limite_minimo) VALUES (:u, :i, :q, :m)"), {"u": unidade_atual, "i": ni, "q": nq, "m": nm})
                            s.commit(); st.success("✅ Cadastrado!"); st.rerun()
                    except: st.error("❌ Já existe.")
        
        st.divider()
        df_geral = conn.query("SELECT item, quantidade, limite_minimo FROM produtos WHERE unidade = :u ORDER BY item ASC", params={"u": unidade_atual}, ttl=0)
        if not df_geral.empty:
            it_edit = st.selectbox("Editar/Remover Item:", df_geral['item'].tolist())
            linha = df_geral[df_geral['item'] == it_edit].iloc[0]
            c1, c2 = st.columns(2)
            with c1:
                nq2, nm2 = st.number_input("Estoque Real", value=int(linha['quantidade'])), st.number_input("Alerta Mínimo", value=int(linha['limite_minimo']))
                if st.button("Atualizar Quantidades"):
                    with conn.session as s:
                        s.execute(text("UPDATE produtos SET quantidade = :q, limite_minimo = :m WHERE unidade = :u AND item = :it"), {"q": nq2, "m": nm2, "u": unidade_atual, "it": it_edit})
                        s.commit()
                    st.success("✅ Quantidades atualizadas com sucesso!"); st.rerun()
            with c2:
                st.write("Exclusão")
                if st.checkbox(f"Confirmar exclusão definitiva de {it_edit}"):
                    if st.button("🗑️ Remover Item", type="primary"):
                        with conn.session as s:
                            s.execute(text("DELETE FROM produtos WHERE unidade = :u AND item = :it"), {"u": unidade_atual, "it": it_edit})
                            s.commit()
                        st.success("✅ Item removido com sucesso!"); st.rerun()

    if st.session_state["perfil"] == "MASTER":
        with tabs[1]: # LIMPEZA
            st.subheader("Operações Críticas")
            pw = st.text_input("Senha Master", type="password")
            if pw == SENHA_ADMIN_MASTER:
                if st.button("🚨 LIMPAR HISTÓRICO DESTA UNIDADE"):
                    with conn.session as s:
                        s.execute(text("DELETE FROM historico WHERE unidade = :u"), {"u": unidade_atual})
                        s.commit(); st.success("✅ Histórico totalmente limpo!")
                if st.button("🚀 ZERAR CATÁLOGO (Deletar tudo desta unidade)"):
                    with conn.session as s:
                        s.execute(text("DELETE FROM produtos WHERE unidade = :u"), {"u": unidade_atual})
                        s.commit(); st.success("✅ Catálogo deletado!")

        with tabs[2]: # USUÁRIOS
            df_requests = conn.query("SELECT * FROM reset_requests", ttl=0)
            if not df_requests.empty:
                st.warning("⚠️ Solicitações Pendentes")
                for index, req in df_requests.iterrows():
                    u_req = req['username']
                    with st.expander(f"Solicitação de: {u_req}"):
                        senha_resp = st.text_input(f"Definir nova senha para {u_req}:", key=f"resp_{u_req}")
                        if st.button(f"Aprovar Reset de {u_req}"):
                            if senha_resp:
                                with conn.session as s:
                                    s.execute(text("UPDATE usuarios SET password = :p, primeiro_acesso = TRUE WHERE username = :u"), {"p": senha_resp, "u": u_req})
                                    s.execute(text("DELETE FROM reset_requests WHERE username = :u"), {"u": u_req})
                                    s.commit()
                                st.success(f"✅ Reset concluído para {u_req}!"); st.rerun()
                            else: st.error("Defina uma senha.")
            st.divider()

            st.subheader("Novo Usuário")
            with st.form("create_user"):
                nu, ns = st.text_input("Login").lower().strip(), st.text_input("Senha Inicial")
                c_p, c_m = st.columns(2)
                with c_p: np = st.selectbox("Perfil", ["LOCAL", "GLOBAL"])
                with c_m: n_perm = st.selectbox("Permissão", ["EDICAO", "LEITURA"])
                
                u_sel = st.multiselect("Unidades", UNIDADES_LISTA) if np == "LOCAL" else ["TODAS"]
                
                if st.form_submit_button("Criar Usuário"):
                    if nu and ns:
                        if np == "LOCAL" and not u_sel:
                            st.error("❌ Selecione ao menos uma unidade para perfil LOCAL.")
                        else:
                            try:
                                with conn.session as s:
                                    s.execute(text("INSERT INTO usuarios (username, password, perfil, unidade, primeiro_acesso, permissao) VALUES (:u, :p, :perf, :un, TRUE, :perm)"),
                                              {"u": nu, "p": ns, "perf": np, "un": ",".join(u_sel), "perm": n_perm})
                                    s.commit()
                                st.success(f"✅ Usuário '{nu}' criado com sucesso!"); st.rerun()
                            except: st.error("❌ Login já existe.")

            st.divider()
            st.subheader("Gerenciar Usuários")
            df_u_list = conn.query("SELECT * FROM usuarios WHERE username != 'master'", ttl=0)
            if not df_u_list.empty:
                sel_u = st.selectbox("Selecionar Usuário:", df_u_list['username'].tolist())
                dados_u = df_u_list[df_u_list['username'] == sel_u].iloc[0]
                
                with st.expander(f"✏️ Editar: {sel_u}", expanded=True):
                    c_edit1, c_edit2 = st.columns(2)
                    
                    with c_edit1:
                        st.write("**Credenciais**")
                        novo_login = st.text_input("Renomear Login:", placeholder=sel_u).lower().strip()
                        if st.button("Gravar Novo Login"):
                            if novo_login and novo_login != sel_u:
                                try:
                                    with conn.session as s:
                                        s.execute(text("UPDATE usuarios SET username = :n WHERE username = :o"), {"n": novo_login, "o": sel_u})
                                        s.commit()
                                    st.success("✅ Login renomeado com sucesso!"); st.rerun()
                                except: st.error("❌ Login já existente.")
                        
                        st.write("---")
                        nova_senha_manual = st.text_input("Nova Senha de Reset:", key="manual_pass")
                        if st.button("Executar Reset de Senha"):
                            if nova_senha_manual:
                                with conn.session as s:
                                    s.execute(text("UPDATE usuarios SET password = :p, primeiro_acesso = TRUE WHERE username = :u"), {"p": nova_senha_manual, "u": sel_u})
                                    s.commit()
                                st.success(f"✅ Senha alterada! O usuário deverá trocar no próximo acesso."); st.rerun()
                            else: st.error("Digite a nova senha.")
                            
                    with c_edit2:
                        st.write("**Perfil e Acessos**")
                        n_perfil = st.selectbox("Perfil de Acesso:", ["LOCAL", "GLOBAL"], index=0 if dados_u['perfil'] == "LOCAL" else 1, key="edit_perfil")
                        
                        u_atuais = dados_u['unidade'].split(",") if dados_u['perfil'] == "LOCAL" else []
                        if n_perfil == "LOCAL":
                            n_u = st.multiselect("Unidades Permitidas:", UNIDADES_LISTA, default=[x for x in u_atuais if x in UNIDADES_LISTA], key="edit_unid")
                        else:
                            n_u = ["TODAS"]
                            
                        n_p = st.selectbox("Permissão no Sistema:", ["EDICAO", "LEITURA"], index=0 if dados_u['permissao'] == "EDICAO" else 1, key="edit_perm")
                        
                        if st.button("Salvar Perfil e Acessos"):
                            if n_perfil == "LOCAL" and not n_u:
                                st.error("❌ Selecione ao menos uma unidade para o perfil LOCAL.")
                            else:
                                with conn.session as s:
                                    s.execute(text("UPDATE usuarios SET perfil = :perf, unidade = :un, permissao = :perm WHERE username = :u"), 
                                              {"perf": n_perfil, "un": ",".join(n_u), "perm": n_p, "u": sel_u})
                                    s.commit()
                                st.success("✅ Acessos atualizados com sucesso!"); time.sleep(1); st.rerun()

                    st.write("---")
                    if st.checkbox(f"Confirmar exclusão definitiva do usuário {sel_u}"):
                        if st.button("🗑️ Deletar Usuário", type="primary"):
                            with conn.session as s:
                                s.execute(text("DELETE FROM usuarios WHERE username = :u"), {"u": sel_u})
                                s.execute(text("DELETE FROM reset_requests WHERE username = :u"), {"u": sel_u})
                                s.commit()
                            st.success("✅ Usuário deletado do sistema!"); time.sleep(1); st.rerun()

        with tabs[3]: # UNIDADES
            st.subheader("Nova Filial")
            with st.form("add_u"):
                n_unid = st.text_input("Nome da Nova Unidade").upper().strip()
                if st.form_submit_button("Adicionar"):
                    if n_unid:
                        with conn.session as s:
                            s.execute(text("INSERT INTO unidades (nome) VALUES (:n) ON CONFLICT DO NOTHING"), {"n": n_unid})
                            s.commit()
                        st.success(f"✅ Unidade '{n_unid}' adicionada com sucesso!"); st.rerun()
            st.divider()
            st.subheader("Renomear Filial")
            u_v = st.selectbox("Unidade Antiga:", UNIDADES_LISTA)
            u_n = st.text_input("Novo Nome da Unidade:").upper().strip()
            if st.button("Gravar Novo Nome de Unidade"):
                if u_n and u_n != u_v:
                    with conn.session as s:
                        s.execute(text("INSERT INTO unidades (nome) VALUES (:n)"), {"n": u_n})
                        s.execute(text("UPDATE produtos SET unidade = :n WHERE unidade = :o"), {"n": u_n, "o": u_v})
                        s.execute(text("UPDATE historico SET unidade = :n WHERE unidade = :o"), {"n": u_n, "o": u_v})
                        s.execute(text("UPDATE usuarios SET unidade = REPLACE(unidade, :o, :n) WHERE perfil = 'LOCAL' AND unidade LIKE :like_o"), {"n": u_n, "o": u_v, "like_o": f"%{u_v}%"})
                        s.execute(text("DELETE FROM unidades WHERE nome = :o"), {"o": u_v})
                        s.commit()
                    st.success("✅ Unidade renomeada! Históricos, estoques e acessos atualizados."); st.rerun()

elif choice == "📜 Histórico":
    st.header("Movimentações")
    df_h = conn.query("SELECT colaborador, item, quantidade, tipo, chamado, data FROM historico WHERE unidade = :u ORDER BY id DESC", params={"u": unidade_atual}, ttl=0)
    st.dataframe(df_h, use_container_width=True)
