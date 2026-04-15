# Document indexing with Ollama

This project builds a local document index with:

- two chunking strategies
- Ollama embeddings
- JSON output with metadata for every chunk
- a comparison report for the chunking strategies

## Features

- Fixed-size chunking by word count with overlap
- Structure-aware chunking by markdown headings or text paragraph blocks
- Automatic splitting of oversized chunks before embedding
- Chunk metadata: `source`, `title`, `section`, `chunk_id`
- Embeddings are built from chunk text plus metadata (`title`, `section`, filename)
- Local JSON indexes with embeddings
- FAISS indexes for fast vector search
- Auto-generated comparison in JSON and Markdown

## Project structure

- `index_documents.py` - main CLI script
- `index_strategy.py` - separate CLI script for indexing only one strategy
- `documents/` - sample source documents
- `output/` - generated indexes and comparison report after a run

## Requirements

1. Python 3.12+
2. Running Ollama server
3. Dependencies:

```powershell
pip install pypdf faiss-cpu numpy
```

4. Pulled embedding model, for example:

```powershell
ollama pull nomic-embed-text
ollama serve
```

## Run

```powershell
python .\index_documents.py --docs-dir documents --output-dir output --model nomic-embed-text
```

If some documents still produce chunks that are too large for embeddings, tune the limit explicitly:

```powershell
python .\index_documents.py --docs-dir documents --output-dir output --model nomic-embed-text --max-embed-words 250
```

You can place `.txt`, `.md`, and `.pdf` files into `documents/`. PDF files are converted to text page by page before chunking.

If Ollama is not running yet, you can still compare chunking strategies without embeddings:

```powershell
python .\index_documents.py --docs-dir documents --output-dir output --chunks-only
```

If you want to build only one strategy, use the separate app:

```powershell
python .\index_strategy.py --strategy fixed --docs-dir documents --output-dir output --model bge-m3 --max-embed-words 250
```

Or for structure-aware chunks:

```powershell
python .\index_strategy.py --strategy structure --docs-dir documents --output-dir output --model bge-m3 --max-embed-words 250
```

## Result files

- `output/fixed_index.json`
- `output/structure_index.json`
- `output/fixed.faiss`
- `output/structure.faiss`
- `output/fixed_chunks.json`
- `output/structure_chunks.json`
- `output/comparison.json`
- `output/comparison.md`

## Output format

Each index item contains:

- `chunk` - text and metadata
- `embedding` - vector from Ollama

Example metadata fields:

```json
{
  "chunk_id": "company_handbook-structure-001",
  "strategy": "structure",
  "source": "D:/.../documents/company_handbook.md",
  "title": "company_handbook",
  "section": "Onboarding"
}
```

## Search with FAISS

After building the index, you can search it with:

```powershell
python .\search_faiss.py "incident response checklist" --index-file output/structure.faiss --metadata-file output/structure_index.json --model nomic-embed-text --top-k 5
```

The script:

- embeds the query through Ollama
- loads the FAISS index from disk
- returns the top matches with `chunk_id`, `source`, `section`, and text preview

## Notes for PDF

- Text PDF files are supported directly through `pypdf`
- Scanned PDFs without embedded text need OCR before indexing
- In structure-aware mode, PDF chunks are grouped by page: `Page 1`, `Page 2`, and so on
