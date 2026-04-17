# Analisador de Gastos com RAG — Cartão de Crédito e Notas Fiscais

Aplicação prática de **Geração Aumentada por Recuperação (RAG)** para extração e análise inteligente de faturas de cartão de crédito e notas fiscais em PDF, desenvolvida como parte do curso **Introduction to RAG** (Coursera).

Roda **100% local** — sem API key, sem internet durante o uso, sem limites de cota.

---

## Visão Geral

O sistema processa documentos PDF com uma pipeline RAG simplificada: carrega o conteúdo do PDF, filtra as linhas relevantes (transações e valores) e envia o contexto diretamente ao modelo de linguagem local (**LLaMA 3.2 via Ollama**) para extração e análise precisa dos dados.

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

## Arquitetura

```
PDF(s) → PyPDFLoader → Filtro de linhas relevantes → Contexto compacto
                                                            ↓
                                             Prompt → LLaMA 3.2 (Ollama) → Resposta estruturada
```

**Tecnologias utilizadas:**
- [Ollama](https://ollama.com/) — servidor local de modelos LLM
- [LLaMA 3.2](https://ollama.com/library/llama3.2) — modelo de linguagem rodando na sua máquina
- [LangChain](https://python.langchain.com/) `>=0.3` — pipeline de processamento (LCEL)
- [Streamlit](https://streamlit.io/) — interface web
- [Plotly](https://plotly.com/python/) — gráficos interativos

---

## Como executar

### Pré-requisitos

- Python **3.11** ou superior
- **8 GB de RAM** recomendado (mínimo 4 GB com o modelo de 1B)
- [Ollama](https://ollama.com/) instalado

---

### 1. Instale o Ollama

**Linux:**
```bash
curl -fsSL https://ollama.com/install.sh | sh
```

**macOS / Windows:** baixe o instalador em [ollama.com/download](https://ollama.com/download)

---

### 2. Baixe o modelo LLaMA 3.2

```bash
ollama pull llama3.2
```

> O download é de aproximadamente **2 GB**. Necessita de pelo menos **8 GB de RAM**.  
> Se a sua máquina tiver pouca memória, use a versão menor:
> ```bash
> ollama pull llama3.2:1b
> ```
> E altere o modelo padrão em `expenseutil.py` e `invoiceutil.py` para `"llama3.2:1b"`.

---

### 3. Verifique se o Ollama está rodando

```bash
ollama list
```

Você deve ver `llama3.2` na lista. O serviço sobe automaticamente após a instalação. Caso não esteja ativo:

```bash
ollama serve
```

---

### 4. Clone o repositório

```bash
git clone https://github.com/M2004GV/rag-document-parser.git
cd rag-document-parser
```

### 5. Crie e ative um ambiente virtual

```bash
# Criar
python -m venv .venv

# Ativar — Linux/macOS
source .venv/bin/activate

# Ativar — Windows
.venv\Scripts\activate
```

### 6. Instale as dependências Python

```bash
pip install -r requirements.txt
```

### 7. Execute a aplicação

```bash
streamlit run invoice-extraction.py
```

A aplicação abrirá automaticamente no navegador em `http://localhost:8501`.

> Nenhuma chave de API ou arquivo `.env` é necessário.

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
├── .env.example            # Referência (sem chaves necessárias)
└── .gitignore
```
