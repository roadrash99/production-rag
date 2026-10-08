"""MVP QA: question -> top-k chunks from pgvector -> Groq answer with sources.

Usage:
    python -m mvp.ask "Why does vLLM run out of memory with long prompts?"
"""

import os
import sys
import textwrap

import psycopg
from dotenv import load_dotenv
from groq import Groq
from pgvector.psycopg import register_vector
from sentence_transformers import SentenceTransformer

MODEL = "BAAI/bge-small-en-v1.5"
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "  # bge query instruction
GEN_MODEL = "openai/gpt-oss-120b"
TOP_K = 5


def retrieve(question: str) -> list[tuple]:
    q = SentenceTransformer(MODEL).encode(QUERY_PREFIX + question, normalize_embeddings=True)
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        register_vector(conn)
        return conn.execute(
            "SELECT doc_id, url, title, content, 1 - (embedding <=> %s) AS score "
            "FROM mvp_chunks ORDER BY embedding <=> %s LIMIT %s",
            (q, q, TOP_K),
        ).fetchall()


def answer(question: str, chunks: list[tuple]) -> str:
    context = "\n\n".join(f"[{i}] ({doc_id}) {title}\n{content}"
                          for i, (doc_id, _, title, content, _) in enumerate(chunks, 1))
    prompt = (
        "Answer the question using only the GitHub issue excerpts below. "
        "Cite sources inline as [1], [2], etc. If the excerpts don't contain "
        "the answer, say so. Reply in plain text for a terminal: no Markdown "
        "(no bold, headings or quote blocks), short paragraphs or '-' bullets.\n\n"
        f"{context}\n\nQuestion: {question}"
    )
    resp = Groq().chat.completions.create(
        model=GEN_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    return resp.choices[0].message.content


def main():
    load_dotenv()
    if len(sys.argv) < 2:
        raise SystemExit('usage: python -m mvp.ask "your question"')
    question = " ".join(sys.argv[1:])

    chunks = retrieve(question)
    text = answer(question, chunks).replace("‑", "-")  # non-breaking hyphens

    print("\nAnswer -\n")
    for para in text.splitlines():
        print(textwrap.fill(para, width=88, subsequent_indent="  " if para.startswith("-") else ""))
    print("\nSources -\n")
    for i, (doc_id, url, title, _, score) in enumerate(chunks, 1):
        print(f"  [{i}] {title[:80]}\n      {url}  (score {score:.3f})")


if __name__ == "__main__":
    main()
