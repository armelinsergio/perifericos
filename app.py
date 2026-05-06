import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
import io

# --- LISTA DE UNIDADES (Edite os nomes aqui) ---
UNIDADES = ["MATRIZ", "RIO DE JANEIRO", "JOINVILLE"]

# --- CONFIGURAÇÃO DO BANCO DE DADOS ---
def init_db():
    conn = sqlite3.connect('estoque_ti.db')
    c = conn.cursor()
    
    # Criação das tabelas
    c.execute('''CREATE TABLE IF NOT EXISTS produtos 
                 (unidade TEXT, item TEXT, quantidade INTEGER, limite_minimo INTEGER, PRIMARY KEY (unidade, item))''')
    c.execute('''CREATE TABLE IF NOT EXISTS historico 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, unidade TEXT, colaborador TEXT, item TEXT, data TEXT, tipo TEXT, chamado TEXT, quantidade INTEGER)''')
    
    # Migrações automáticas de estrutura
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
SENHA_ADMIN = "admin123"  # <--- Altere sua senha aqui

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

# --- INTERFACE ---
st.set_page_config(page_title="Controle de Periféricos TI", layout="wide")

# Barra Lateral
st.sidebar.title("🏢 Unidade de Operação")
unidade_atual = st.sidebar.selectbox("Selecione a Unidade", UNIDADES)
st.sidebar.divider()
st.sidebar.title("🎮 Menu Principal")
menu = ["📊 Dashboard", "📤 Dar Baixa (Saída)", "📥 Reposição (Entrada)", "⚙️ Gerenciar Itens", "📜 Histórico"]
choice = st.sidebar.selectbox("Selecione uma opção", menu)

# --- LÓGICA DAS TELAS ---

if choice == "📊 Dashboard":
    st.title(f"Painel de Controle - {unidade_atual}")
    conn = sqlite3.connect('estoque_ti.db')
    df = pd.read_sql_query(f"SELECT item, quantidade, limite_minimo FROM produtos WHERE unidade = '{unidade_atual}' ORDER BY item ASC", conn)
    conn.close()

    if df.empty:
        st.info(f"Nenhum item cadastrado para {unidade_atual}. Vá em 'Gerenciar Itens' para cadastrar o estoque local.")
    else:
        itens_zerados = df[df['quantidade'] == 0]
        if not itens_zerados.empty:
            st.error("### 🚨 ITENS TOTALMENTE ZERADOS")
            st.table(itens_zerados[['item', 'quantidade']])
            
        reposicao = df[(df['quantidade'] <= df['limite_minimo']) & (df['quantidade'] > 0)]
        if not reposicao.empty:
            st.warning("### ⚠️ NECESSIDADE DE REPOSIÇÃO (Estoque Baixo)")
            st.dataframe(reposicao, use_container_width=True)
            csv = reposicao.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Baixar Lista de Compras", csv, f"compras_{unidade_atual}.csv", "text/csv")

        st.divider()
        st.write(f"### 📦 Inventário Geral ({unidade_atual})")
        st.dataframe(df, use_container_width=True)

elif choice == "📤 Dar Baixa (Saída)":
    st.title(f"Registrar Entrega ({unidade_atual})")
    col1, col2 = st.columns(2)
    with col1:
        colaborador = st.text_input("Usuário do Colaborador").strip().upper()
        n_chamado = st.text_input("Número do Chamado").strip().upper()
    with col2:
        df_itens = pd.DataFrame(run_query("SELECT item FROM produtos WHERE unidade = ? ORDER BY item ASC", (unidade_atual,)), columns=['item'])
        if df_itens.empty:
            st.warning("Não há itens cadastrados nesta unidade.")
            item_selecionado = None
        else:
            item_selecionado = st.selectbox("Selecione o Periférico", df_itens['item'].tolist())
        qtd = st.number_input("Quantidade a Entregar", min_value=1, step=1)

    bloquear = False
    if colaborador and item_selecionado:
        hist = run_query("SELECT data FROM historico WHERE unidade = ? AND colaborador = ? AND item = ? AND tipo = 'SAÍDA'", (unidade_atual, colaborador, item_selecionado))
        if hist:
            st.warning(f"🛑 CUIDADO: O usuário **{colaborador}** já recebeu este item em {hist[0][0]}.")
            if not st.checkbox("Autorizar nova entrega"): bloquear = True

    if st.button("Confirmar Baixa") and item_selecionado:
        if not colaborador or not n_chamado: st.error("Preencha Usuário e Chamado.")
        elif bloquear: st.error("Autorização necessária.")
        else:
            saldo_query = run_query("SELECT quantidade FROM produtos WHERE unidade = ? AND item = ?", (unidade_atual, item_selecionado))
            saldo = saldo_query[0][0]
            if saldo >= qtd:
                run_query("UPDATE produtos SET quantidade = quantidade - ? WHERE unidade = ? AND item = ?", (qtd, unidade_atual, item_selecionado), True)
                run_query("INSERT INTO historico (unidade, colaborador, item, data, tipo, chamado, quantidade) VALUES (?, ?, ?, ?, ?, ?, ?)", 
                          (unidade_atual, colaborador, item_selecionado, datetime.now().strftime("%d/%m/%Y %H:%M"), "SAÍDA", n_chamado, qtd), True)
                st.success(f"Baixa registrada em {unidade_atual}!")
                st.balloons()
            else: st.error(f"Estoque insuficiente ({saldo} unidades).")

