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
UNIDADES_DISPONIVEIS = ["MATRIZ", "FILIAL SÃO PAULO", "FILIAL RIO DE JANEIRO"]
SENHA_ADMIN = "admin123" # Senha para funções de exclusão (Reset de Catálogo)
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
# 2. CONEXÃO E CRIAÇÃO DAS TABELAS (INCLUINDO USUÁRIOS)
# ==========================================
conn = st.connection("postgresql", type="sql", url=st.secrets["PG_URL"])

@st.cache_resource
def init_db():
    try:
        with conn.session as session:
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
            # Nova Tabela de Usuários
            session.execute(text("""
                CREATE TABLE IF NOT EXISTS usuarios (
                    username TEXT PRIMARY KEY,
                    password TEXT,
                    perfil TEXT,
                    unidade TEXT,
                    primeiro_acesso BOOLEAN DEFAULT TRUE
                );
            """))
            
            # Cria o Admin Padrão caso não exista ninguém no banco
            session.execute(text("""
                INSERT INTO usuarios (username, password, perfil, unidade, primeiro_acesso) 
                VALUES ('admin', '123', 'GLOBAL', 'TODAS', FALSE) 
                ON CONFLICT (username) DO NOTHING;
            """))
            session.commit()
    except Exception as e:
        st.warning("⚠️ Inicializando banco de dados. Pressione F5 se a tela travar.")

init_db()

# ==========================================
# 3. SISTEMA DE LOGIN (AUTH WALL E TROCA DE SENHA)
# ==========================================
if "autenticado" not in st.session_state:
    st.session_state["autenticado"] = False
    st.session_state["usuario"] = None
    st.session_state["perfil"] = None
    st.session_state["unidade_acesso"] = None
    st.session_state["primeiro_acesso"] = False

