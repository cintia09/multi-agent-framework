# Writing-style notes (writing plugin -- plugin-shipped knowledge)

Read by every role on demand. Captures the small set of cross-phase
conventions that keep the drafter and reviser consistent across runs.

## Voice

- Plain, direct sentences. No filler ("In today's world ...", "It is
  important to note that ..."). Cut every sentence that starts with
  "When we think about ...".
- Active voice by default; passive only when the actor genuinely does
  not matter.
- Second-person ("you") is fine for how-to articles; first-person
  plural ("we") for analysis pieces; first-person singular ("I") only
  if the user task explicitly opts in.

## Audience

- Default audience: a working professional in the topic field who has
  ~2 years of practice. Assume vocabulary, NOT context.
- Define every acronym on first use.
- Link out, do not inline-explain, anything that would take more than
  three sentences to define.

## Structure

- Lead with the thesis. The first paragraph must be readable on its
  own as the entire article in miniature.
- Sections are 200-500 words; one idea per section. Use a sub-heading
  if a section runs longer.
- Close with either (a) a one-paragraph summary OR (b) a single
  call-to-action -- never both.

## Length budgets (per article type)

| Type            | Soft target | Hard cap |
|-----------------|-------------|----------|
| blog post       | 1200 words  | 2500     |
| newsletter      | 600 words   | 1200     |
| essay           | 2500 words  | 5000     |
| how-to / tutorial | 1500 words | 3500    |

## Markdown house style

- ATX headings only (`##`).
- `-` for unordered lists, `1.` for ordered (Markdown auto-numbers).
- Code fences carry a language tag.
- Inline code spans use single backticks; never wrap multi-word phrases
  in code spans for emphasis.
- Bold for the first occurrence of a key term, italics for emphasis;
  never both.
