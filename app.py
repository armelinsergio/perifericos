import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime

# --- CONFIGURAÇÃO DO BANCO DE DADOS ---
def init_db():
    conn = sqlite3.connect('estoque_ti.db')
    c = conn.cursor()
    # Tabela de Produtos
    c.execute('''CREATE TABLE IF NOT EXISTS produtos 
                 (item TEXT PRIMARY KEY, quantidade INTEGER, limite_minimo INTEGER)''')
    # Tabela de Histórico
    c.execute('''CREATE TABLE IF NOT EXISTS historico 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, colaborador TEXT, item TEXT, data TEXT, tipo TEXT, chamado TEXT, quantidade INTEGER)''')
    
    # Migrações automáticas (Adiciona colunas se não existirem)
    try: c.execute("ALTER TABLE historico ADD COLUMN chamado TEXT")
    except: pass
    try: c.execute("ALTER TABLE historico ADD COLUMN quantidade INTEGER")
    except: pass
    
    conn.commit()
    conn.close()

init_db()

# --- FUNÇÕES DE BANCO ---
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

# --- INTERFACE ---
st.set_page_config(page_title="Controle de Periféricos TI", layout="wide")

st.sidebar.title("🎮 Menu Principal")
menu = ["📊 Dashboard", "📤 Dar Baixa (Saída)", "📥 Reposição (Entrada)", "⚙️ Gerenciar Itens", "📜 Histórico"]
choice = st.sidebar.selectbox("Selecione uma opção", menu)

if choice == "📊 Dashboard":
    st.title("Painel de Controle de Estoque")
    
    conn = sqlite3.connect('estoque_ti.db')
    df = pd.read_sql_query("SELECT * FROM produtos ORDER BY item ASC", conn)
    conn.close()

    # 1. SEÇÃO DE ITENS ZERADOS
    itens_zerados = df[df['quantidade'] == 0]
    if not itens_zerados.empty:
        st.error("### 🚨 ITENS TOTALMENTE ZERADOS")
        st.table(itens_zerados[['item', 'quantidade']])
        
    # 2. SEÇÃO DE REPOSIÇÃO
    reposicao = df[(df['quantidade'] <= df['limite_minimo']) & (df['quantidade'] > 0)]
    if not reposicao.empty:
        st.warning("### ⚠️ NECESSIDADE DE REPOSIÇÃO (Estoque Baixo)")
        st.dataframe(reposicao, use_container_width=True)
        csv = reposicao.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Baixar Lista de Compras (CSV)", csv, "lista_compras.csv", "text/csv")

    st.divider()
    st.write("### 📦 Inventário Geral")
    st.dataframe(df, use_container_width=True)

elif choice == "📤 Dar Baixa (Saída)":
    st.title("Registrar Entrega")
    col1, col2 = st.columns(2)
    with col1:
        colaborador = st.text_input("Usuário do Colaborador").strip().upper()
        n_chamado = st.text_input("Número do Chamado").strip().upper()
    with col2:
        df_itens = pd.DataFrame(run_query("SELECT item FROM produtos ORDER BY item ASC"), columns=['item'])
        item_selecionado = st.selectbox("Selecione o Periférico", df_itens['item'].tolist())
        qtd = st.number_input("Quantidade a Entregar", min_value=1, step=1)

    bloquear = False
    if colaborador:
        hist = run_query("SELECT data FROM historico WHERE colaborador = ? AND item = ? AND tipo = 'SAÍDA'", (colaborador, item_selecionado))
        if hist:
            st.warning(f"🛑 CUIDADO: O usuário **{colaborador}** já recebeu este item em {hist[0][0]}.")
            if not st.checkbox("Autorizar nova entrega"): bloquear = True

    if st.button("Confirmar Baixa"):
        if not colaborador or not n_chamado: st.error("Preencha Usuário e Chamado.")
        elif bloquear: st.error("Autorização necessária.")
        else:
            saldo = run_query("SELECT quantidade FROM produtos WHERE item = ?", (item_selecionado,))[0][0]
            if saldo >= qtd:
                run_query("UPDATE produtos SET quantidade = quantidade - ? WHERE item = ?", (qtd, item_selecionado), True)
                # GRAVAÇÃO COM QUANTIDADE NO HISTÓRICO
                run_query("INSERT INTO historico (colaborador, item, data, tipo, chamado, quantidade) VALUES (?, ?, ?, ?, ?, ?)", 
                          (colaborador, item_selecionado, datetime.now().strftime("%d/%m/%Y %H:%M"), "SAÍDA", n_chamado, qtd), True)
                st.success(f"Baixa de {qtd} unidade(s) efetuada! Chamado: {n_chamado}")
                st.balloons()
            else: st.error(f"Estoque insuficiente ({saldo} unidades).")

