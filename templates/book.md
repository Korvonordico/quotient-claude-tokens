# Template: book — a short book written in installments (non-fiction or fiction)

This template comes with Quotient. It tells each installment HOW to work; the job itself (what the book is
about, for whom, how long, in which language, which formats) is written by the user below "The job".

## How every installment works
1. Read HANDOFF.md first. Never redo a step it marks as done; never rewrite a finished chapter unless the
   handoff says it must be revised.
2. Work in small, finished steps and update HANDOFF.md after each one: what is done, what remains, where to
   resume, and the line `PROGRESS: <n>%` computed from the plan (below), not guessed.
3. Keep the context small: open only the files the current step needs (the plan, the chapter you write, the
   one before it). Do not read the whole book to write one chapter.
4. Write the book in the language of "The job". These working rules stay in English.

## The order of the work
1. **Plan** (first installment): `PLAN.md` with the chapters, the length of each in words, what each one
   must contain, and the facts or sources it needs. The plan is the measure of progress: a chapter written
   is worth its share of the words; a chapter revised, its share again; the final files, 10%.
2. **Sources** (non-fiction): every date, name, number or "the first to..." gets a source in `SOURCES.md`
   (author or site, title, link). What cannot be verified is written as uncertain, never as a fact.
3. **Chapters**, one at a time, each in its own file: `chapters/NN-short-title.md`. Hold the length the plan
   gives. Simple words for the readers named in "The job".
4. **Revision**, one chapter at a time: read it once as the reader would; cut repetitions and explanations
   that are too long; check every fact against `SOURCES.md`; check that it leads into the next chapter.
5. **Final files**, only if "The job" asks for them (EPUB, PDF, cover): made with scripts kept in `tools/`,
   so they can be made again after a change. Check the result opens.
6. **REPORT.md** in the work folder, in the language of the job: where every file is, how many words, what
   is uncertain or left to the author's choice, what the author should check first.

## Finished
Write `JOB DONE` as the first line of HANDOFF.md only when every item of the plan is written, revised and
checked, and REPORT.md exists.