elif choice == "📥 Reposição (Entrada)":
    st.title(f"Entrada de Itens ({unidade_atual})")
    df_itens = pd.DataFrame(run_query("SELECT item FROM produtos WHERE unidade = ? ORDER BY item ASC", (unidade_atual,)), columns=['item'])
    if df_itens.empty:
        st.warning("Cadastre itens na unidade antes de dar entrada.")
    else:
        item_add = st.selectbox("Selecione o Item", df_itens['item'].tolist())
        qtd_add = st.number_input("Quantidade Adquirida", min_value=1, step=1)
        if st.button("Adicionar ao Estoque"):
            run_query("UPDATE produtos SET quantidade = quantidade + ? WHERE unidade = ? AND item = ?", (qtd_add, unidade_atual, item_add), True)
            run_query("INSERT INTO historico (unidade, colaborador, item, data, tipo, chamado, quantidade) VALUES (?, ?, ?, ?, ?, ?, ?)", 
                      (unidade_atual, "REPOSIÇÃO", item_add, datetime.now().strftime("%d/%m/%Y %H:%M"), "ENTRADA", "N/A", qtd_add), True)
            st.success("Estoque atualizado!")

elif choice == "⚙️ Gerenciar Itens":
    st.title(f"Gerenciamento - {unidade_atual}")
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["🆕 Cadastrar", "✏️ Editar Limites", "📝 Renomear", "🗑️ Remover", "🧹 Zerar Histórico", "🚀 Resetar Unidade"])
    
    # Carrega dados para uso nas abas
    df_itens = pd.DataFrame(run_query("SELECT * FROM produtos WHERE unidade = ? ORDER BY item ASC", (unidade_atual,)), columns=['unidade', 'item', 'quantidade', 'limite_minimo'])

    with tab1:
        st.subheader("Cadastrar Novo Item")
        n_item = st.text_input("Nome do Periférico").strip()
        n_qtd = st.number_input("Qtd Inicial", min_value=0)
        n_lim = st.number_input("Limite de Alerta", min_value=1, value=5)
        if st.button("Cadastrar"):
            run_query("INSERT OR IGNORE INTO produtos VALUES (?, ?, ?, ?)", (unidade_atual, n_item, n_qtd, n_lim), True)
            st.success(f"'{n_item}' cadastrado!")
            st.rerun()

    with tab2:
        if not df_itens.empty:
            item_edit = st.selectbox("Selecione para editar", df_itens['item'].tolist())
            atual = df_itens[df_itens['item'] == item_edit].iloc[0]
            nova_qtd_edit = st.number_input("Ajustar Quantidade Atual", value=int(atual['quantidade']))
            novo_lim_edit = st.number_input("Definir Novo Limite Mínimo", value=int(atual['limite_minimo']))
            if st.button("Salvar Alterações"):
                run_query("UPDATE produtos SET quantidade = ?, limite_minimo = ? WHERE unidade = ? AND item = ?", (nova_qtd_edit, novo_lim_edit, unidade_atual, item_edit), True)
                st.success("Configurações atualizadas!")
                st.rerun()

    with tab3:
        if not df_itens.empty:
            item_ren = st.selectbox("Item para renomear", df_itens['item'].tolist(), key="ren1")
            novo_n = st.text_input("Novo nome").strip()
            if st.button("Confirmar Novo Nome"):
                if novo_n:
                    run_query("UPDATE produtos SET item = ? WHERE unidade = ? AND item = ?", (novo_n, unidade_atual, item_ren), True)
                    run_query("UPDATE historico SET item = ? WHERE unidade = ? AND item = ?", (novo_n, unidade_atual, item_ren), True)
                    st.success("Item renomeado com sucesso!")
                    st.rerun()

    with tab4:
        if not df_itens.empty:
            item_del = st.selectbox("Item para remover", df_itens['item'].tolist(), key="del1")
            if st.checkbox(f"Confirmo a remoção permanente de {item_del}"):
                if st.button("Excluir Item"):
                    run_query("DELETE FROM produtos WHERE unidade = ? AND item = ?", (unidade_atual, item_del), True)
                    st.success("Item removido.")
                    st.rerun()

    with tab5:
        st.subheader("🧹 Limpar Histórico de Movimentações")
        st.warning("Esta ação apagará todos os registros da aba Histórico para esta unidade. O saldo atual do estoque não será alterado.")
        
        senha_h = st.text_input("Senha Admin (Histórico)", type="password", key="pwd_hist")
        if senha_h == SENHA_ADMIN:
            conf_h = st.checkbox("Confirmo que desejo apagar o histórico desta unidade.")
            if st.button("APAGAR HISTÓRICO AGORA"):
                if conf_h:
                    run_query("DELETE FROM historico WHERE unidade = ?", (unidade_atual,), True)
                    # Gera log de limpeza
                    run_query("INSERT INTO historico (unidade, colaborador, item, data, tipo, chamado, quantidade) VALUES (?, 'SISTEMA', 'LIMPEZA HISTÓRICO', ?, 'LOG', 'ADMIN', 0)", 
                              (unidade_atual, datetime.now().strftime("%d/%m/%Y %H:%M")), True)
                    st.success("Histórico limpo!")
                    st.rerun()
                else:
                    st.error("Você precisa marcar a caixa de confirmação.")

    with tab6:
        st.subheader("🚀 Resetar Catálogo da Unidade")
        st.error(f"CUIDADO: Isso apagará TODOS os itens e quantidades da unidade {unidade_atual}.")
        
        senha_r = st.text_input("Senha Admin (Catálogo)", type="password", key="pwd_cat")
        if senha_r == SENHA_ADMIN:
            st.info("Para confirmar, digite a palavra **CONFIRMAR**:")
            palavra_c = st.text_input("Palavra de confirmação:").strip().upper()
            if palavra_c == "CONFIRMAR":
                if st.button("RESETAR CATÁLOGO IRREVERSIVELMENTE"):
                    run_query("DELETE FROM produtos WHERE unidade = ?", (unidade_atual,), True)
                    # Registra log
                    run_query("INSERT INTO historico (unidade, colaborador, item, data, tipo, chamado, quantidade) VALUES (?, 'SISTEMA', 'RESET DE CATÁLOGO', ?, 'LOG', 'ADMIN', 0)", 
                              (unidade_atual, datetime.now().strftime("%d/%m/%Y %H:%M")), True)
                    st.success("Unidade resetada!")
                    st.rerun()

elif choice == "📜 Histórico":
    st.title(f"Histórico - {unidade_atual}")
    
    col_busca, col_excel = st.columns([3, 1])
    with col_busca:
        busca = st.text_input("🔍 Buscar (Usuário, Item ou Chamado)").strip().upper()
    
    conn = sqlite3.connect('estoque_ti.db')
    df_hist = pd.read_sql_query(f"SELECT colaborador, item, quantidade, data, tipo, chamado FROM historico WHERE unidade = '{unidade_atual}' ORDER BY id DESC", conn)
    conn.close()
    
    if busca:
        df_hist = df_hist[df_hist['colaborador'].str.contains(busca, na=False) | 
                          df_hist['item'].str.upper().str.contains(busca, na=False) | 
                          df_hist['chamado'].str.contains(busca, na=False)]
    
    with col_excel:
        if not df_hist.empty:
            excel_data = to_excel(df_hist)
            st.download_button("📥 Baixar Excel", excel_data, f"hist_{unidade_atual}.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    
    st.dataframe(df_hist, use_container_width=True)
