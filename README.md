# Analisador de Gastos com RAG — Cartão de Crédito e Notas Fiscais

Aplicação prática de **Geração Aumentada por Recuperação (RAG)** para extração e análise inteligente de faturas de cartão de crédito e notas fiscais em PDF, desenvolvida como parte do curso **Introduction to RAG** (Coursera).

---

## Visão Geral

O sistema processa documentos PDF com uma pipeline RAG completa: carrega e vetoriza o conteúdo, recupera trechos relevantes por similaridade semântica e envia o contexto enriquecido ao modelo de linguagem (Google Gemini) para extração e análise precisa dos dados.

A interface é construída em **Streamlit** e organizada em três abas:

| Aba | Funcionalidade |
|-----|---------------|
| **Gastos do Cartão** | Upload de múltiplas faturas, extração de transações, KPIs, gráficos e análise com IA |
| **Assistente Financeiro** | Chat conversacional para perguntas sobre os gastos extraídos |
| **Notas Fiscais** | Extração de campos estruturados de notas fiscais em PDF |

---

## Funcionalidades

### Upload de múltiplos arquivos
Envie uma ou mais faturas de uma vez. O sistema consolida todas as transações em um único conjunto de dados para análise unificada.

### Visualizações e métricas
- **KPIs rápidos:** total gasto, número de transações e quantidade de meses analisados.
- **Gráfico de pizza:** distribuição dos gastos por categoria.
- **Gráfico de barras por mês:** evolução dos gastos ao longo do tempo.
- **Ranking dos estabelecimentos:** top 10 lugares onde mais se gastou, agrupados por categoria.

### Análise e recomendações com IA
Gera um relatório automático com insights sobre os padrões de consumo e sugestões de economia com base nos dados das faturas.

### Assistente financeiro por chat
Converse diretamente com a IA sobre seus gastos. Exemplos de perguntas:
- *"Qual categoria eu mais gastei?"*
- *"Quanto gastei com alimentação em março?"*
- *"Quais gastos posso cortar para economizar R$ 200?"*
- *"Tenho algum gasto recorrente que poderia cancelar?"*

### Extração de notas fiscais
Processa múltiplos PDFs de notas fiscais e retorna os campos-chave (número, descrição, quantidade, data, preço unitário, valor total) em uma tabela estruturada.

---

## Arquitetura RAG

```
PDF(s) → Loader → Chunks → Embeddings → FAISS (vector store)
                                               ↓
                              Similarity Search → Contexto relevante
                                               ↓
                              Prompt aumentado → Gemini (LLM) → Resposta estruturada
```

**Tecnologias utilizadas:**
- [LangChain](https://python.langchain.com/) `>=0.3` — pipeline RAG (retrieval chain, stuff documents chain)
- [Google Gemini](https://ai.google.dev/) — LLM e embeddings via `langchain-google-genai`
- [FAISS](https://faiss.ai/) — banco de dados vetorial em memória
- [Streamlit](https://streamlit.io/) — interface web
- [Plotly](https://plotly.com/python/) — gráficos interativos

---

## Como executar

### Pré-requisitos

- Python **3.11** ou superior
- Uma **chave de API do Google Gemini** (gratuita em [aistudio.google.com](https://aistudio.google.com/app/apikey))

### 1. Clone o repositório

```bash
git clone https://github.com/M2004GV/rag-document-parser.git
cd rag-document-parser
```

### 2. Crie e ative um ambiente virtual

```bash
# Criar
python -m venv .venv

# Ativar — Linux/macOS
source .venv/bin/activate

# Ativar — Windows
.venv\Scripts\activate
```

### 3. Instale as dependências

```bash
pip install -r requirements.txt
```

### 4. Configure as variáveis de ambiente

```bash
# Copie o arquivo de exemplo
cp .env.example .env
```

Abra o arquivo `.env` e substitua o valor pelo sua chave real:

```env
GOOGLE_API_KEY=sua_chave_aqui
```

> Obtenha sua chave gratuitamente em: [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey)

### 5. Execute a aplicação

```bash
streamlit run invoice-extraction.py
```

A aplicação abrirá automaticamente no navegador em `http://localhost:8501`.

---

## Uso rápido

1. **Aba "Gastos do Cartão"** → clique em *Selecione as faturas* → envie um ou mais PDFs → clique em *Extrair Transações*.
2. Após a extração, os gráficos e métricas são exibidos automaticamente.
3. Clique em *Gerar Análise Completa* para receber insights e recomendações da IA.
4. **Aba "Assistente Financeiro"** → digite qualquer pergunta sobre seus gastos no campo de chat.
5. **Aba "Notas Fiscais"** → envie PDFs de notas fiscais e clique em *Extrair Dados*.

---

## Estrutura do projeto

```
rag-document-parser/
├── invoice-extraction.py   # Aplicação Streamlit (interface)
├── expenseutil.py          # Lógica RAG para faturas de cartão
├── invoiceutil.py          # Lógica RAG para notas fiscais
├── requirements.txt        # Dependências Python
├── .env.example            # Modelo de variáveis de ambiente
└── .gitignore
```