# TELA DE LOGIN
if not st.session_state["autenticado"]:
    st.markdown("<br><br>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        try:
            st.image(Image.open("logo_totvs_2025_white.png"), use_container_width=True)
        except:
            st.markdown("<h2 style='text-align: center;'>TOTVS</h2>", unsafe_allow_html=True)
            
        st.markdown("<h3 style='text-align: center;'>🔐 Acesso ao Sistema</h3>", unsafe_allow_html=True)
        
        # O uso do st.form é o que permite que a tecla "ENTER" funcione!
        with st.form("login_form"):
            user_input = st.text_input("Usuário").lower().strip()
            pass_input = st.text_input("Senha", type="password")
            submit_login = st.form_submit_button("Entrar", use_container_width=True)
            
            if submit_login:
                # Busca o usuário no banco de dados
                df_user = conn.query("SELECT * FROM usuarios WHERE username = :u", params={"u": user_input}, ttl=0)
                
                if not df_user.empty and df_user.iloc[0]["password"] == pass_input:
                    st.session_state["autenticado"] = True
                    st.session_state["usuario"] = user_input
                    st.session_state["perfil"] = df_user.iloc[0]["perfil"]
                    st.session_state["unidade_acesso"] = df_user.iloc[0]["unidade"]
                    st.session_state["primeiro_acesso"] = df_user.iloc[0]["primeiro_acesso"]
                    st.rerun()
                else:
                    st.error("❌ Credenciais inválidas!")
    st.stop()

# TELA DE TROCA DE SENHA OBRIGATÓRIA
if st.session_state["primeiro_acesso"]:
    st.markdown("<br><br>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        st.warning(f"👋 Olá, {st.session_state['usuario']}! Como este é o seu primeiro acesso, é obrigatório alterar a sua senha provisória.")
        with st.form("form_troca_senha"):
            nova_senha = st.text_input("Digite sua nova senha", type="password")
            confirma_senha = st.text_input("Confirme sua nova senha", type="password")
            submit_senha = st.form_submit_button("Atualizar Senha e Entrar")
            
            if submit_senha:
                if nova_senha and nova_senha == confirma_senha:
                    with conn.session as s:
                        s.execute(text("UPDATE usuarios SET password = :p, primeiro_acesso = FALSE WHERE username = :u"), 
                                  {"p": nova_senha, "u": st.session_state["usuario"]})
                        s.commit()
                    st.session_state["primeiro_acesso"] = False
                    st.success("✅ Senha atualizada com sucesso! Entrando no sistema...")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("❌ As senhas não coincidem ou estão em branco.")
    st.stop()

# Função de Logout
def logout():
    st.session_state["autenticado"] = False
    st.rerun()

# ==========================================
# 4. FUNÇÕES DE APOIO E EXPORTAÇÃO
# ==========================================
def get_data_br():
    return datetime.now(fuso_br).strftime("%d/%m/%Y %H:%M")

def gerar_excel_formatado(df, nome_aba, titulo):
    output = io.BytesIO()
    writer = pd.ExcelWriter(output, engine='xlsxwriter')
    df.to_excel(writer, index=False, sheet_name=nome_aba, startrow=3)
    workbook = writer.book
    worksheet = writer.sheets[nome_aba]
    fmt_titulo = workbook.add_format({'bold': True, 'font_size': 16, 'font_color': '#FFFFFF', 'bg_color': '#000000', 'align': 'center', 'valign': 'vcenter', 'border': 1})
    fmt_header = workbook.add_format({'bold': True, 'bg_color': '#D3D3D3', 'border': 1, 'align': 'center'})
    fmt_data = workbook.add_format({'italic': True, 'font_size': 10})
    worksheet.merge_range('A1:G2', titulo, fmt_titulo)
    worksheet.write('A3', f'Relatório extraído em: {get_data_br()}', fmt_data)
    for i, col in enumerate(df.columns):
        largura = max(len(col) + 5, 18)
        worksheet.set_column(i, i, largura)
        worksheet.write(3, i, col, fmt_header)
    writer.close()
    return output.getvalue()

# ==========================================
# 5. MENU E CONTROLE DE VISIBILIDADE
# ==========================================
st.sidebar.markdown(f"👤 Logado como: **{st.session_state['usuario'].upper()}**")
st.sidebar.button("Sair (Logout)", on_click=logout)
st.sidebar.divider()

if st.session_state["perfil"] == "GLOBAL":
    st.sidebar.title("🏢 Unidade Visível")
    unidade_atual = st.sidebar.selectbox("Selecione para visualizar", UNIDADES_DISPONIVEIS)
else:
    unidade_atual = st.session_state["unidade_acesso"]
    st.sidebar.info(f"📍 Unidade Fixa: \n**{unidade_atual}**")

st.sidebar.divider()
menu = ["📊 Dashboard", "📤 Saída", "📥 Entrada", "⚙️ Gestão", "📜 Histórico"]
choice = st.sidebar.selectbox("Menu Principal", menu)

# ==========================================
# 6. TELAS DO SISTEMA
# ==========================================

if choice == "📊 Dashboard":
    st.header(f"Painel de Controle - {unidade_atual}")
    
    if st.session_state["perfil"] == "GLOBAL":
        df_alertas = conn.query("SELECT unidade as \"Unidade\", item as \"Produto\", quantidade as \"Estoque\", limite_minimo as \"Mínimo\" FROM produtos WHERE quantidade <= limite_minimo ORDER BY unidade, item ASC", ttl=0)
        
        if not df_alertas.empty:
            st.toast("⚠️ Alerta: Existem itens críticos no estoque!", icon="🚨")
            with st.expander("🚨 ALERTA GLOBAL - ITENS CRÍTICOS EM TODAS AS UNIDADES", expanded=True):
                st.warning("Os seguintes itens atingiram o limite mínimo ou estão zerados em suas respectivas filiais:")
                st.dataframe(df_alertas, use_container_width=True)
                excel_alertas = gerar_excel_formatado(df_alertas, "Alertas Globais", "ITENS CRÍTICOS - TODAS AS UNIDADES")
                st.download_button("📥 Baixar Relatório de Alertas (Excel)", excel_alertas, f"alertas_globais.xlsx")
            st.divider()

    df_u = conn.query("SELECT item as \"Produto\", quantidade as \"Estoque\", limite_minimo as \"Mínimo\" FROM produtos WHERE unidade = :unid ORDER BY item ASC", params={"unid": unidade_atual}, ttl=0)

    if df_u.empty:
        st.info(f"Nenhum item cadastrado em {unidade_atual}. Vá em 'Gestão' para começar.")
    else:
        df_zerado = df_u[df_u['Estoque'] <= 0]
        df_limite = df_u[(df_u['Estoque'] > 0) & (df_u['Estoque'] <= df_u['Mínimo'])]
        df_ok = df_u[df_u['Estoque'] > df_u['Mínimo']]

        if not df_zerado.empty:
            st.error("### 🔴 ESTOQUE ZERADO")
            st.dataframe(df_zerado, use_container_width=True)
        if not df_limite.empty:
            st.warning("### 🟡 LIMITE MÍNIMO ATINGIDO")
            st.dataframe(df_limite, use_container_width=True)
        if not df_ok.empty:
            st.success("### 🟢 ESTOQUE SAUDÁVEL")
            st.dataframe(df_ok, use_container_width=True)
        
        df_compra = pd.concat([df_zerado, df_limite])
        if not df_compra.empty:
            st.divider()
            st.markdown("#### 🛒 Reposição de Estoque")
            excel_compra = gerar_excel_formatado(df_compra, "Lista de Compras", f"SOLICITAÇÃO DE COMPRAS - {unidade_atual}")
            st.download_button(label="📥 Baixar Lista de Compras Formatada", data=excel_compra, file_name=f"compras_{unidade_atual}.xlsx")

elif choice == "📤 Saída":
    st.header(f"Registrar Entrega - {unidade_atual}")
    df_itens = conn.query("SELECT item, quantidade FROM produtos WHERE unidade = :unid ORDER BY item ASC", params={"unid": unidade_atual}, ttl=0)
    
    if df_itens.empty:
        st.warning(f"⚠️ Não existem produtos cadastrados em {unidade_atual}. Cadastre primeiro em 'Gestão'.")
    else:
        c1, col2 = st.columns(2)
        with c1:
            user = st.text_input("Colaborador").upper()
            cham = st.text_input("Número do Chamado").upper()
        with col2:
            it_sel = st.selectbox("Selecione o Produto", df_itens['item'].tolist())
            q_sai = st.number_input("Quantidade", min_value=1, step=1)
            if st.button("Confirmar Baixa"):
                if user and cham:
                    saldo = df_itens.loc[df_itens['item'] == it_sel, 'quantidade'].values[0]
                    if saldo >= q_sai:
                        with conn.session as s:
                            s.execute(text("UPDATE produtos SET quantidade = quantidade - :q WHERE unidade = :unid AND item = :it"), {"q": q_sai, "unid": unidade_atual, "it": it_sel})
                            s.execute(text("INSERT INTO historico (unidade, colaborador, item, data, tipo, chamado, quantidade, nf) VALUES (:unid, :user, :it, :dt, 'SAÍDA', :ch, :q, 'N/A')"),
                                      {"unid": unidade_atual, "user": user, "it": it_sel, "dt": get_data_br(), "ch": cham, "q": q_sai})
                            s.commit()
                        st.toast("✅ Saída registrada!", icon="✅")
                        time.sleep(0.5)
                        st.rerun()
                    else: st.error("Estoque insuficiente.")
                else: st.error("Preencha todos os campos obrigatórios.")

elif choice == "📥 Entrada":
    st.header(f"Entrada de Material (Reposição) - {unidade_atual}")
    df_itens = conn.query("SELECT item FROM produtos WHERE unidade = :unid ORDER BY item ASC", params={"unid": unidade_atual}, ttl=0)
    
    if df_itens.empty:
        st.warning(f"⚠️ Não existem produtos cadastrados em {unidade_atual}.")
    else:
        c1, c2 = st.columns(2)
        with c1:
            it_ent = st.selectbox("Produto", df_itens['item'].tolist())
            q_ent = st.number_input("Qtd Recebida", min_value=1, step=1)
        with c2:
            nf_ent = st.text_input("Número da NF").upper()
        if st.button("Confirmar Entrada"):
            if nf_ent:
                with conn.session as s:
                    s.execute(text("UPDATE produtos SET quantidade = quantidade + :q WHERE unidade = :unid AND item = :it"), {"q": q_ent, "unid": unidade_atual, "it": it_ent})
                    s.execute(text("INSERT INTO historico (unidade, colaborador, item, data, tipo, chamado, quantidade, nf) VALUES (:unid, 'SISTEMA', :it, :dt, 'ENTRADA', 'REPOSIÇÃO', :q, :nf)"),
                              {"unid": unidade_atual, "it": it_ent, "dt": get_data_br(), "q": q_ent, "nf": nf_ent})
                    s.commit()
                st.toast("📥 Estoque atualizado!", icon="📥")
                time.sleep(0.5)
                st.rerun()
            else: st.error("O número da NF é obrigatório para entrada.")

elif choice == "⚙️ Gestão":
    st.header(f"Gerenciamento - {unidade_atual}")
    
    # Prepara as abas. Se for GLOBAL, adiciona a aba de Gestão de Usuários
    abas_nomes = ["🆕 Novo Item", "✏️ Ajustar", "📝 Renomear", "🗑️ Remover", "🧹 Histórico", "🚀 Reset"]
    if st.session_state["perfil"] == "GLOBAL":
        abas_nomes.append("👥 Usuários")
        
    abas = st.tabs(abas_nomes)
    
    with abas[0]:
        st.subheader("Cadastrar Periférico")
        n_it = st.text_input("Nome do Periférico", key="new_item").upper()
        n_q = st.number_input("Qtd Inicial", min_value=0, key="new_qtd")
        n_m = st.number_input("Limite Mínimo", min_value=1, value=5, key="new_min")
        n_nf = st.text_input("NF (Opcional)", key="new_nf").upper()
        if st.button("Salvar Cadastro"):
            if n_it:
                try:
                    with conn.session as s:
                        s.execute(text("INSERT INTO produtos (unidade, item, quantidade, limite_minimo) VALUES (:unid, :it, :q, :m)"), {"unid": unidade_atual, "it": n_it, "q": n_q, "m": n_m})
                        s.execute(text("INSERT INTO historico (unidade, colaborador, item, data, tipo, chamado, quantidade, nf) VALUES (:unid, 'SISTEMA', :it, :dt, 'CADASTRO', 'N/A', :q, :nf)"),
                                  {"unid": unidade_atual, "it": n_it, "dt": get_data_br(), "q": n_q, "nf": n_nf if n_nf else "N/A"})
                        s.commit()
                    st.toast("✨ Item cadastrado!", icon="✨")
                    time.sleep(0.5)
                    st.rerun()
                except: st.error("Erro: Este item já existe nesta unidade.")

    df_geral = conn.query("SELECT item, quantidade, limite_minimo FROM produtos WHERE unidade = :unid ORDER BY item ASC", params={"unid": unidade_atual}, ttl=0)

    with abas[1]:
        if df_geral.empty: st.info("Nenhum item cadastrado para ajustar.")
        else:
            it_edit = st.selectbox("Editar:", df_geral['item'].tolist(), key="sb_edit")
            linha = df_geral[df_geral['item'] == it_edit].iloc[0]
            nq = st.number_input("Nova Qtd", value=int(linha['quantidade']), key="ni_qtd")
            nm = st.number_input("Novo Mínimo", value=int(linha['limite_minimo']), key="ni_min")
            if st.button("Salvar Ajustes", key="btn_ajustes"):
                with conn.session as s:
                    s.execute(text("UPDATE produtos SET quantidade = :q, limite_minimo = :m WHERE unidade = :unid AND item = :it"), {"q": nq, "m": nm, "unid": unidade_atual, "it": it_edit})
                    s.commit()
                st.toast("💾 Salvo!")
                time.sleep(0.5)
                st.rerun()

    with abas[2]:
        if df_geral.empty: st.info("Nenhum item cadastrado para renomear.")
        else:
            it_ren = st.selectbox("Item para renomear:", df_geral['item'].tolist(), key="sb_ren")
            novo_nome = st.text_input("Novo Nome", key="ti_ren").upper()
            if st.button("Confirmar Renomeação"):
                if novo_nome:
                    with conn.session as s:
                        s.execute(text("UPDATE produtos SET item = :novo WHERE unidade = :unid AND item = :velho"), {"novo": novo_nome, "unid": unidade_atual, "velho": it_ren})
                        s.execute(text("UPDATE historico SET item = :novo WHERE unidade = :unid AND item = :velho"), {"novo": novo_nome, "unid": unidade_atual, "velho": it_ren})
                        s.commit()
                    st.toast("📝 Nome atualizado!")
                    time.sleep(0.5)
                    st.rerun()

    with abas[3]:
        if df_geral.empty: st.info("Nenhum item cadastrado para remover.")
        else:
            it_rem = st.selectbox("Remover:", df_geral['item'].tolist(), key="sb_rem")
            if st.checkbox(f"Confirmo a remoção de {it_rem}"):
                if st.button("Remover Agora"):
                    with conn.session as s:
                        s.execute(text("DELETE FROM produtos WHERE unidade = :unid AND item = :it"), {"unid": unidade_atual, "it": it_rem})
                        s.commit()
                    st.toast("🗑️ Item removido!")
                    time.sleep(0.5)
                    st.rerun()

    with abas[4]:
        senha_h = st.text_input("Senha Admin (Histórico)", type="password", key="pw_hist")
        if senha_h == SENHA_ADMIN:
            if st.button("Apagar Histórico desta Unidade"):
                with conn.session as s:
                    s.execute(text("DELETE FROM historico WHERE unidade = :unid"), {"unid": unidade_atual})
                    s.commit()
                st.toast("🧹 Histórico zerado!")
                time.sleep(0.5)
                st.rerun()

    with abas[5]:
        senha_r = st.text_input("Senha Admin (Reset)", type="password", key="pw_reset")
        if senha_r == SENHA_ADMIN:
            conf_text = st.text_input("Digite CONFIRMAR:").upper()
            if conf_text == "CONFIRMAR":
                if st.button("EXECUTAR RESET CATÁLOGO"):
                    with conn.session as s:
                        s.execute(text("DELETE FROM produtos WHERE unidade = :unid"), {"unid": unidade_atual})
                        s.commit()
                    st.toast("🚀 Catálogo resetado!")
                    time.sleep(0.5)
                    st.rerun()
                    
    # ABA EXCLUSIVA DE CRIAÇÃO DE USUÁRIOS
    if st.session_state["perfil"] == "GLOBAL":
        with abas[6]:
            st.subheader("Cadastrar Novo Colaborador")
            st.info("A senha cadastrada aqui será temporária. O usuário será obrigado a criar uma nova no primeiro acesso.")
            with st.form("form_novo_usuario"):
                novo_login = st.text_input("Login do Usuário").lower().strip()
                senha_temp = st.text_input("Senha Temporária")
                
                col_u1, col_u2 = st.columns(2)
                with col_u1:
                    perfil_novo = st.selectbox("Perfil de Acesso", ["LOCAL", "GLOBAL"])
                with col_u2:
                    if perfil_novo == "GLOBAL":
                        unidade_novo = st.selectbox("Unidade Base", ["TODAS"])
                    else:
                        unidade_novo = st.selectbox("Unidade Base", UNIDADES_DISPONIVEIS)
                        
                submit_novo_user = st.form_submit_button("Criar Usuário")
                
                if submit_novo_user:
                    if novo_login and senha_temp:
                        try:
                            with conn.session as s:
                                s.execute(text("INSERT INTO usuarios (username, password, perfil, unidade, primeiro_acesso) VALUES (:u, :p, :perf, :unid, TRUE)"),
                                          {"u": novo_login, "p": senha_temp, "perf": perfil_novo, "unid": unidade_novo})
                                s.commit()
                            st.success(f"✅ Usuário '{novo_login}' criado com sucesso!")
                        except:
                            st.error("❌ Este login já existe no sistema.")
                    else:
                        st.error("Preencha todos os campos obrigatórios.")

elif choice == "📜 Histórico":
    st.header(f"Histórico - {unidade_atual}")
    busca = st.text_input("🔍 Buscar por Colaborador, Item ou Chamado").upper()
    query_hist = "SELECT colaborador as \"Colaborador\", item as \"Item\", quantidade as \"Qtd\", nf as \"NF\", data as \"Data/Hora\", tipo as \"Operação\", chamado as \"Ticket\" FROM historico WHERE unidade = :unid"
    params_hist = {"unid": unidade_atual}
    
    if busca:
        query_hist += " AND (colaborador ILIKE :b OR item ILIKE :b OR chamado ILIKE :b)"
        params_hist["b"] = f"%{busca}%"
    
    query_hist += " ORDER BY id DESC"
    df_h = conn.query(query_hist, params=params_hist, ttl=0)
    
    if not df_h.empty:
        st.dataframe(df_h, use_container_width=True)
        excel_hist = gerar_excel_formatado(df_h, "Histórico", f"RELATÓRIO DE MOVIMENTAÇÃO - {unidade_atual}")
        st.download_button("📥 Baixar Histórico Formatado", excel_hist, f"historico_{unidade_atual}.xlsx")
    else:
        st.info("Nenhuma movimentação encontrada.")
