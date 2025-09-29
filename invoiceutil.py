from langchain.chat_models import ChatOpenAI
from langchain.prompts import PromptTemplate
from langchain_community.document_loaders import PyPDFLoader
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain.chains import create_retrieval_chain
from langchain.chains.combine_documents import create_stuff_documents_chain

# Iterate over files in
# that user uploaded PDF files, one by one
def create_docs(user_pdf_list):
    """This function is used to extract the invoice data from the given PDF files.
    It uses the LangChain agent to extract the data from given PDF files."""

    for filename in user_pdf_list:
        
        #Extract PDF Data
        print("Processing -", filename.name)
        loader=PyPDFLoader(filename.name)
        pages=loader.load_and_split()

        embeddings = OpenAIEmbeddings()
        
        vector = FAISS.from_documents(pages, embeddings)

        template = """Extract all the following values : invoice no., Description, Quantity, date,
        Unit price, Amount, Total, email, phone number and address from the following Inoice content
        (create a JSON output with the extracted fields only):
        {context}
        The fields and values in the above content may be jumbled up as they are extracted from a PDF. Please
        the fields and values correctly based on the fields asked for in the question above.
        Expected JSON output format as follows:
        {{'Invoice no.': 'xxxxxxxx','Description': 'xxxxxx','Quantity': 'x','Date': 'dd/mm/yyyy',
        'Unit price': 'xxx.xx','Amount': 'xxx.xx','Total': 'xxx.xx','Email': 'xxx@xxx.xxx','Phone number': 'xxxxxxxxxx','Address': 'xxxxxx xxxxx xxxxx'}}
        Remove any dollar symbols or currency symbols from the extracted values.
        """
        prompt = PromptTemplate.from_template(template)

        llm = ChatOpenAI(temperature=0, model_name="gpt-4o")
        retriever = vector.as_retriever()
        document_chain = create_stuff_documents_chain(llm, prompt)
        retrieval_chain = create_retrieval_chain(retriever, document_chain)
        response = retrieval_chain.invoke({"input":""})
        answer_content = response['answer']
        print("Extracted Data: ")
        print(answer_content)

        print("**********************Done************************")
    
    return answer_content
