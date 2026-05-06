import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import io
from PIL import Image

# --- CONFIGURAÇÃO DA PLANILHA ---
# 1. Crie uma planilha no Google Sheets com duas abas: "produtos" e "historico"
# 2. Compartilhe como "Qualquer pessoa com o link" -> "Editor"
URL_PLANILHA = "COLE_AQUI_O_LINK_DA_SUA_PLANILHA"

# --- CONFIGURAÇÕES INICIAIS ---
UNIDADES = ["MATRIZ", "RIO DE JANEIRO", "JOINVILLE"]
SENHA_ADMIN = "admin123"

st.set_page_config(page_title="Controle de Estoque TOTVS", layout="wide", initial_sidebar_state="expanded")

# --- ESTILIZAÇÃO CSS (Esconder menus e manter seta) ---
st.markdown("""
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    [data-testid="stAppDeployButton"] {display: none;}
    [data-testid="stToolbar"] {visibility: hidden;}
    [data-testid="stDecoration"] {display: none;}
    [data-testid="collapsedControl"] {visibility: visible !important; display: flex !important;}
    /* Cores das tabelas */
    .stDataFrame {border-radius: 10px;}
    </style>
""", unsafe_allow_html=True)

# --- CONEXÃO COM GOOGLE SHEETS ---
conn = st.connection("gsheets", type=GSheetsConnection)

def ler_produtos():
    return conn.read(spreadsheet=URL_PLANILHA, worksheet="produtos")

def ler_historico():
    return conn.read(spreadsheet=URL_PLANILHA, worksheet="historico")

def salvar_produtos(df):
    conn.update(spreadsheet=URL_PLANILHA, worksheet="produtos", data=df)

def salvar_historico(df):
    conn.update(spreadsheet=URL_PLANILHA, worksheet="historico", data=df)

# --- LOGO CENTRALIZADO ---
col_esq, col_centro, col_dir = st.columns([2, 1, 2])
with col_centro:
    try:
        logo = Image.open("logo_totvs_2025_white.png")
        st.image(logo, use_container_width=True)
    except:
        st.warning("⚠️ Logo não carregado. Verifique o arquivo no GitHub.")

# --- BARRA LATERAL ---
st.sidebar.title("🏢 Unidade")
unidade_atual = st.sidebar.selectbox("Selecione", UNIDADES)
st.sidebar.divider()
menu = ["📊 Dashboard", "📤 Saída", "📥 Entrada", "⚙️ Gestão", "📜 Histórico"]
choice = st.sidebar.selectbox("Menu Principal", menu)

# --- LÓGICA DAS TELAS ---

if choice == "📊 Dashboard":
    st.header(f"Painel de Controle - {unidade_atual}")
    df_p = ler_produtos()
    df_u = df_p[df_p['unidade'] == unidade_atual]

    if df_u.empty:
        st.info("Nenhum item cadastrado para esta unidade.")
    else:
        # 1. ESTOQUE ZERADO
        df_zerado = df_u[df_u['quantidade'] <= 0]
        if not df_zerado.empty:
            st.error("### 🔴 ESTOQUE ZERADO (Ação Imediata)")
            st.dataframe(df_zerado[['item', 'quantidade', 'limite_minimo']], use_container_width=True)
        
        # 2. LIMITE ATINGIDO
        df_limite = df_u[(df_u['quantidade'] > 0) & (df_u['quantidade'] <= df_u['limite_minimo'])]
        if not df_limite.empty:
            st.warning("### 🟡 ATENÇÃO - LIMITE MÍNIMO ATINGIDO")
            st.dataframe(df_limite[['item', 'quantidade', 'limite_minimo']], use_container_width=True)

        # 3. ESTOQUE OK
        df_ok = df_u[df_u['quantidade'] > df_u['limite_minimo']]
        if not df_ok.empty:
            st.success("### 🟢 ESTOQUE OK")
            st.dataframe(df_ok[['item', 'quantidade', 'limite_minimo']], use_container_width=True)

elif choice == "📤 Saída":
    st.header(f"Registrar Entrega - {unidade_atual}")
    df_p = ler_produtos()
    df_unidade = df_p[df_p['unidade'] == unidade_atual]
    
    c1, c2 = st.columns(2)
    with c1:
        user = st.text_input("Colaborador").upper()
        cham = st.text_input("Número do Chamado").upper()
    with c2:
        itens = df_unidade['item'].tolist()
        if itens:
            it_sel = st.selectbox("Selecione o Produto", itens)
            q_sai = st.number_input("Quantidade", min_value=1, step=1)
            
            if st.button("Confirmar Baixa"):
                if user and cham:
                    idx = df_p[(df_p['unidade'] == unidade_atual) & (df_p['item'] == it_sel)].index[0]
                    if df_p.at[idx, 'quantidade'] >= q_sai:
                        df_p.at[idx, 'quantidade'] -= q_sai
                        salvar_produtos(df_p)
                        
                        df_h = ler_historico()
                        novo_log = pd.DataFrame([{"unidade": unidade_atual, "colaborador": user, "item": it_sel, "data": datetime.now().strftime("%d/%m/%Y %H:%M"), "tipo": "SAÍDA", "chamado": cham, "quantidade": q_sai}])
                        salvar_historico(pd.concat([df_h, novo_log], ignore_index=True))
                        
                        st.toast(f"✅ Saída registrada: {it_sel}")
                        st.success(f"Registrado: {q_sai}x {it_sel} para {user}")
                        st.balloons()
                    else: st.error("Estoque insuficiente.")
                else: st.error("Preencha todos os campos.")

