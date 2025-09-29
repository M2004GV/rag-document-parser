# This RAG application takes in an invoice PDF, loads the data into a Vector Database,
# Send the Invoice information as context to the OpenAI GPT and
# comes banck with extracted details

import streamlit as st
from dotenv import load_dotenv
import invoiceutil as iu

def main():
    load_dotenv()

    st.set_page_config(page_title="Invoice Extraction Bot")
    st.title("Invoice Extraction Bot. . .")
    st.subheader("I can help you in extracting invoice data")

    # Upload the Invoices (pdf files)
    pdf = st.file_uploader("Upload invoices here, only PDF files allowed", type=["pdf"], accept_multiple_files=True)

    submit = st.button("Extract Data")

    if submit:
        with st.spinner("Wait for it..."):
            df = iu.create_docs(pdf)
            if df.empty:
                st.info("Nenhum arquivo processado ou sem dados extraídos.")
            else:
                st.dataframe(df, use_container_width=True)

    st.success("Hope I was able to save your time")
    
if __name__ == '__main__':
    main()