from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from app.core.config import settings

embeddings = OpenAIEmbeddings(model=settings.embedding_model)
llm = ChatOpenAI(model=settings.chat_model, temperature=0.2)
