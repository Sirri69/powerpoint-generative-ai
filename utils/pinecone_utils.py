import backoff
import openai
import pinecone
from langchain.docstore.document import Document
from typing import List

from utils.utils import setup_logger

logger = setup_logger(__name__)


@backoff.on_exception(backoff.expo, openai.error.OpenAIError, logger=logger)
def call_embeddings_with_backoff(input_text: str, model: str = "text-embedding-ada-002"):
    """
    Wrapper function to call open ai and get the embeddings of the input text
    """
    return openai.Embedding.create(
        input=input_text, model=model
    )["data"][0]["embedding"]


def get_embeddings(texts: List[str]) -> List:
    """
    Calls a wrapper function with backoff enabled to handle errors from openai
    """
    return [
        call_embeddings_with_backoff(input_text=text)
        for text in texts
    ]


def index_data(index: pinecone.Index, documents: List[Document]):
    """
    Function to add records to the index
    """
    id = index.describe_index_stats()['total_vector_count']
    texts = [text.page_content for text in documents]
    embeddings = get_embeddings(texts=texts)
    for chunk_id, text, embedding, document in zip(range(0, len(texts)), texts, embeddings, documents):
        id += 1
        metadata = {
            'chunk_id': chunk_id,
            'text': text,
            'slide_index': document.metadata.get('slide_index', -1),
            'filepath': document.metadata.get('filepath', 'filepath not found')
        }
        logger.info(metadata)
        chunkInfo = (str(id), embedding, metadata)
        index.upsert(vectors=[chunkInfo])


def search_pinecone_index(
    index: pinecone.Index,
    query: str,
    num_results: int,
    threshold: float = 0.8
) -> List[str]:
    """
    Function to search pinecone index
    """
    # get total number of vectors from pinecone to fix out of bounds error
    TOTAL_NUM_VECTORS = index.describe_index_stats()['total_vector_count']
    if num_results > TOTAL_NUM_VECTORS:
        num_results = TOTAL_NUM_VECTORS

    query_em = get_embeddings([query])[0]

    try:
        result = index.query(query_em, top_k=num_results, includeMetadata=True)
        num_matches = len(result['matches'])

        # iterate through and only return the results that are within the set threshold
        return [
            result['matches'][i]['metadata']
            for i in range(num_matches) 
            if result['matches'][i]['score'] >= threshold
        ]
    except Exception as e:
        logger.error(f"Error querying pinecone: {e}")
        return []