elif choice == "📥 Reposição (Entrada)":
    st.title("Entrada de Itens")
    df_itens = pd.DataFrame(run_query("SELECT item FROM produtos ORDER BY item ASC"), columns=['item'])
    item_add = st.selectbox("Selecione o Item", df_itens['item'].tolist())
    qtd_add = st.number_input("Quantidade Adquirida", min_value=1, step=1)
    if st.button("Adicionar ao Estoque"):
        run_query("UPDATE produtos SET quantidade = quantidade + ? WHERE item = ?", (qtd_add, item_add), True)
        # GRAVAÇÃO COM QUANTIDADE NO HISTÓRICO
        run_query("INSERT INTO historico (colaborador, item, data, tipo, chamado, quantidade) VALUES (?, ?, ?, ?, ?, ?)", 
                  ("REPOSIÇÃO", item_add, datetime.now().strftime("%d/%m/%Y %H:%M"), "ENTRADA", "N/A", qtd_add), True)
        st.success(f"Entrada de {qtd_add} unidades de {item_add} registrada!")

elif choice == "⚙️ Gerenciar Itens":
    st.title("Gerenciamento do Catálogo")
    tab1, tab2, tab3 = st.tabs(["🆕 Cadastrar", "✏️ Editar Limites", "🗑️ Remover"])
    
    with tab1:
        st.subheader("Novo Periférico")
        n_item = st.text_input("Nome").strip()
        n_qtd = st.number_input("Qtd Inicial", min_value=0)
        n_lim = st.number_input("Limite de Alerta", min_value=1, value=5)
        if st.button("Cadastrar Item"):
            try:
                run_query("INSERT INTO produtos VALUES (?, ?, ?)", (n_item, n_qtd, n_lim), True)
                st.success("Cadastrado!")
            except: st.error("Item já existe.")

    with tab2:
        st.subheader("Alterar Limite Mínimo ou Quantidade")
        df_itens = pd.DataFrame(run_query("SELECT * FROM produtos ORDER BY item ASC"), columns=['item', 'quantidade', 'limite_minimo'])
        item_edit = st.selectbox("Selecione para editar", df_itens['item'].tolist())
        atual = df_itens[df_itens['item'] == item_edit].iloc[0]
        nova_qtd_edit = st.number_input("Ajustar Quantidade Atual", value=int(atual['quantidade']))
        novo_lim_edit = st.number_input("Definir Novo Limite Mínimo", value=int(atual['limite_minimo']))
        if st.button("Atualizar Configurações"):
            run_query("UPDATE produtos SET quantidade = ?, limite_minimo = ? WHERE item = ?", (nova_qtd_edit, novo_lim_edit, item_edit), True)
            st.success("Atualizado!")
            st.rerun()

    with tab3:
        st.subheader("Excluir do Sistema")
        item_del = st.selectbox("Remover item", df_itens['item'].tolist())
        if st.checkbox(f"Confirmar exclusão de {item_del}"):
            if st.button("Remover Permanentemente"):
                run_query("DELETE FROM produtos WHERE item = ?", (item_del,), True)
                st.success("Removido!")
                st.rerun()

elif choice == "📜 Histórico":
    st.title("Histórico de Movimentações")
    busca = st.text_input("🔍 Buscar (Usuário, Item ou Chamado)").strip().upper()
    conn = sqlite3.connect('estoque_ti.db')
    # ADICIONADO A COLUNA QUANTIDADE NA CONSULTA
    df_hist = pd.read_sql_query("SELECT colaborador, item, quantidade, data, tipo, chamado FROM historico ORDER BY id DESC", conn)
    conn.close()
    if busca:
        df_hist = df_hist[df_hist['colaborador'].str.contains(busca) | df_hist['item'].str.upper().str.contains(busca) | df_hist['chamado'].str.contains(busca)]
    
    st.dataframe(df_hist, use_container_width=True)