elif choice == "📥 Entrada":
    st.header(f"Entrada de Material - {unidade_atual}")
    df_p = ler_produtos()
    itens = df_p[df_p['unidade'] == unidade_atual]['item'].tolist()
    
    if itens:
        it_ent = st.selectbox("Produto", itens)
        q_ent = st.number_input("Qtd Recebida", min_value=1, step=1)
        if st.button("Adicionar ao Estoque"):
            idx = df_p[(df_p['unidade'] == unidade_atual) & (df_p['item'] == it_ent)].index[0]
            df_p.at[idx, 'quantidade'] += q_ent
            salvar_produtos(df_p)
            
            df_h = ler_historico()
            novo_log = pd.DataFrame([{"unidade": unidade_atual, "colaborador": "SISTEMA", "item": it_ent, "data": datetime.now().strftime("%d/%m/%Y %H:%M"), "tipo": "ENTRADA", "chamado": "REPOSIÇÃO", "quantidade": q_ent}])
            salvar_historico(pd.concat([df_h, novo_log], ignore_index=True))
            st.toast("📥 Estoque Atualizado!")
            st.success(f"Sucesso: {q_ent} unidades de {it_ent} adicionadas.")

elif choice == "⚙️ Gestão":
    st.header(f"Gerenciamento - {unidade_atual}")
    t1, t2, t3 = st.tabs(["🆕 Cadastrar Item", "🗑️ Remover Item", "🧹 Zerar Histórico"])
    df_p = ler_produtos()

    with t1:
        n_it = st.text_input("Nome do Periférico").upper()
        n_q = st.number_input("Qtd Inicial", min_value=0)
        n_m = st.number_input("Limite Mínimo", min_value=1, value=5)
        if st.button("Salvar Cadastro"):
            if n_it:
                # Salva Produto
                novo_p = pd.DataFrame([{"unidade": unidade_atual, "item": n_it, "quantidade": n_q, "limite_minimo": n_m}])
                salvar_produtos(pd.concat([df_p, novo_p], ignore_index=True))
                
                # Salva Histórico de Cadastro
                df_h = ler_historico()
                novo_log = pd.DataFrame([{"unidade": unidade_atual, "colaborador": "SISTEMA", "item": n_it, "data": datetime.now().strftime("%d/%m/%Y %H:%M"), "tipo": "CADASTRO", "chamado": "N/A", "quantidade": n_q}])
                salvar_historico(pd.concat([df_h, novo_log], ignore_index=True))
                
                st.success(f"Item {n_it} cadastrado com log de histórico!")
                st.rerun()

    with t2:
        df_u = df_p[df_p['unidade'] == unidade_atual]
        if not df_u.empty:
            it_rem = st.selectbox("Escolha o item para remover", df_u['item'].tolist())
            if st.checkbox(f"Confirmo a remoção definitiva de {it_rem}"):
                if st.button("Remover Agora"):
                    df_p = df_p[~((df_p['unidade'] == unidade_atual) & (df_p['item'] == it_rem))]
                    salvar_produtos(df_p)
                    st.rerun()

    with t3:
        st.subheader("Limpar Logs da Planilha")
        senha = st.text_input("Senha Admin", type="password")
        if senha == SENHA_ADMIN:
            if st.button("Apagar Histórico desta Unidade"):
                df_h = ler_historico()
                df_h = df_h[df_h['unidade'] != unidade_atual]
                salvar_historico(df_h)
                st.success("Histórico limpo permanentemente!")
                st.rerun()

elif choice == "📜 Histórico":
    st.header(f"Movimentações - {unidade_atual}")
    df_h = ler_historico()
    df_h_u = df_h[df_h['unidade'] == unidade_atual]
    
    if not df_h_u.empty:
        st.dataframe(df_h_u.sort_index(ascending=False), use_container_width=True)
        csv = df_h_u.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Baixar Excel (CSV)", csv, f"hist_{unidade_atual}.csv", "text/csv")
    else:
        st.info("Nenhuma movimentação registrada.")
