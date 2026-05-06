import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
import io
import os

# --- LISTA DE UNIDADES ---
UNIDADES = ["MATRIZ", "RIO DE JANEIRO", "JOINVILLE", "BELO HORIZONTE"]

# --- CONFIGURAÇÃO DO BANCO DE DADOS ---
def init_db():
    conn = sqlite3.connect('estoque_ti.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS produtos 
                 (unidade TEXT, item TEXT, quantidade INTEGER, limite_minimo INTEGER, PRIMARY KEY (unidade, item))''')
    c.execute('''CREATE TABLE IF NOT EXISTS historico 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, unidade TEXT, colaborador TEXT, item TEXT, data TEXT, tipo TEXT, chamado TEXT, quantidade INTEGER)''')
    
    # Migrações de colunas para versões antigas
    try: c.execute("ALTER TABLE historico ADD COLUMN chamado TEXT")
    except: pass
    try: c.execute("ALTER TABLE historico ADD COLUMN quantidade INTEGER")
    except: pass
    try: c.execute("ALTER TABLE historico ADD COLUMN unidade TEXT DEFAULT 'MATRIZ'")
    except: pass
    conn.commit()
    conn.close()

init_db()

SENHA_ADMIN = "admin123"

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

# --- CONFIGURAÇÕES VISUAIS ---
st.set_page_config(page_title="TOTVS - Controlo de Stock TI", layout="wide", initial_sidebar_state="expanded")

# Esconder botões de programador e menu nativo
st.markdown("""
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    [data-testid="stAppDeployButton"] {display: none;}
    /* Garante que o fundo da tabela seja visível no modo escuro */
    .stDataFrame {border: 1px solid #444;}
    </style>
""", unsafe_allow_html=True)

# --- LOGÓTIPO CENTRALIZADO ---
# Usamos colunas largas para centralizar sem "esmagar" a imagem
col_esq, col_centro, col_dir = st.columns([1, 2, 1])
with col_centro:
    # O nome deve ser EXATAMENTE igual ao que está no teu screenshot do GitHub
    st.image("logo_totvs_2025_white.png", use_container_width=True)

# --- MENU LATERAL ---
st.sidebar.markdown("### 🏢 Unidade Operacional")
unidade_atual = st.sidebar.selectbox("Selecione a Unidade", UNIDADES)
st.sidebar.divider()
menu = ["📊 Dashboard Geral", "📤 Saída (Entrega)", "📥 Entrada (Reposição)", "⚙️ Gestão de Itens", "📜 Histórico"]
choice = st.sidebar.selectbox("Menu Principal", menu)

# --- TELAS ---

if choice == "📊 Dashboard Geral":
    st.header(f"📦 Inventário Completo - {unidade_atual}")
    
    conn = sqlite3.connect('estoque_ti.db')
    df = pd.read_sql_query(f"SELECT item as 'Produto', quantidade as 'Qtd Atual', limite_minimo as 'Qtd Mínima' FROM produtos WHERE unidade = '{unidade_atual}' ORDER BY item ASC", conn)
    conn.close()

    if df.empty:
        st.info("Nenhum item cadastrado. Vá a 'Gestão de Itens' para começar.")
    else:
        # VISIBILIDADE MELHORADA: Uma única tabela com todos os produtos
        # Destacamos em vermelho o que está a zeros ou abaixo do limite
        def alert_style(row):
            if row['Qtd Atual'] <= 0:
                return ['background-color: #721c24; color: white'] * len(row)
            elif row['Qtd Atual'] <= row['Qtd Mínima']:
                return ['background-color: #856404; color: white'] * len(row)
            return [''] * len(row)

        st.dataframe(df.style.apply(alert_style, axis=1), use_container_width=True, height=500)
        
        # Resumo rápido abaixo da tabela
        baixos = df[df['Qtd Atual'] <= df['Qtd Mínima']].shape[0]
        if baixos > 0:
            st.warning(f"🚨 Atenção: Existem {baixos} produtos com stock crítico ou zerado na unidade {unidade_atual}.")

elif choice == "📤 Saída (Entrega)":
    st.header(f"Registar Entrega - {unidade_atual}")
    c1, c2 = st.columns(2)
    with c1:
        colaborador = st.text_input("Nome/Login do Colaborador").upper()
        chamado = st.text_input("Número do Chamado").upper()
    with c2:
        itens = [row[0] for row in run_query("SELECT item FROM produtos WHERE unidade = ? ORDER BY item ASC", (unidade_atual,))]
        if itens:
            item_sel = st.selectbox("Selecione o Produto", itens)
            qtd_saida = st.number_input("Quantidade", min_value=1, step=1)
            
            if st.button("Confirmar Saída"):
                if colaborador and chamado:
                    saldo = run_query("SELECT quantidade FROM produtos WHERE unidade = ? AND item = ?", (unidade_atual, item_sel))[0][0]
                    if saldo >= qtd_saida:
                        run_query("UPDATE produtos SET quantidade = quantidade - ? WHERE unidade = ? AND item = ?", (qtd_saida, unidade_atual, item_sel), True)
                        run_query("INSERT INTO historico (unidade, colaborador, item, data, tipo, chamado, quantidade) VALUES (?, ?, ?, ?, 'SAÍDA', ?, ?)", 
                                  (unidade_atual, colaborador, item_sel, datetime.now().strftime("%d/%m/%Y %H:%M"), chamado, qtd_saida), True)
                        st.success(f"✅ Saída de {qtd_saida}x {item_sel} registada!")
                        st.balloons()
                    else: st.error("Stock insuficiente!")
                else: st.error("Preencha todos os campos.")
        else: st.warning("Não há produtos cadastrados nesta unidade.")

elif choice == "📥 Entrada (Reposição)":
    st.header(f"Entrada de Material - {unidade_atual}")
    itens = [row[0] for row in run_query("SELECT item FROM produtos WHERE unidade = ? ORDER BY item ASC", (unidade_atual,))]
    if itens:
        item_ent = st.selectbox("Selecione o Produto para Repor", itens)
        qtd_ent = st.number_input("Quantidade Recebida", min_value=1, step=1)
        if st.button("Confirmar Entrada"):
            run_query("UPDATE produtos SET quantidade = quantidade + ? WHERE unidade = ? AND item = ?", (qtd_ent, unidade_atual, item_ent), True)
            run_query("INSERT INTO historico (unidade, colaborador, item, data, tipo, chamado, quantidade) VALUES (?, 'REPOSIÇÃO', ?, ?, 'ENTRADA', 'N/A', ?)", 
                      (unidade_atual, item_ent, datetime.now().strftime("%d/%m/%Y %H:%M"), qtd_ent), True)
            st.success(f"📥 Stock de {item_ent} atualizado!")
    else: st.warning("Cadastre o item primeiro na aba 'Gestão'.")

elif choice == "⚙️ Gestão de Itens":
    st.header(f"Configurações de Itens - {unidade_atual}")
    t1, t2, t3, t4 = st.tabs(["🆕 Cadastrar Novo", "✏️ Ajustar Stock/Mínimo", "🗑️ Remover", "🚨 Reset Unidade"])
    
    with t1:
        n_item = st.text_input("Nome do Produto (ex: Mouse Logitech)").upper()
        n_qtd = st.number_input("Qtd Inicial", min_value=0)
        n_min = st.number_input("Limite de Alerta (Mínimo)", min_value=1, value=5)
        if st.button("Gravar Novo Produto"):
            run_query("INSERT OR IGNORE INTO produtos VALUES (?, ?, ?, ?)", (unidade_atual, n_item, n_qtd, n_min), True)
            st.success(f"Item {n_item} adicionado à unidade {unidade_atual}!")

    with t2:
        df_edit = pd.DataFrame(run_query("SELECT item, quantidade, limite_minimo FROM produtos WHERE unidade = ?", (unidade_atual,)), columns=['item', 'q', 'm'])
        if not df_edit.empty:
            sel_edit = st.selectbox("Escolha o item para editar", df_edit['item'].tolist())
            linha = df_edit[df_edit['item'] == sel_edit].iloc[0]
            nova_q = st.number_input("Nova Quantidade Atual", value=int(linha['q']))
            nova_m = st.number_input("Novo Limite Mínimo", value=int(linha['m']))
            if st.button("Salvar Alterações"):
                run_query("UPDATE produtos SET quantidade = ?, limite_minimo = ? WHERE unidade = ? AND item = ?", (nova_q, nova_m, unidade_atual, sel_edit), True)
                st.success("Alterado!")

    with t3:
        # Opção para remover item do catálogo
        item_rem = st.selectbox("Item para remover definitivamente", df_edit['item'].tolist() if not df_edit.empty else ["Nenhum"])
        if st.checkbox(f"Confirmo que quero apagar {item_rem}"):
            if st.button("Apagar Agora"):
                run_query("DELETE FROM produtos WHERE unidade = ? AND item = ?", (unidade_atual, item_rem), True)
                st.rerun()

    with t4:
        st.error("ZONA PERIGOSA: Reset de Unidade")
        senha = st.text_input("Senha Admin", type="password")
        confirm = st.text_input("Digite 'CONFIRMAR' para apagar tudo desta unidade")
        if st.button("EXECUTAR RESET"):
            if senha == SENHA_ADMIN and confirm == "CONFIRMAR":
                run_query("DELETE FROM produtos WHERE unidade = ?", (unidade_atual,), True)
                run_query("DELETE FROM historico WHERE unidade = ?", (unidade_atual,), True)
                st.success("Unidade limpa!")
                st.rerun()

elif choice == "📜 Histórico":
    st.header(f"Registo de Movimentações - {unidade_atual}")
    df_h = pd.read_sql_query(f"SELECT colaborador as 'Quem', item as 'O quê', quantidade as 'Qtd', data as 'Quando', tipo as 'Ação', chamado as 'Chamado' FROM historico WHERE unidade = '{unidade_atual}' ORDER BY id DESC", sqlite3.connect('estoque_ti.db'))
    
    if not df_h.empty:
        st.dataframe(df_h, use_container_width=True)
        st.download_button("📥 Exportar Histórico (Excel)", to_excel(df_h), f"historico_{unidade_atual}.xlsx")
    else:
        st.info("Ainda não existem movimentações registadas.")
