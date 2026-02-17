from app.services.rag.store import ingest_texts

FILE_PATH = "data/feedback_large.txt"

def main():
    with open(FILE_PATH, "r", encoding="utf-8") as f:
        text = f.read()

    chunks = ingest_texts([{
        "content": text,
        "metadata": {"source": FILE_PATH, "type": "feedback_test"}
    }])

    print(f"Ingest OK. La til {chunks} chunks.")

if __name__ == "__main__":
    main()
