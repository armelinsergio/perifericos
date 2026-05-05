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
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, colaborador TEXT, item TEXT, data TEXT, tipo TEXT)''')
    
    # Lista Completa de Periféricos (Cadastro Inicial)
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

# Barra Lateral
st.sidebar.title("Navegação")
menu = ["📊 Dashboard", "📤 Dar Baixa (Saída)", "📥 Reposição (Entrada)", "🆕 Cadastrar Novo Item", "📜 Histórico"]
choice = st.sidebar.selectbox("Escolha uma opção", menu)

if choice == "📊 Dashboard":
    st.title("Estado Atual do Estoque")
    
    # Busca dados
    conn = sqlite3.connect('estoque_ti.db')
    df = pd.read_sql_query("SELECT * FROM produtos ORDER BY item ASC", conn)
    conn.close()

    # Alertas de Estoque Baixo
    estoque_baixo = df[df['quantidade'] <= df['limite_minimo']]
    if not estoque_baixo.empty:
        st.error(f"⚠️ Atenção! {len(estoque_baixo)} itens precisam de reposição imediata.")
        st.dataframe(estoque_baixo, use_container_width=True)

    st.divider()
    st.write("### Inventário Geral")
    st.dataframe(df, use_container_width=True)

elif choice == "📤 Dar Baixa (Saída)":
    st.title("Registrar Entrega")
    
    colaborador = st.text_input("Usuário do Colaborador").strip().upper()
    
    # Carrega itens para o selectbox
    df_itens = pd.DataFrame(run_query("SELECT item FROM produtos ORDER BY item ASC"), columns=['item'])
    item_selecionado = st.selectbox("Selecione o Periférico", df_itens['item'].tolist())
    qtd = st.number_input("Quantidade", min_value=1, step=1)

    # Variável de segurança para travar o botão caso haja duplicidade não autorizada
    bloquear_entrega = False

    if colaborador:
        # VERIFICAÇÃO DE DUPLICIDADE
        historico = run_query("SELECT data FROM historico WHERE colaborador = ? AND item = ? AND tipo = 'SAÍDA'", (colaborador, item_selecionado))
        
        if historico:
            st.warning(f"🛑 CUIDADO: O usuário **{colaborador}** já recebeu um(a) **{item_selecionado}** anteriormente em {historico[0][0]}.")
            
            # Cria a opção explícita para o analista autorizar a continuação
            autorizar_duplicidade = st.checkbox("Estou ciente do histórico e autorizo uma nova entrega deste item.")
            
            if not autorizar_duplicidade:
                bloquear_entrega = True # Trava a entrega se a caixa não for marcada

    if st.button("Confirmar Baixa"):
        if not colaborador:
            st.error("Por favor, insira o usuário do colaborador.")
        elif bloquear_entrega:
            st.error("⚠️ Para entregar um item duplicado, você precisa marcar a caixa de autorização acima.")
        else:
            # Lógica de baixa segura
            saldo = run_query("SELECT quantidade FROM produtos WHERE item = ?", (item_selecionado,))[0][0]
            if saldo >= qtd:
                # Atualiza estoque
                run_query("UPDATE produtos SET quantidade = quantidade - ? WHERE item = ?", (qtd, item_selecionado), True)
                # Grava histórico
                run_query("INSERT INTO historico (colaborador, item, data, tipo) VALUES (?, ?, ?, ?)", 
                          (colaborador, item_selecionado, datetime.now().strftime("%d/%m/%Y %H:%M"), "SAÍDA"), True)
                st.success(f"Baixa realizada com sucesso! Novo saldo de {item_selecionado}: {saldo - qtd}")
                st.balloons()
            else:
                st.error(f"Erro: Saldo insuficiente no estoque. Temos apenas {saldo} unidades.")

elif choice == "📥 Reposição (Entrada)":
    st.title("Entrada de Itens")
    df_itens = pd.DataFrame(run_query("SELECT item FROM produtos ORDER BY item ASC"), columns=['item'])
    item_add = st.selectbox("Selecione o Item", df_itens['item'].tolist())
    qtd_add = st.number_input("Quantidade Adquirida", min_value=1, step=1)
    
    if st.button("Adicionar ao Estoque"):
        run_query("UPDATE produtos SET quantidade = quantidade + ? WHERE item = ?", (qtd_add, item_add), True)
        run_query("INSERT INTO historico (colaborador, item, data, tipo) VALUES (?, ?, ?, ?)", 
                  ("REPOSIÇÃO", item_add, datetime.now().strftime("%d/%m/%Y %H:%M"), "ENTRADA"), True)
        st.success(f"Entrada de {qtd_add} unidades de {item_add} registrada!")

elif choice == "🆕 Cadastrar Novo Item":
    st.title("Cadastrar Novo Periférico no Sistema")
    novo_nome = st.text_input("Nome do Periférico").strip()
    nova_qtd = st.number_input("Quantidade Inicial em Estoque", min_value=0, step=1)
    novo_limite = st.number_input("Limite para Alerta de Compra", min_value=1, value=2, step=1)
    
    if st.button("Cadastrar"):
        if novo_nome:
            try:
                run_query("INSERT INTO produtos (item, quantidade, limite_minimo) VALUES (?, ?, ?)", (novo_nome, nova_qtd, novo_limite), True)
                st.success(f"Item '{novo_nome}' cadastrado com sucesso!")
            except:
                st.error("Este item já existe no sistema.")
        else:
            st.error("Digite o nome do periférico.")

elif choice == "📜 Histórico":
    st.title("Histórico de Movimentações")
    conn = sqlite3.connect('estoque_ti.db')
    df_hist = pd.read_sql_query("SELECT colaborador, item, data, tipo FROM historico ORDER BY id DESC", conn)
    st.dataframe(df_hist, use_container_width=True)
    conn.close()
