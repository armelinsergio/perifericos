import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
import io

# --- LISTA DE UNIDADES (EDITE AQUI COM OS NOMES DAS SUAS FILIAIS/UNIDADES) ---
UNIDADES = ["MATRIZ", "BELO HORIZONTE", "RIO DE JANEIRO", "CASCAVEL", "MARINGA", "JOINVILLE"]

# --- CONFIGURAÇÃO DO BANCO DE DADOS ---
def init_db():
    conn = sqlite3.connect('estoque_ti.db')
    c = conn.cursor()
    
    # 1. Tenta criar as tabelas no novo formato (se for banco novo)
    c.execute('''CREATE TABLE IF NOT EXISTS produtos 
                 (unidade TEXT, item TEXT, quantidade INTEGER, limite_minimo INTEGER, PRIMARY KEY (unidade, item))''')
    c.execute('''CREATE TABLE IF NOT EXISTS historico 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, unidade TEXT, colaborador TEXT, item TEXT, data TEXT, tipo TEXT, chamado TEXT, quantidade INTEGER)''')
    
    # 2. SISTEMA DE MIGRAÇÃO (Caso você já tenha a tabela antiga sem a coluna "unidade")
    c.execute("PRAGMA table_info(produtos)")
    colunas_produtos = [col[1] for col in c.fetchall()]
    if 'unidade' not in colunas_produtos:
        # Se a tabela for a antiga, cria uma nova, copia os dados e marca tudo como "MATRIZ"
        c.execute('''CREATE TABLE produtos_novo 
                     (unidade TEXT, item TEXT, quantidade INTEGER, limite_minimo INTEGER, PRIMARY KEY (unidade, item))''')
        c.execute("INSERT INTO produtos_novo (unidade, item, quantidade, limite_minimo) SELECT 'MATRIZ', item, quantidade, limite_minimo FROM produtos")
        c.execute("DROP TABLE produtos")
        c.execute("ALTER TABLE produtos_novo RENAME TO produtos")

    # Atualizações na tabela histórico
    try: c.execute("ALTER TABLE historico ADD COLUMN chamado TEXT")
    except: pass
    try: c.execute("ALTER TABLE historico ADD COLUMN quantidade INTEGER")
    except: pass
    try: c.execute("ALTER TABLE historico ADD COLUMN unidade TEXT DEFAULT 'MATRIZ'")
    except: pass

    # 3. Cadastro Inicial para TODAS as unidades
    itens_padrao = [
        ('Headset de 2 lados', 0, 5), ('Teclado', 0, 5), ('Mouse', 0, 5),
        ('Headset de 1 lado', 0, 5), ('Monitor', 0, 2), ('Memoria 16gb ddr4', 0, 3),
        ('ssd m2 512gb', 0, 3), ('HDMI', 0, 10), ('ssd 2tb', 0, 2),
        ('DockStation', 0, 2), ('Pen Drive 64gb', 0, 5), ('HD externo 2tb', 0, 2),
        ('Adaptador Tipo-C Macbook', 0, 3), ('Mouse sem Fio', 0, 5), ('headphone sem fio', 0, 2),
        ('Kit teclado e mouse sem fio', 0, 3), ('Filtro de privacidade 13.3x16:10', 0, 2),
        ('filtro de privacidade 14"x16:9', 0, 2), ('filtro de privacidade 14"16:10', 0, 2),
        ('Trava HP', 0, 5), ('HUB USB', 0, 5), ('Trava dell 3420', 0, 3),
        ('trava E14 Gen 2', 0, 3), ('Trava Lenovo G4', 0, 3)
    ]
    
    # Insere os itens básicos em cada uma das unidades cadastradas
    itens_com_unidade = []
    for unid in UNIDADES:
        for item in itens_padrao:
            itens_com_unidade.append((unid, item[0], item[1], item[2]))
            
    c.executemany('INSERT OR IGNORE INTO produtos VALUES (?, ?, ?, ?)', itens_com_unidade)
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

# --- INTERFACE ---
st.set_page_config(page_title="Controle de Periféricos TI", layout="wide")

# ================= MENU LATERAL & SELEÇÃO DE UNIDADE =================
st.sidebar.title("🏢 Unidade de Operação")
unidade_atual = st.sidebar.selectbox("Selecione a Unidade", UNIDADES)
st.sidebar.divider()

