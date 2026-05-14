import streamlit as st
import pandas as pd
from datetime import datetime
import io
from PIL import Image
import time
from sqlalchemy import text
import pytz

# --- CONFIGURAÇÕES INICIAIS ---
UNIDADES = ["MATRIZ", "RIO DE JANEIRO", "JOINVILLE", "BELO HORIZONTE"]
SENHA_ADMIN = "admin123"
fuso_br = pytz.timezone('America/Sao_Paulo')

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

# --- CONEXÃO NATIVA ---
conn = st.connection("postgresql", type="sql", url=st.secrets["PG_URL"])

def init_db():
    with conn.session as session:
        session.execute(text("""
            CREATE TABLE IF NOT EXISTS produtos (
                unidade TEXT, item TEXT, quantidade INTEGER, limite_minimo INTEGER,
                PRIMARY KEY (unidade, item)
            );
        """))
        session.execute(text("""
            CREATE TABLE IF NOT EXISTS historico (
                id SERIAL PRIMARY KEY, unidade TEXT, colaborador TEXT, item TEXT,
                data TEXT, tipo TEXT, chamado TEXT, quantidade INTEGER, nf TEXT
            );
        """))
        session.commit()

init_db()

# --- FUNÇÕES DE APOIO ---
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
    df_u = conn.query("SELECT item as \"Produto\", quantidade as \"Estoque\", limite_minimo as \"Mínimo\" FROM produtos WHERE unidade = :unid ORDER BY item ASC", 
                      params={"unid": unidade_atual}, ttl=0)

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
            st.download_button(label="📥 Baixar Lista de Compras Formatada", data=excel_compra,
                               file_name=f"compras_{unidade_atual}.xlsx", mime="application/vnd.ms-excel")

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

elif choice == "⚙️ Gestão":
    st.header(f"Gerenciamento - {unidade_atual}")
    t1, t2, t3, t4, t5, t6 = st.tabs(["🆕 Novo", "✏️ Ajustar", "📝 Renomear", "🗑️ Remover", "🧹 Histórico", "🚀 Reset"])
    
    with t1:
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

    # Carregar itens para as outras abas
    df_geral = conn.query("SELECT item, quantidade, limite_minimo FROM produtos WHERE unidade = :unid ORDER BY item ASC", params={"unid": unidade_atual}, ttl=0)

    with t2:
        if df_geral.empty: st.info("Nenhum item cadastrado para ajustar.")
        else:
            it_edit = st.selectbox("Editar:", df_geral['item'].tolist(), key="sb_edit")
            linha = df_geral[df_geral['item'] == it_edit].iloc[0]
            nq = st.number_input("Nova Qtd", value=int(linha['quantidade']), key="ni_qtd")
            nm = st.number_input("Novo Mínimo", value=int(linha['limite_minimo']), key="ni_min")
            if st.button("Salvar Ajustes"):
                with conn.session as s:
                    s.execute(text("UPDATE produtos SET quantidade = :q, limite_minimo = :m WHERE unidade = :unid AND item = :it"), {"q": nq, "m": nm, "unid": unidade_atual, "it": it_edit})
                    s.commit()
                st.toast("💾 Salvo!")
                time.sleep(0.5)
                st.rerun()

    with t3:
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

    with t4:
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

    with t5:
        senha_h = st.text_input("Senha Admin (Histórico)", type="password", key="pw_hist")
        if senha_h == SENHA_ADMIN:
            if st.button("Apagar Histórico desta Unidade"):
                with conn.session as s:
                    s.execute(text("DELETE FROM historico WHERE unidade = :unid"), {"unid": unidade_atual})
                    s.commit()
                st.toast("🧹 Histórico zerado!")
                time.sleep(0.5)
                st.rerun()

    with t6:
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

elif choice == "📜 Histórico":
    st.header(f"Histórico - {unidade_atual}")
    busca = st.text_input("🔍 Buscar...").upper()
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
