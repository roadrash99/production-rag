"""MVP ingestion: raw issue JSON -> naive chunks -> bge-small -> pgvector.

Deliberately naive (replaced in Phase 1 step 2): issue body and comments are
concatenated and split into fixed-size character windows. Rebuilds the table
from scratch on every run.

Usage:
    python -m mvp.ingest
"""

import json
import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from pgvector.psycopg import register_vector
from sentence_transformers import SentenceTransformer

RAW_DIR = Path("data/raw/github")
MODEL = "BAAI/bge-small-en-v1.5"
CHUNK_CHARS = 1500  # ~400 tokens, under bge-small's 512-token limit
OVERLAP = 200


def thread_text(issue: dict) -> str:
    parts = [f"Title: {issue['title']}", issue.get("body") or ""]
    for c in issue["comments_data"]:
        parts.append(f"--- {c['user']['login']}:\n{c.get('body') or ''}")
    return "\n\n".join(parts)


def chunk(text: str) -> list[str]:
    step = CHUNK_CHARS - OVERLAP
    return [text[i:i + CHUNK_CHARS] for i in range(0, max(len(text) - OVERLAP, 1), step)]


def load_chunks() -> list[dict]:
    rows = []
    for path in sorted(RAW_DIR.glob("*/*.json")):
        issue = json.loads(path.read_text())
        repo = path.parent.name.replace("__", "/")
        for i, text in enumerate(chunk(thread_text(issue))):
            rows.append({
                "doc_id": f"github:{repo}#{issue['number']}",
                "url": issue["html_url"],
                "title": issue["title"],
                "chunk_index": i,
                "content": text,
            })
    return rows


def main():
    load_dotenv()
    rows = load_chunks()
    if not rows:
        raise SystemExit(f"no raw issues in {RAW_DIR}; run the fetcher first")
    print(f"{len(rows)} chunks from {len({r['doc_id'] for r in rows})} threads")

    model = SentenceTransformer(MODEL)
    embeddings = model.encode([r["content"] for r in rows], batch_size=32,
                              normalize_embeddings=True, show_progress_bar=True)

    with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True) as conn:
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        register_vector(conn)
        conn.execute("DROP TABLE IF EXISTS mvp_chunks")
        conn.execute("""
            CREATE TABLE mvp_chunks (
                id serial PRIMARY KEY,
                doc_id text NOT NULL,
                url text NOT NULL,
                title text NOT NULL,
                chunk_index int NOT NULL,
                content text NOT NULL,
                embedding vector(384) NOT NULL
            )
        """)
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO mvp_chunks (doc_id, url, title, chunk_index, content, embedding) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                [(r["doc_id"], r["url"], r["title"], r["chunk_index"], r["content"], e)
                 for r, e in zip(rows, embeddings)],
            )
    print("loaded into mvp_chunks")


if __name__ == "__main__":
    main()
