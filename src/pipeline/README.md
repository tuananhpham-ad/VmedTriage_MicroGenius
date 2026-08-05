# Thu muc `src/pipeline`

Thu muc nay phuc vu pipeline Weaviate Cloud/RAG ben canh luong triage API. No co the upload knowledge/case vao Weaviate, search lai bang BM25/semantic/hybrid, rerank, va tao cau tra loi bang LLM.

## File

| File | Lam gi |
|---|---|
| `__init__.py` | Export cac class hay dung: `DatabaseUpdatePhase`, `UserAnswerPhase`, `WeaviateCloudRepository`. |
| `database_update_phase.py` | Phase ghi du lieu: luu `TriageCase` vao collection case, hoac upload document vao collection knowledge. |
| `user_answer_phase.py` | Phase doc du lieu: search Weaviate, build context, build prompt, goi LLM neu `use_llm=True`. |
| `weaviate_cloud.py` | Adapter Weaviate Cloud: connect, tao collection, store case/document, search, chunk, embedding, rerank. |
| `full_pipeline.py` | Script/runner demo end-to-end: ensure collection, upload sample docs, query, rerank, in ket qua. |
| `sample_data.py` | Sample documents va query mau dung cho `full_pipeline.py`. |

## Bien moi truong can co khi chay that

| Bien | Y nghia |
|---|---|
| `WEAVIATE_URL` hoac `WVC_URL` | URL cluster Weaviate Cloud. |
| `WEAVIATE_API_KEY` hoac `WVC_API_KEY` | API key Weaviate Cloud. |
| `DEEPSEEK_API_KEY`, `GEMINI_API_KEY`/`GOOGLE_API_KEY`, hoac `OPENAI_API_KEY` | Key LLM neu muon sinh cau tra loi bang model. |