st.sidebar.title("🎮 Menu Principal")
menu = ["📊 Dashboard", "📤 Dar Baixa (Saída)", "📥 Reposição (Entrada)", "⚙️ Gerenciar Itens", "📜 Histórico"]
choice = st.sidebar.selectbox("Selecione uma opção", menu)

# ================= TELAS DO SISTEMA =================

if choice == "📊 Dashboard":
    st.title(f"Painel de Controle - {unidade_atual}")
    conn = sqlite3.connect('estoque_ti.db')
    df = pd.read_sql_query(f"SELECT item, quantidade, limite_minimo FROM produtos WHERE unidade = '{unidade_atual}' ORDER BY item ASC", conn)
    conn.close()

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
        item_selecionado = st.selectbox("Selecione o Periférico", df_itens['item'].tolist())
        qtd = st.number_input("Quantidade a Entregar", min_value=1, step=1)

    bloquear = False
    if colaborador:
        hist = run_query("SELECT data FROM historico WHERE unidade = ? AND colaborador = ? AND item = ? AND tipo = 'SAÍDA'", (unidade_atual, colaborador, item_selecionado))
        if hist:
            st.warning(f"🛑 CUIDADO: O usuário **{colaborador}** já recebeu este item em {hist[0][0]} nesta unidade.")
            if not st.checkbox("Autorizar nova entrega"): bloquear = True

    if st.button("Confirmar Baixa"):
        if not colaborador or not n_chamado: st.error("Preencha Usuário e Chamado.")
        elif bloquear: st.error("Autorização necessária.")
        else:
            saldo = run_query("SELECT quantidade FROM produtos WHERE unidade = ? AND item = ?", (unidade_atual, item_selecionado))[0][0]
            if saldo >= qtd:
                run_query("UPDATE produtos SET quantidade = quantidade - ? WHERE unidade = ? AND item = ?", (qtd, unidade_atual, item_selecionado), True)
                run_query("INSERT INTO historico (unidade, colaborador, item, data, tipo, chamado, quantidade) VALUES (?, ?, ?, ?, ?, ?, ?)", 
                          (unidade_atual, colaborador, item_selecionado, datetime.now().strftime("%d/%m/%Y %H:%M"), "SAÍDA", n_chamado, qtd), True)
                st.success(f"Baixa registrada em {unidade_atual}! Chamado: {n_chamado}")
                st.balloons()
            else: st.error(f"Estoque insuficiente ({saldo} unidades).")

elif choice == "📥 Reposição (Entrada)":
    st.title(f"Entrada de Itens ({unidade_atual})")
    df_itens = pd.DataFrame(run_query("SELECT item FROM produtos WHERE unidade = ? ORDER BY item ASC", (unidade_atual,)), columns=['item'])
    item_add = st.selectbox("Selecione o Item", df_itens['item'].tolist())
    qtd_add = st.number_input("Quantidade Adquirida", min_value=1, step=1)
    if st.button("Adicionar ao Estoque"):
        run_query("UPDATE produtos SET quantidade = quantidade + ? WHERE unidade = ? AND item = ?", (qtd_add, unidade_atual, item_add), True)
        run_query("INSERT INTO historico (unidade, colaborador, item, data, tipo, chamado, quantidade) VALUES (?, ?, ?, ?, ?, ?, ?)", 
                  (unidade_atual, "REPOSIÇÃO", item_add, datetime.now().strftime("%d/%m/%Y %H:%M"), "ENTRADA", "N/A", qtd_add), True)
        st.success("Estoque atualizado!")

