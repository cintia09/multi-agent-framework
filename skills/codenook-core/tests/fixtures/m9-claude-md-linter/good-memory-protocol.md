# CodeNook — main session

> Pure protocol conductor.

## Protocol

The main session relays router replies verbatim and drives the tick loop.

## 上下文水位监控 (M9.2)

When estimated context usage reaches 80% of the model window, the main
session must stop new work and call extractor-batch with
`--reason context-pressure` so each task's knowledge is sedimented into
memory. The main session MUST NOT scan memory directly; it only consumes
the JSON envelope from extractor-batch. See `extraction-log.jsonl` and
`MEMORY_INDEX` for canonical references.
