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
    # Tabela de Histórico de Entregas
    c.execute('''CREATE TABLE IF NOT EXISTS historico 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, colaborador TEXT, item TEXT, data TEXT, tipo TEXT)''')
    
    # Cadastro Inicial dos seus itens (se o banco estiver vazio)
    itens_iniciais = [
        ('Headset 2 lados', 10, 3), ('Teclado', 15, 5), ('Mouse', 20, 5),
        ('Headset 1 lado', 10, 3), ('Monitor', 5, 2), ('Memoria 16gb ddr4', 10, 2),
        ('SSD M2 512gb', 10, 2), ('SSD 2tb', 5, 1), ('DockStation', 5, 1),
        ('Mouse sem Fio', 10, 3), ('Headphone sem fio', 5, 2), ('HUB USB', 10, 3)
        # ... adicione os outros aqui seguindo o padrão
    ]
    c.executemany('INSERT OR IGNORE INTO produtos VALUES (?, ?, ?)', itens_iniciais)
    conn.commit()
    conn.close()

init_db()

# --- FUNÇÕES DE AUXÍLIO ---
def get_estoque():
    conn = sqlite3.connect('estoque_ti.db')
    df = pd.read_sql_query("SELECT * FROM produtos", conn)
    conn.close()
    return df

def verificar_duplicidade(colaborador, item):
    conn = sqlite3.connect('estoque_ti.db')
    c = conn.cursor()
    c.execute("SELECT data FROM historico WHERE colaborador = ? AND item = ? AND tipo = 'SAÍDA'", (colaborador, item))
    resultado = c.fetchone()
    conn.close()
    return resultado

# --- INTERFACE ---
st.set_page_config(page_title="Gestão de Periféricos TI", layout="wide")
st.title("📦 Sistema de Controle de Periféricos")

menu = ["Dashboard", "Dar Baixa (Saída)", "Reposição (Entrada)", "Histórico"]
choice = st.sidebar.selectbox("Menu", menu)

if choice == "Dashboard":
    st.subheader("Estado Atual do Estoque")
    df = get_estoque()
    
    # Destacar itens com estoque baixo
    def highlight_low_stock(s):
        return ['background-color: #ffcccc' if s.quantidade <= s.limite_minimo else '' for _ in s]
    
    st.table(df.style.apply(highlight_low_stock, axis=1))

elif choice == "Dar Baixa (Saída)":
    st.subheader("Registrar Entrega de Periférico")
    
    colaborador = st.text_input("ID ou Nome do Colaborador").upper()
    df_estoque = get_estoque()
    item_selecionado = st.selectbox("Selecione o Periférico", df_estoque['item'].tolist())
    qtd = st.number_input("Quantidade", min_value=1, value=1)

    if colaborador:
        # LOGICA DE AVISO DE DUPLICIDADE
        ja_recebeu = verificar_duplicidade(colaborador, item_selecionado)
        if ja_recebeu:
            st.warning(f"⚠️ ATENÇÃO: O colaborador {colaborador} já recebeu este item ({item_selecionado}) no dia {ja_recebeu[0]}!")
        
    if st.button("Confirmar Entrega"):
        conn = sqlite3.connect('estoque_ti.db')
        c = conn.cursor()
        
        # Verificar se tem saldo
        c.execute("SELECT quantidade FROM produtos WHERE item = ?", (item_selecionado,))
        saldo = c.fetchone()[0]
        
        if saldo >= qtd:
            # Atualiza estoque
            c.execute("UPDATE produtos SET quantidade = quantidade - ? WHERE item = ?", (qtd, item_selecionado))
            # Grava histórico
            c.execute("INSERT INTO historico (colaborador, item, data, tipo) VALUES (?, ?, ?, ?)", 
                      (colaborador, item_selecionado, datetime.now().strftime("%d/%m/%Y %H:%M"), "SAÍDA"))
            conn.commit()
            st.success(f"Saída de {item_selecionado} registrada com sucesso!")
        else:
            st.error("Saldo insuficiente no estoque!")
        conn.close()

elif choice == "Reposição (Entrada)":
    st.subheader("Entrada de Mercadoria")
    df_estoque = get_estoque()
    item_add = st.selectbox("Selecione o Item para Repor", df_estoque['item'].tolist())
    qtd_add = st.number_input("Quantidade Adquirida", min_value=1, value=1)
    
    if st.button("Adicionar ao Estoque"):
        conn = sqlite3.connect('estoque_ti.db')
        c = conn.cursor()
        c.execute("UPDATE produtos SET quantidade = quantidade + ? WHERE item = ?", (qtd_add, item_add))
        c.execute("INSERT INTO historico (colaborador, item, data, tipo) VALUES (?, ?, ?, ?)", 
                  ("ESTOQUE", item_add, datetime.now().strftime("%d/%m/%Y %H:%M"), "ENTRADA"))
        conn.commit()
        conn.close()
        st.success("Estoque atualizado!")

elif choice == "Histórico":
    st.subheader("Histórico de Movimentações")
    conn = sqlite3.connect('estoque_ti.db')
    df_hist = pd.read_sql_query("SELECT colaborador, item, data, tipo FROM historico ORDER BY id DESC", conn)
    st.dataframe(df_hist, use_container_width=True)
    conn.close()