elif choice == "⚙️ Gerenciar Itens":
    st.title(f"Gerenciamento do Catálogo ({unidade_atual})")
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["🆕 Cadastrar", "✏️ Editar Limites", "📝 Renomear", "🗑️ Remover", "🧹 Zerar Histórico"])
    
    with tab1:
        n_item = st.text_input("Nome").strip()
        n_qtd = st.number_input("Qtd Inicial", min_value=0)
        n_lim = st.number_input("Limite de Alerta", min_value=1, value=5)
        if st.button("Cadastrar Item"):
            try:
                run_query("INSERT INTO produtos VALUES (?, ?, ?, ?)", (unidade_atual, n_item, n_qtd, n_lim), True)
                st.success(f"Cadastrado na unidade {unidade_atual}!")
            except: st.error("Item já existe nesta unidade.")

    with tab2:
        df_itens = pd.DataFrame(run_query("SELECT * FROM produtos WHERE unidade = ? ORDER BY item ASC", (unidade_atual,)), columns=['unidade', 'item', 'quantidade', 'limite_minimo'])
        item_edit = st.selectbox("Selecione para editar", df_itens['item'].tolist())
        atual = df_itens[df_itens['item'] == item_edit].iloc[0]
        nova_qtd_edit = st.number_input("Ajustar Quantidade Atual", value=int(atual['quantidade']))
        novo_lim_edit = st.number_input("Definir Novo Limite Mínimo", value=int(atual['limite_minimo']))
        if st.button("Atualizar Configurações"):
            run_query("UPDATE produtos SET quantidade = ?, limite_minimo = ? WHERE unidade = ? AND item = ?", (nova_qtd_edit, novo_lim_edit, unidade_atual, item_edit), True)
            st.success("Atualizado!")
            st.rerun()

    with tab3:
        item_para_renomear = st.selectbox("Item atual", df_itens['item'].tolist(), key="ren1")
        novo_nome_input = st.text_input("Novo nome").strip()
        if st.button("Confirmar Renomeação"):
            if novo_nome_input:
                run_query("UPDATE produtos SET item = ? WHERE unidade = ? AND item = ?", (novo_nome_input, unidade_atual, item_para_renomear), True)
                run_query("UPDATE historico SET item = ? WHERE unidade = ? AND item = ?", (novo_nome_input, unidade_atual, item_para_renomear), True)
                st.success("Item renomeado!")
                st.rerun()

    with tab4:
        item_del = st.selectbox("Remover item", df_itens['item'].tolist(), key="del1")
        if st.checkbox(f"Confirmar exclusão de {item_del}"):
            if st.button("Remover Permanentemente"):
                run_query("DELETE FROM produtos WHERE unidade = ? AND item = ?", (unidade_atual, item_del), True)
                st.success("Removido!")
                st.rerun()
                
    with tab5:
        st.subheader("Limpar Dados da Unidade Atual")
        senha_input = st.text_input("Senha de Admin", type="password")
        if senha_input == SENHA_ADMIN:
            st.warning(f"Apagará o histórico APENAS da unidade {unidade_atual}.")
            if st.button("APAGAR HISTÓRICO"):
                run_query("DELETE FROM historico WHERE unidade = ?", (unidade_atual,), commit=True)
                run_query("INSERT INTO historico (unidade, colaborador, item, data, tipo, chamado, quantidade) VALUES (?, ?, ?, ?, ?, ?, ?)", 
                          (unidade_atual, "SISTEMA", "LIMPEZA GERAL", datetime.now().strftime("%d/%m/%Y %H:%M"), "LOG", "ADMIN", 0), True)
                st.success("Histórico zerado.")
                st.rerun()

elif choice == "📜 Histórico":
    st.title(f"Histórico - {unidade_atual}")
    
    col_busca, col_excel = st.columns([3, 1])
    with col_busca:
        busca = st.text_input("🔍 Buscar (Usuário, Item ou Chamado)").strip().upper()
    
    conn = sqlite3.connect('estoque_ti.db')
    # O histórico agora puxa e filtra APENAS pela unidade selecionada
    df_hist = pd.read_sql_query(f"SELECT colaborador, item, quantidade, data, tipo, chamado FROM historico WHERE unidade = '{unidade_atual}' ORDER BY id DESC", conn)
    conn.close()
    
    if busca:
        df_hist = df_hist[df_hist['colaborador'].str.contains(busca) | df_hist['item'].str.upper().str.contains(busca) | df_hist['chamado'].str.contains(busca)]
    
    with col_excel:
        excel_data = to_excel(df_hist)
        st.download_button(label="📥 Baixar em Excel", data=excel_data, file_name=f'historico_{unidade_atual}_{datetime.now().strftime("%Y%m%d")}.xlsx', mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

    st.dataframe(df_hist, use_container_width=True)
