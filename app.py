import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
import io
import os

# --- LISTA DE UNIDADES (Edite os nomes aqui) ---
UNIDADES = ["MATRIZ", "RIO DE JANEIRO", "JOINVILLE"]

# --- CONFIGURAÇÃO DO BANCO DE DADOS ---
def init_db():
    conn = sqlite3.connect('estoque_ti.db')
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS produtos 
                 (unidade TEXT, item TEXT, quantidade INTEGER, limite_minimo INTEGER, PRIMARY KEY (unidade, item))''')
    c.execute('''CREATE TABLE IF NOT EXISTS historico 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, unidade TEXT, colaborador TEXT, item TEXT, data TEXT, tipo TEXT, chamado TEXT, quantidade INTEGER)''')
    
    c.execute("PRAGMA table_info(produtos)")
    colunas_produtos = [col[1] for col in c.fetchall()]
    if 'unidade' not in colunas_produtos:
        c.execute('''CREATE TABLE produtos_novo (unidade TEXT, item TEXT, quantidade INTEGER, limite_minimo INTEGER, PRIMARY KEY (unidade, item))''')
        c.execute("INSERT INTO produtos_novo (unidade, item, quantidade, limite_minimo) SELECT 'MATRIZ', item, quantidade, limite_minimo FROM produtos")
        c.execute("DROP TABLE produtos")
        c.execute("ALTER TABLE produtos_novo RENAME TO produtos")

    try: c.execute("ALTER TABLE historico ADD COLUMN chamado TEXT")
    except: pass
    try: c.execute("ALTER TABLE historico ADD COLUMN quantidade INTEGER")
    except: pass
    try: c.execute("ALTER TABLE historico ADD COLUMN unidade TEXT DEFAULT 'MATRIZ'")
    except: pass

    conn.commit()
    conn.close()

init_db()

# --- CONFIGURAÇÃO DE SEGURANÇA ---
SENHA_ADMIN = "admin123" 

# --- FUNÇÕES DE APOIO ---
def run_query(query, params=(), commit=False):
    conn = sqlite3.connect('estoque_ti.db')
    c = conn.cursor()
    c.execute(query, params)
    if commit:
        conn.commit()
        conn.close()
    else:
        res = c.fetchall()
        conn.close()
        return res

def to_excel(df):
    output = io.BytesIO()
    writer = pd.ExcelWriter(output, engine='xlsxwriter')
    df.to_excel(writer, index=False, sheet_name='Histórico')
    writer.close()
    return output.getvalue()

# --- INTERFACE E CONFIGURAÇÕES VISUAIS ---
st.set_page_config(page_title="Controle de Periféricos TI", layout="wide", initial_sidebar_state="expanded")

# --- ESCONDER ELEMENTOS NATIVOS ---
esconder_elementos = """
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    [data-testid="stAppDeployButton"] {display: none;}
    [data-testid="stToolbar"] {visibility: hidden;}
    [data-testid="stDecoration"] {display: none;}
    [data-testid="collapsedControl"] {visibility: visible !important; display: flex !important;}
    </style>
"""
st.markdown(esconder_elementos, unsafe_allow_html=True)

# --- LOGO CENTRALIZADO NO TOPO DA PÁGINA ---
nome_do_logo = "logo_totvs_2025_white.png"
if os.path.exists(nome_do_logo):
    # Cria colunas para centralizar a imagem (ajuste os números se quiser o logo maior ou menor)
    c1, c2, c3 = st.columns([1, 1, 1])
    with c2:
        st.image(nome_do_logo, use_container_width=True)
else:
    st.sidebar.warning("⚠️ Logo não encontrado no GitHub.")

# --- BARRA LATERAL ---
st.sidebar.title("🏢 Unidade")
unidade_atual = st.sidebar.selectbox("Selecione a Unidade", UNIDADES)
st.sidebar.divider()

st.sidebar.title("🎮 Menu")
menu = ["📊 Dashboard", "📤 Dar Baixa (Saída)", "📥 Reposição (Entrada)", "⚙️ Gerenciar Itens", "📜 Histórico"]
choice = st.sidebar.selectbox("Opções", menu)

# --- LÓGICA DAS TELAS ---

if choice == "📊 Dashboard":
    st.title(f"Inventário Geral - {unidade_atual}")
    
    conn = sqlite3.connect('estoque_ti.db')
    df = pd.read_sql_query(f"SELECT item as 'Produto', quantidade as 'Estoque Atual', limite_minimo as 'Mínimo Aceitável' FROM produtos WHERE unidade = '{unidade_atual}' ORDER BY item ASC", conn)
    conn.close()

    if df.empty:
        st.info(f"Nenhum item cadastrado para {unidade_atual}.")
    else:
        # Exibe a tabela completa diretamente para melhor visibilidade
        st.dataframe(df, use_container_width=True, height=600)
        
        # Botão discreto para exportar o que precisa de compra
        df_compra = df[df['Estoque Atual'] <= df['Mínimo Aceitável']]
        if not df_compra.empty:
            st.divider()
            st.warning(f"Existem {len(df_compra)} itens com estoque baixo ou zerado.")
            csv = df_compra.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Baixar Lista de Itens para Reposição", csv, f"reposicao_{unidade_atual}.csv")

elif choice == "📤 Dar Baixa (Saída)":
    st.header(f"Registrar Entrega ({unidade_atual})")
    col1, col2 = st.columns(2)
    with col1:
        colaborador = st.text_input("Usuário do Colaborador").strip().upper()
        n_chamado = st.text_input("Número do Chamado").strip().upper()
    with col2:
        df_itens = pd.DataFrame(run_query("SELECT item FROM produtos WHERE unidade = ? ORDER BY item ASC", (unidade_atual,)), columns=['item'])
        item_selecionado = st.selectbox("Selecione o Periférico", df_itens['item'].tolist()) if not df_itens.empty else None
        qtd = st.number_input("Quantidade", min_value=1, step=1)

    if st.button("Confirmar Saída") and item_selecionado:
        if not colaborador or not n_chamado: 
            st.error("Preencha Usuário e Chamado.")
        else:
            saldo = run_query("SELECT quantidade FROM produtos WHERE unidade = ? AND item = ?", (unidade_atual, item_selecionado))[0][0]
            if saldo >= qtd:
                run_query("UPDATE produtos SET quantidade = quantidade - ? WHERE unidade = ? AND item = ?", (qtd, unidade_atual, item_selecionado), True)
                run_query("INSERT INTO historico (unidade, colaborador, item, data, tipo, chamado, quantidade) VALUES (?, ?, ?, ?, ?, ?, ?)", 
                          (unidade_atual, colaborador, item_selecionado, datetime.now().strftime("%d/%m/%Y %H:%M"), "SAÍDA", n_chamado, qtd), True)
                st.toast(f"✅ Saída Confirmada!")
                st.success(f"Registrado: {qtd}x {item_selecionado} para {colaborador}")
                st.balloons()
            else: st.error("Estoque insuficiente.")

elif choice == "📥 Reposição (Entrada)":
    st.header(f"Entrada de Material ({unidade_atual})")
    df_itens = pd.DataFrame(run_query("SELECT item FROM produtos WHERE unidade = ? ORDER BY item ASC", (unidade_atual,)), columns=['item'])
    if not df_itens.empty:
        item_add = st.selectbox("Selecione o Item", df_itens['item'].tolist())
        qtd_add = st.number_input("Quantidade Adquirida", min_value=1, step=1)
        if st.button("Adicionar ao Estoque"):
            run_query("UPDATE produtos SET quantidade = quantidade + ? WHERE unidade = ? AND item = ?", (qtd_add, unidade_atual, item_add), True)
            run_query("INSERT INTO historico (unidade, colaborador, item, data, tipo, chamado, quantidade) VALUES (?, ?, ?, ?, ?, ?, ?)", 
                      (unidade_atual, "REPOSIÇÃO", item_add, datetime.now().strftime("%d/%m/%Y %H:%M"), "ENTRADA", "N/A", qtd_add), True)
            st.toast("📥 Estoque Atualizado!")
            st.success(f"Adicionado {qtd_add} unidades ao item {item_add}.")

elif choice == "⚙️ Gerenciar Itens":
    st.header(f"Gestão de Catálogo - {unidade_atual}")
    t1, t2, t3, t4, t5, t6 = st.tabs(["🆕 Novo", "✏️ Limites", "📝 Renomear", "🗑️ Remover", "🧹 Histórico", "🚀 Reset"])
    
    df_itens = pd.DataFrame(run_query("SELECT * FROM produtos WHERE unidade = ? ORDER BY item ASC", (unidade_atual,)), columns=['unidade', 'item', 'quantidade', 'limite_minimo'])

    with t1:
        n_item = st.text_input("Nome do Periférico")
        n_qtd = st.number_input("Qtd Inicial", min_value=0)
        n_lim = st.number_input("Limite de Alerta", min_value=1, value=5)
        if st.button("Salvar Novo"):
            run_query("INSERT OR IGNORE INTO produtos VALUES (?, ?, ?, ?)", (unidade_atual, n_item, n_qtd, n_lim), True)
            st.success("Item cadastrado com sucesso!")
            st.rerun()

    with t2:
        if not df_itens.empty:
            item_edit = st.selectbox("Editar configurações de:", df_itens['item'].tolist())
            atual = df_itens[df_itens['item'] == item_edit].iloc[0]
            nova_q = st.number_input("Ajustar Quantidade", value=int(atual['quantidade']))
            novo_l = st.number_input("Ajustar Mínimo", value=int(atual['limite_minimo']))
            if st.button("Salvar Alterações"):
                run_query("UPDATE produtos SET quantidade = ?, limite_minimo = ? WHERE unidade = ? AND item = ?", (nova_q, novo_l, unidade_atual, item_edit), True)
                st.success("Configurações atualizadas!")

    with t3:
        if not df_itens.empty:
            item_r = st.selectbox("Renomear:", df_itens['item'].tolist(), key="r1")
            novo_n = st.text_input("Novo Nome")
            if st.button("Confirmar Novo Nome"):
                run_query("UPDATE produtos SET item = ? WHERE unidade = ? AND item = ?", (novo_n, unidade_atual, item_r), True)
                run_query("UPDATE historico SET item = ? WHERE unidade = ? AND item = ?", (novo_n, unidade_atual, item_r), True)
                st.rerun()

    with t4:
        if not df_itens.empty:
            item_d = st.selectbox("Remover:", df_itens['item'].tolist(), key="d1")
            if st.checkbox(f"Confirmar exclusão definitiva de {item_d}"):
                if st.button("Deletar"):
                    run_query("DELETE FROM produtos WHERE unidade = ? AND item = ?", (unidade_atual, item_d), True)
                    st.rerun()

    with t5:
        senha_h = st.text_input("Senha Admin (Limpar Histórico)", type="password")
        if senha_h == SENHA_ADMIN:
            if st.button("Apagar Histórico desta Unidade"):
                run_query("DELETE FROM historico WHERE unidade = ?", (unidade_atual,), True)
                st.rerun()

    with t6:
        senha_r = st.text_input("Senha Admin (Reset Total)", type="password")
        if senha_r == SENHA_ADMIN:
            if st.text_input("Digite CONFIRMAR:").upper() == "CONFIRMAR":
                if st.button("RESETAR CATALOGO"):
                    run_query("DELETE FROM produtos WHERE unidade = ?", (unidade_atual,), True)
                    st.rerun()

elif choice == "📜 Histórico":
    st.header(f"Histórico de Movimentações - {unidade_atual}")
    busca = st.text_input("🔍 Pesquisar por Usuário, Item ou Chamado").upper()
    
    conn = sqlite3.connect('estoque_ti.db')
    df_hist = pd.read_sql_query(f"SELECT colaborador as 'Usuário', item as 'Item', quantidade as 'Qtd', data as 'Data/Hora', tipo as 'Operação', chamado as 'Chamado' FROM historico WHERE unidade = '{unidade_atual}' ORDER BY id DESC", conn)
    conn.close()
    
    if busca:
        df_hist = df_hist[df_hist['Usuário'].str.contains(busca, na=False) | df_hist['Item'].str.upper().str.contains(busca, na=False) | df_hist['Chamado'].str.contains(busca, na=False)]
    
    if not df_hist.empty:
        ex = to_excel(df_hist)
        st.download_button("📥 Exportar Histórico para Excel", ex, f"historico_{unidade_atual}.xlsx")
    
    st.dataframe(df_hist, use_container_width=True)
