import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime

# --- CONFIGURAÇÃO DO BANCO DE DADOS ---
def init_db():
    conn = sqlite3.connect('estoque_ti.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS produtos 
                 (item TEXT PRIMARY KEY, quantidade INTEGER, limite_minimo INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS historico 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, colaborador TEXT, item TEXT, data TEXT, tipo TEXT)''')
    
    itens_iniciais = [
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
    c.executemany('INSERT OR IGNORE INTO produtos VALUES (?, ?, ?)', itens_iniciais)
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

st.sidebar.title("Navegação")
menu = ["📊 Dashboard", "📤 Dar Baixa (Saída)", "📥 Reposição (Entrada)", "⚙️ Gerenciar Itens", "📜 Histórico"]
choice = st.sidebar.selectbox("Escolha uma opção", menu)

if choice == "📊 Dashboard":
    st.title("Estado Atual do Estoque")
    conn = sqlite3.connect('estoque_ti.db')
    df = pd.read_sql_query("SELECT * FROM produtos ORDER BY item ASC", conn)
    conn.close()

    estoque_baixo = df[df['quantidade'] <= df['limite_minimo']]
    if not estoque_baixo.empty:
        st.error(f"⚠️ Atenção! {len(estoque_baixo)} itens precisam de reposição.")
        st.dataframe(estoque_baixo, use_container_width=True)

    st.divider()
    st.write("### Inventário Geral")
    st.dataframe(df, use_container_width=True)

elif choice == "📤 Dar Baixa (Saída)":
    st.title("Registrar Entrega")
    colaborador = st.text_input("Usuário do Colaborador").strip().upper()
    df_itens = pd.DataFrame(run_query("SELECT item FROM produtos ORDER BY item ASC"), columns=['item'])
    item_selecionado = st.selectbox("Selecione o Periférico", df_itens['item'].tolist())
    qtd = st.number_input("Quantidade", min_value=1, step=1)

    bloquear_entrega = False
    if colaborador:
        historico = run_query("SELECT data FROM historico WHERE colaborador = ? AND item = ? AND tipo = 'SAÍDA'", (colaborador, item_selecionado))
        if historico:
            st.warning(f"🛑 CUIDADO: O usuário **{colaborador}** já recebeu este item em {historico[0][0]}.")
            autorizar = st.checkbox("Autorizar nova entrega deste item.")
            if not autorizar:
                bloquear_entrega = True

    if st.button("Confirmar Baixa"):
        if not colaborador: st.error("Insira o usuário.")
        elif bloquear_entrega: st.error("Marque a autorização.")
        else:
            saldo = run_query("SELECT quantidade FROM produtos WHERE item = ?", (item_selecionado,))[0][0]
            if saldo >= qtd:
                run_query("UPDATE produtos SET quantidade = quantidade - ? WHERE item = ?", (qtd, item_selecionado), True)
                run_query("INSERT INTO historico (colaborador, item, data, tipo) VALUES (?, ?, ?, ?)", 
                          (colaborador, item_selecionado, datetime.now().strftime("%d/%m/%Y %H:%M"), "SAÍDA"), True)
                st.success("Baixa realizada!")
                st.balloons()
            else: st.error(f"Saldo insuficiente ({saldo} unidades).")

elif choice == "📥 Reposição (Entrada)":
    st.title("Entrada de Itens")
    df_itens = pd.DataFrame(run_query("SELECT item FROM produtos ORDER BY item ASC"), columns=['item'])
    item_add = st.selectbox("Selecione o Item", df_itens['item'].tolist())
    qtd_add = st.number_input("Quantidade Adquirida", min_value=1, step=1)
    if st.button("Adicionar ao Estoque"):
        run_query("UPDATE produtos SET quantidade = quantidade + ? WHERE item = ?", (qtd_add, item_add), True)
        run_query("INSERT INTO historico (colaborador, item, data, tipo) VALUES (?, ?, ?, ?)", 
                  ("REPOSIÇÃO", item_add, datetime.now().strftime("%d/%m/%Y %H:%M"), "ENTRADA"), True)
        st.success("Estoque atualizado!")

elif choice == "⚙️ Gerenciar Itens":
    st.title("Gerenciamento de Periféricos")
    
    tab1, tab2 = st.tabs(["🆕 Cadastrar Novo", "🗑️ Remover Item"])
    
    with tab1:
        st.subheader("Cadastrar Novo Item")
        novo_nome = st.text_input("Nome do Periférico").strip()
        nova_qtd = st.number_input("Qtd Inicial", min_value=0, step=1)
        novo_limite = st.number_input("Limite Alerta", min_value=1, value=2)
        if st.button("Salvar Novo Item"):
            if novo_nome:
                try:
                    run_query("INSERT INTO produtos VALUES (?, ?, ?)", (novo_nome, nova_qtd, novo_limite), True)
                    st.success(f"'{novo_nome}' adicionado!")
                except: st.error("Item já existe.")
            else: st.error("Nome vazio.")

    with tab2:
        st.subheader("Excluir Item do Controle")
        df_itens = pd.DataFrame(run_query("SELECT item FROM produtos ORDER BY item ASC"), columns=['item'])
        item_para_remover = st.selectbox("Selecione o item para REMOVER PERMANENTEMENTE", df_itens['item'].tolist())
        
        st.warning(f"Atenção: Remover '{item_para_remover}' apagará o saldo deste item, mas manterá o registro no histórico.")
        confirmar_exclusao = st.checkbox(f"Eu confirmo que não usaremos mais '{item_para_remover}'")
        
        if st.button("Remover Item"):
            if confirmar_exclusao:
                run_query("DELETE FROM produtos WHERE item = ?", (item_para_remover,), True)
                st.success(f"Item '{item_para_remover}' removido com sucesso!")
                st.rerun() # Atualiza a tela
            else:
                st.error("Marque a confirmação para excluir.")

elif choice == "📜 Histórico":
    st.title("Histórico de Movimentações")
    
    # BUSCA NO HISTÓRICO
    busca = st.text_input("🔍 Buscar por Colaborador ou Item").strip().upper()
    
    conn = sqlite3.connect('estoque_ti.db')
    df_hist = pd.read_sql_query("SELECT colaborador, item, data, tipo FROM historico ORDER BY id DESC", conn)
    conn.close()

    if busca:
        # Filtra se o texto da busca estiver no colaborador ou no item
        df_hist = df_hist[df_hist['colaborador'].str.contains(busca) | df_hist['item'].str.upper().str.contains(busca)]

    st.dataframe(df_hist, use_container_width=True)
